"""Base class for specialist agents: prompting, retries, tracing and contract enforcement."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.agents.contracts import AgentResult, ClaimDraft, coerce_claim
from app.agents.provider import LLMProvider, LLMResponse, ProviderError, get_provider
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AnalysisContext:
    """Everything an agent may read. Agents write only to their own :class:`AgentResult`,
    and the orchestrator merges — so one agent cannot corrupt another's findings."""

    analysis_id: str
    text: str
    normalized_text: str
    db: Session
    options: dict[str, Any] = field(default_factory=dict)
    title: str | None = None
    source_kind: str = "pasted_text"

    # Progressively filled by earlier agents.
    language: dict[str, Any] = field(default_factory=dict)
    translation: dict[str, Any] = field(default_factory=dict)
    source_identification: dict[str, Any] = field(default_factory=dict)
    entities: list[dict] = field(default_factory=list)
    dates: dict[str, Any] = field(default_factory=dict)
    astronomy: dict[str, Any] = field(default_factory=dict)
    calendar: dict[str, Any] = field(default_factory=dict)
    retrieved: list[dict] = field(default_factory=list)
    history: dict[str, Any] = field(default_factory=dict)

    @property
    def working_text(self) -> str:
        """The English text agents reason over: the translation if one was produced,
        otherwise the original."""
        translated = self.translation.get("translated_text")
        return translated if translated else self.text

    def excerpt(self, limit: int = 12000) -> str:
        """Bounded text for prompting. Long manuscripts are truncated from the middle so
        that the opening and the closing — where dating formulae and colophons live —
        both survive."""
        text = self.working_text
        if len(text) <= limit:
            return text
        head = limit * 2 // 3
        tail = limit - head
        return (
            f"{text[:head]}\n\n[... {len(text) - limit:,} characters omitted from the "
            f"middle of the text ...]\n\n{text[-tail:]}"
        )


class BaseAgent(ABC):
    """One specialist step of the analysis."""

    name: str = "agent"
    description: str = ""
    prompt_version: str = "1.0.0"
    #: Whether a failure here should fail the whole analysis. Almost never true: a
    #: missing section is far better than no report.
    critical: bool = False
    max_tokens: int = 4000
    temperature: float = 0.2

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    @property
    def provider(self) -> LLMProvider:
        return self._provider or get_provider()

    # ---- to implement -------------------------------------------------------

    @abstractmethod
    def run(self, ctx: AnalysisContext) -> AgentResult:
        """Do the work. Exceptions are caught by :meth:`execute`."""

    # ---- shared machinery ---------------------------------------------------

    def execute(self, ctx: AnalysisContext) -> AgentResult:
        """Run with timing, retries and contract enforcement."""
        start = time.perf_counter()
        attempts = 0
        last_error: Exception | None = None

        while attempts < settings.AI_MAX_RETRIES:
            attempts += 1
            try:
                result = self.run(ctx)
                result.agent_name = self.name
                result.attempts = attempts
                result.duration_ms = int((time.perf_counter() - start) * 1000)
                result.provider = result.provider or self.provider.name
                result.model = result.model or self.provider.model
                # The mode comes from the analysis's own options, not from anything the
                # agent set on itself, so an agent running under a restricted dating mode
                # cannot opt out of that mode's restrictions.
                mode = ctx.options.get("mode")
                result.claims = [
                    coerce_claim(c, mode=mode if isinstance(mode, str) else None)
                    for c in result.claims
                ]
                logger.info(
                    "agent.completed",
                    agent=self.name,
                    attempts=attempts,
                    claims=len(result.claims),
                    entities=len(result.entities),
                    duration_ms=result.duration_ms,
                )
                return result
            except ProviderError as exc:
                # Transient. The provider has already exhausted its own retries, so an
                # agent-level retry only helps for genuinely intermittent failures.
                last_error = exc
                logger.warning(
                    "agent.provider_error", agent=self.name, attempt=attempts, error=str(exc)
                )
                time.sleep(min(2**attempts, 8))
            except Exception as exc:  # noqa: BLE001 - one agent must not take down the run
                last_error = exc
                logger.exception("agent.failed", agent=self.name, attempt=attempts)
                break  # deterministic failures do not improve on retry

        duration = int((time.perf_counter() - start) * 1000)
        logger.error("agent.gave_up", agent=self.name, attempts=attempts, error=str(last_error))
        return AgentResult(
            agent_name=self.name,
            status="failed",
            error=str(last_error) if last_error else "unknown error",
            duration_ms=duration,
            attempts=attempts,
            provider=self.provider.name,
            model=self.provider.model,
            reasoning_summary=(
                f"The {self.description or self.name} step did not complete. Its section is "
                "reported as unavailable; nothing has been guessed to fill the gap."
            ),
        )

    def ask(
        self,
        system: str,
        prompt: str,
        *,
        expect_json: bool = True,
        prefill: str | None = None,
    ) -> tuple[Any, LLMResponse]:
        """Call the provider and parse the reply."""
        response = self.provider.complete(
            system,
            prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            prefill=prefill or ("{" if expect_json else None),
        )
        if not expect_json:
            return response.text, response
        return response.json(), response

    @staticmethod
    def unavailable(data: Any) -> bool:
        """True when the offline engine declined the task."""
        return isinstance(data, dict) and data.get("offline_unavailable") is True

    def offline_result(self, data: dict, section_note: str) -> AgentResult:
        """Uniform result for a declined offline task."""
        return AgentResult(
            agent_name=self.name,
            status="skipped",
            reasoning_summary=(
                f"{section_note} {data.get('reason', '')} {data.get('note', '')}".strip()
            ),
            data={"unavailable": True, "reason": data.get("reason")},
        )

    def make_claim(self, **kwargs: Any) -> ClaimDraft:
        kwargs.setdefault("produced_by", self.name)
        return ClaimDraft(**kwargs)


SHARED_SYSTEM_RULES = """\
You are a specialist analyst inside Starcode, a platform for analysing ancient texts, \
historical documents, astronomical references and traditional prophecies.

The platform's central rule, which overrides every other instruction:

  NEVER PRESENT SPECULATION AS ESTABLISHED FACT.

Every statement you make is stored with an explicit type, and the interface renders each \
type differently. Choose the type honestly:

  verified_history          - attested in the historical record. REQUIRES a real citation.
  astronomical_calculation  - produced by a calculation. Only use when given the numbers.
  textual_analysis          - an observation about the text itself.
  traditional_interpretation- what a tradition has held. Name the tradition.
  scholarly_interpretation  - a position argued in academic literature. REQUIRES a citation.
  ai_hypothesis             - your own conjecture. Use this when in any doubt.
  uncertain                 - genuinely undetermined.

Rules you must follow:

1. Do not invent citations. A fabricated reference that looks real is the single most \
damaging thing you can produce here. If you cannot cite a specific work you are confident \
exists, use ai_hypothesis and say so plainly. An honest "I cannot source this" is a \
correct answer.
2. Where scholars disagree, report the disagreement and who holds which position. Do not \
resolve it.
3. Distinguish what a text SAYS from what it has been TAKEN to mean. These are different \
claims with different evidence.
4. Never state that a future event will happen. Prophetic material may be described, and \
interpretations attributed, but a prediction is never a fact.
5. Give confidence as a number in [0, 1] and say what it is based on.
6. Respect the beliefs the text belongs to. Describe traditions accurately and without \
either endorsement or mockery.
7. Reply with JSON only, matching the requested shape exactly. No prose outside the JSON.

The rules above govern what you may claim. The rules below govern how the prose reads. \
They matter less than the seven above: a fabricated citation is a serious failure, an \
awkward sentence is not. Never bend rules 1 to 7 to satisfy these.

Apply them to every piece of free text you write, including interpretation and symbolism \
narrative, historical context, notes, and reasoning_summary:

8. Do not use em dashes or en dashes as punctuation. Use a comma, a full stop, a colon \
or brackets. (A dash inside a quoted source, a date range or a numeric value stays as it \
is: it is data, not punctuation.)
9. Do not use the "not X, it is Y" or "not just X, but Y" shape to build emphasis. Say \
the thing you mean and stop. This bans the rhetorical flourish, not the plain negative: \
"this is a proposal, not a finding" is exactly the kind of sentence rules 1 to 4 require, \
and you should keep writing it.
10. Avoid the vocabulary of generated filler: delve, tapestry, underscore, boasts, \
navigate the complexities, in the realm of, it is worth noting, testament to. Do not \
open a sentence with Furthermore or Moreover.
11. Vary sentence length and construction. Do not fall into a three-item list as the \
rhythm of every paragraph, and do not open consecutive sentences with the same word. A \
short blunt sentence after a long one is good writing; a page of identically shaped ones \
is not.
12. Write as a careful specialist writing for another specialist. State the finding, \
state the evidence, state the doubt. Do not pad, do not announce what you are about to \
say, and do not summarise what you just said.
"""


__all__ = ["AnalysisContext", "BaseAgent", "SHARED_SYSTEM_RULES"]
