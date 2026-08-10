"""Orchestration: run the agents in dependency order, persist everything, build a report.

Design decisions worth stating:

* **Failure is partial, never total.** One agent failing produces a report with that
  section marked unavailable, not an error page. A user who pasted a manuscript should
  get the eleven sections that worked.
* **Every step is traced.** Each agent run is persisted with its provider, model, prompt
  version, timing and reasoning summary, so any conclusion in a report can be traced back
  to what produced it.
* **The contract is applied on write.** Claims are coerced into lawful form before they
  touch the database, so nothing unlawful can be read back out.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.agents.base import AgentResult, AnalysisContext, BaseAgent
from app.agents.contracts import (
    SECTION_ORDER,
    SECTION_TITLES,
    ClaimDraft,
    ClaimType,
    Section,
    summarize_confidence,
)
from app.agents.provider import get_provider
from app.agents.report import build_report
from app.agents.specialists import (
    AstronomyAgent,
    CalendarAgent,
    EntityAgent,
    EvidenceAgent,
    HistoricalContextAgent,
    InterpretationAgent,
    LanguageAgent,
    SourceIdentificationAgent,
)
from app.core.logging import get_logger
from app.db.models.analysis import (
    AgentRun,
    Analysis,
    AnalysisStatus,
    Claim,
    Entity,
    EntityType,
    Reference,
    Report,
)
from app.knowledge.rag import index_analysis

logger = get_logger(__name__)

#: Execution order. Later agents read what earlier ones put in the context, so this is a
#: dependency order rather than a preference.
PIPELINE: list[tuple[type[BaseAgent], float]] = [
    (LanguageAgent, 0.12),
    (SourceIdentificationAgent, 0.24),
    (EntityAgent, 0.40),
    (CalendarAgent, 0.52),
    (AstronomyAgent, 0.66),
    (HistoricalContextAgent, 0.78),
    (InterpretationAgent, 0.90),
    (EvidenceAgent, 0.96),
]

ProgressCallback = Callable[[float, str], None]


class Orchestrator:
    def __init__(self, db: Session, *, agents: list[tuple[type[BaseAgent], float]] | None = None):
        self.db = db
        self.pipeline = agents or PIPELINE

    def run(
        self,
        analysis: Analysis,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> Analysis:
        started = time.perf_counter()
        provider = get_provider()

        analysis.status = AnalysisStatus.RUNNING
        analysis.started_at = datetime.now(UTC)
        analysis.progress = 0.02
        analysis.current_stage = "starting"
        self.db.commit()

        document = analysis.document
        ctx = AnalysisContext(
            analysis_id=analysis.id,
            text=document.raw_text,
            normalized_text=document.normalized_text,
            db=self.db,
            options=dict(analysis.options or {}),
            title=document.title,
            source_kind=document.source_kind.value,
        )

        results: list[AgentResult] = []
        all_claims: list[ClaimDraft] = []
        failed_stages: list[str] = []

        for sequence, (agent_class, progress) in enumerate(self.pipeline):
            agent = agent_class()
            analysis.current_stage = agent.name
            self.db.commit()
            if on_progress:
                on_progress(progress, agent.name)

            # The evidence agent audits everything produced so far.
            if agent_class is EvidenceAgent:
                ctx.options["_claims_for_review"] = [c.to_dict() for c in all_claims]

            result = agent.execute(ctx)
            results.append(result)
            self._persist_agent_run(analysis, agent, result, sequence)

            if result.status == "failed":
                failed_stages.append(agent.name)
            else:
                all_claims.extend(result.claims)
                if result.entities:
                    self._persist_entities(analysis, result.entities)

            analysis.progress = progress
            self.db.commit()

        # Source text is always recorded verbatim, whatever else happened.
        all_claims.insert(0, self._source_text_claim(document.raw_text))

        self._persist_claims(analysis, all_claims)

        confidence = summarize_confidence(all_claims)
        analysis.overall_confidence = confidence["overall"]
        analysis.confidence_rationale = confidence["rationale"]
        analysis.detected_language = (ctx.language or {}).get("language_code")
        analysis.translation_applied = bool(ctx.translation.get("translated_text"))
        analysis.source_identification = ctx.source_identification
        analysis.failed_stages = failed_stages

        report = build_report(
            analysis=analysis,
            document=document,
            claims=all_claims,
            results=results,
            context=ctx,
            confidence=confidence,
        )
        self._persist_report(analysis, report)

        succeeded = sum(1 for r in results if r.status == "succeeded")
        analysis.status = (
            AnalysisStatus.COMPLETED
            if not failed_stages
            else (AnalysisStatus.PARTIAL if succeeded else AnalysisStatus.FAILED)
        )
        if analysis.status == AnalysisStatus.FAILED:
            analysis.error_message = (
                "Every analysis stage failed. This usually means the AI provider is "
                "unreachable or misconfigured; see the agent trace for the specific errors."
            )

        analysis.progress = 1.0
        analysis.current_stage = "complete"
        analysis.completed_at = datetime.now(UTC)
        analysis.duration_ms = int((time.perf_counter() - started) * 1000)
        analysis.token_usage = {
            "input_tokens": sum(r.input_tokens or 0 for r in results),
            "output_tokens": sum(r.output_tokens or 0 for r in results),
            "provider": provider.name,
            "model": provider.model,
        }

        if analysis.status != AnalysisStatus.FAILED:
            index_analysis(
                self.db,
                analysis.id,
                analysis.owner_id,
                f"{analysis.title}\n{report['executive_summary']}",
            )

        self.db.commit()

        logger.info(
            "analysis.completed",
            analysis_id=analysis.id,
            status=analysis.status.value,
            claims=len(all_claims),
            failed_stages=failed_stages,
            duration_ms=analysis.duration_ms,
        )
        if on_progress:
            on_progress(1.0, "complete")
        return analysis

    # ---- persistence --------------------------------------------------------

    @staticmethod
    def _source_text_claim(text: str) -> ClaimDraft:
        excerpt = text if len(text) <= 2000 else text[:2000] + " […]"
        return ClaimDraft(
            section=Section.ORIGINAL_TEXT,
            claim_type=ClaimType.SOURCE_TEXT,
            statement="The submitted text, recorded verbatim.",
            quoted_text=excerpt,
            confidence=1.0,
            confidence_basis="This is the input itself.",
            produced_by="orchestrator",
            text_span=(0, min(len(text), 2000)),
        )

    def _persist_agent_run(
        self, analysis: Analysis, agent: BaseAgent, result: AgentResult, sequence: int
    ) -> None:
        self.db.add(
            AgentRun(
                analysis_id=analysis.id,
                agent_name=agent.name,
                sequence=sequence,
                status=result.status,
                attempt=result.attempts,
                provider=result.provider,
                model=result.model,
                prompt_version=agent.prompt_version,
                input_summary={"description": agent.description},
                output_summary=result.to_dict(),
                reasoning_summary=result.reasoning_summary,
                error_message=result.error,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                duration_ms=result.duration_ms,
                finished_at=datetime.now(UTC),
            )
        )

    def _persist_claims(self, analysis: Analysis, claims: list[ClaimDraft]) -> None:
        for ordering, draft in enumerate(claims):
            claim = Claim(
                analysis_id=analysis.id,
                section=draft.section.value,
                claim_type=draft.claim_type,
                statement=draft.statement,
                reasoning=draft.reasoning,
                confidence=draft.confidence,
                confidence_basis=draft.confidence_basis,
                produced_by=draft.produced_by,
                engine=draft.engine,
                algorithm_reference=draft.algorithm_reference,
                quoted_text=draft.quoted_text,
                text_span_start=draft.text_span[0] if draft.text_span else None,
                text_span_end=draft.text_span[1] if draft.text_span else None,
                ordering=ordering,
                payload=draft.payload,
            )
            self.db.add(claim)
            self.db.flush()

            for index, citation in enumerate(draft.citations):
                self.db.add(
                    Reference(
                        analysis_id=analysis.id,
                        claim_id=claim.id,
                        citation_text=citation.citation_text,
                        title=citation.title,
                        authors=citation.authors,
                        publication=citation.publication,
                        year=citation.year,
                        url=citation.url,
                        doi=citation.doi,
                        locator=citation.locator,
                        reference_kind=citation.reference_kind,
                        reliability=citation.reliability,
                        verified=citation.verified,
                        ordering=index,
                    )
                )

    def _persist_entities(self, analysis: Analysis, entities: list[dict]) -> None:
        for entity in entities:
            try:
                entity_type = EntityType(entity.get("entity_type", "other"))
            except ValueError:
                entity_type = EntityType.OTHER

            mentions = entity.get("mentions", [])
            self.db.add(
                Entity(
                    analysis_id=analysis.id,
                    entity_type=entity_type,
                    name=str(entity.get("name", ""))[:300],
                    canonical_name=str(entity.get("name", ""))[:300],
                    aliases=entity.get("aliases", []),
                    description=entity.get("description"),
                    extraction_confidence=float(entity.get("extraction_confidence") or 0.5),
                    identification_confidence=(
                        float(entity["identification_confidence"])
                        if entity.get("identification_confidence") is not None
                        else None
                    ),
                    mention_count=int(entity.get("mention_count") or 1),
                    mentions=mentions,
                    earliest_year=entity.get("earliest_year"),
                    latest_year=entity.get("latest_year"),
                    attributes={
                        k: v
                        for k, v in entity.items()
                        if k
                        not in {
                            "name",
                            "entity_type",
                            "aliases",
                            "description",
                            "mentions",
                            "extraction_confidence",
                            "identification_confidence",
                            "mention_count",
                            "earliest_year",
                            "latest_year",
                        }
                    },
                )
            )

    def _persist_report(self, analysis: Analysis, report: dict) -> None:
        version = analysis.version or 1
        existing = next((r for r in analysis.reports if r.version == version), None)
        target = existing or Report(analysis_id=analysis.id, version=version)
        target.executive_summary = report["executive_summary"]
        target.sections = report["sections"]
        target.timeline = report["timeline"]
        target.confidence_summary = report["confidence_summary"]
        target.further_reading = report["further_reading"]
        target.reasoning_trace = report["reasoning_trace"]
        target.word_count = report["word_count"]
        if existing is None:
            # Append through the relationship rather than db.add(): reading
            # `analysis.reports` above loaded and cached the (empty) collection, and a
            # bare add would leave the in-memory object disagreeing with the database
            # until something re-queried it. Callers that hold the Analysis — the job
            # runner, tests, anything not going through the API's re-query — would see
            # no report at all.
            analysis.reports.append(target)
            self.db.add(target)


def run_analysis(
    db: Session, analysis: Analysis, on_progress: ProgressCallback | None = None
) -> Analysis:
    return Orchestrator(db).run(analysis, on_progress=on_progress)


def pipeline_description() -> list[dict[str, Any]]:
    """Machine-readable description of the pipeline, surfaced in the UI and docs."""
    return [
        {
            "name": agent_class.name,
            "description": agent_class.description,
            "critical": agent_class.critical,
            "prompt_version": agent_class.prompt_version,
            "deterministic": agent_class in (CalendarAgent, AstronomyAgent),
            "progress_after": progress,
        }
        for agent_class, progress in PIPELINE
    ]


__all__ = [
    "Orchestrator",
    "run_analysis",
    "pipeline_description",
    "PIPELINE",
    "SECTION_ORDER",
    "SECTION_TITLES",
]
