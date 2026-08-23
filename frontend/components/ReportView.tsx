"use client";

import { useMemo, useState } from "react";
import { ClaimCard } from "./ClaimCard";
import { Timeline } from "./Timeline";
import { EntityTable } from "./EntityTable";
import { ConfidencePanel } from "./ConfidencePanel";
import { ReasoningTrace } from "./ReasoningTrace";
import { claimStyle } from "@/lib/claims";
import type { AnalysisDetail, ClaimType, ReportSection } from "@/lib/types";

const ALL_TYPES: ClaimType[] = [
  "source_text",
  "verified_history",
  "astronomical_calculation",
  "textual_analysis",
  "traditional_interpretation",
  "scholarly_interpretation",
  "ai_hypothesis",
  "uncertain",
];

export function ReportView({ analysis }: { analysis: AnalysisDetail }) {
  const report = analysis.report;
  const [hidden, setHidden] = useState<Set<ClaimType>>(new Set());
  const [evidenceOnly, setEvidenceOnly] = useState(false);

  const visibleTypes = useMemo(() => {
    if (evidenceOnly) {
      return new Set<ClaimType>(
        ALL_TYPES.filter((type) => claimStyle(type).isEvidence),
      );
    }
    return new Set<ClaimType>(ALL_TYPES.filter((type) => !hidden.has(type)));
  }, [evidenceOnly, hidden]);

  const presentTypes = useMemo(() => {
    const counts = new Map<ClaimType, number>();
    analysis.claims.forEach((claim) => {
      counts.set(claim.claim_type, (counts.get(claim.claim_type) ?? 0) + 1);
    });
    return counts;
  }, [analysis.claims]);

  if (!report) {
    return (
      <div className="card p-6">
        <p>No report was produced for this analysis.</p>
        {analysis.error_message && (
          <p className="mt-2 text-sm text-crimson-700 dark:text-crimson-400">
            {analysis.error_message}
          </p>
        )}
      </div>
    );
  }

  const sections = report.sections.filter(
    (section) => section.key !== "executive_summary",
  );

  return (
    <div className="space-y-8">
      <ExecutiveSummary analysis={analysis} />

      {/* The filter is a reading aid, not a way to make the report say something it
          does not: "evidence only" narrows to verifiable claims and says so plainly. */}
      <div className="no-print card sticky top-16 z-20 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium">Show</span>
          <button
            type="button"
            onClick={() => {
              setEvidenceOnly((value) => !value);
              setHidden(new Set());
            }}
            aria-pressed={evidenceOnly}
            className={`badge ${
              evidenceOnly
                ? "border-lapis-500 bg-lapis-100 text-lapis-900 dark:bg-lapis-900 dark:text-lapis-100"
                : "border-ink-300 bg-ink-50 text-ink-700 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-300"
            }`}
          >
            Evidence only
          </button>

          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by claim type">
            {ALL_TYPES.filter((type) => presentTypes.has(type)).map((type) => {
              const style = claimStyle(type);
              const active = visibleTypes.has(type);
              return (
                <button
                  key={type}
                  type="button"
                  disabled={evidenceOnly}
                  aria-pressed={active}
                  onClick={() =>
                    setHidden((current) => {
                      const next = new Set(current);
                      if (next.has(type)) next.delete(type);
                      else next.add(type);
                      return next;
                    })
                  }
                  title={style.description}
                  className={`badge transition-opacity ${style.badge} ${
                    active ? "" : "opacity-35"
                  } ${evidenceOnly ? "cursor-not-allowed" : ""}`}
                >
                  <span aria-hidden="true">{style.icon}</span>
                  {style.label}
                  <span className="ml-1 tabular-nums opacity-70">
                    {presentTypes.get(type)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        {evidenceOnly && (
          <p className="mt-3 text-xs text-ink-600 dark:text-ink-400">
            Showing only quotations, calculations and cited history. Interpretations and
            hypotheses are hidden — they are still part of the analysis.
          </p>
        )}
      </div>

      {sections.map((section) => (
        <SectionBlock
          key={section.key}
          section={section}
          analysis={analysis}
          visibleTypes={visibleTypes}
        />
      ))}

      <ReasoningTrace steps={report.reasoning_trace} />
    </div>
  );
}

function ExecutiveSummary({ analysis }: { analysis: AnalysisDetail }) {
  const report = analysis.report!;
  return (
    <section className="card p-6" aria-labelledby="section-executive-summary">
      <h2 id="section-executive-summary" className="text-xl font-semibold">
        Executive Summary
      </h2>
      <p className="prose-report mt-3">{report.executive_summary}</p>

      {analysis.failed_stages.length > 0 && (
        <div className="mt-4 rounded-lg border border-gold-300 bg-gold-50 p-3 text-sm text-gold-900 dark:border-gold-700 dark:bg-gold-950 dark:text-gold-200">
          <strong>Incomplete:</strong> these stages did not finish, and their sections are
          empty rather than guessed: {analysis.failed_stages.join(", ")}.
        </div>
      )}
    </section>
  );
}

function SectionBlock({
  section,
  analysis,
  visibleTypes,
}: {
  section: ReportSection;
  analysis: AnalysisDetail;
  visibleTypes: Set<ClaimType>;
}) {
  const claims = section.claims.filter((claim) => visibleTypes.has(claim.claim_type));
  const data = (section.data ?? {}) as Record<string, unknown>;
  const anchor = `section-${section.key}`;

  const hasStructuredContent =
    section.key === "timeline" ||
    section.key === "key_entities" ||
    section.key === "confidence_ratings" ||
    section.key === "references" ||
    section.key === "further_reading";

  if (section.is_empty && !hasStructuredContent) {
    return (
      <section className="card p-6" aria-labelledby={anchor}>
        <h2 id={anchor} className="text-xl font-semibold">
          {section.title}
        </h2>
        <p className="mt-2 text-sm italic text-ink-500 dark:text-ink-400">
          {section.empty_reason ?? "Nothing was produced for this section."}
        </p>
      </section>
    );
  }

  return (
    <section className="card p-6" aria-labelledby={anchor}>
      <h2 id={anchor} className="text-xl font-semibold">
        {section.title}
      </h2>

      {section.key === "timeline" && (
        <Timeline events={analysis.report?.timeline ?? []} />
      )}

      {section.key === "key_entities" && <EntityTable entities={analysis.entities} />}

      {section.key === "confidence_ratings" && analysis.report && (
        <ConfidencePanel summary={analysis.report.confidence_summary} />
      )}

      {section.key === "references" && (
        <ReferenceList references={(data.references as ReferenceItem[]) ?? []} />
      )}

      {section.key === "further_reading" && (
        <FurtherReading items={(data.items as FurtherReadingItem[]) ?? []} />
      )}

      {claims.length > 0 && (
        <div className="mt-4 space-y-3">
          {claims.map((claim, index) => (
            // Claims embedded in a stored report have no database id yet — the report is
            // assembled before they are persisted — so the key is positional. The array
            // is fixed for a given report version, so this is stable.
            <ClaimCard key={claim.id ?? `${section.key}-${index}`} claim={claim} />
          ))}
        </div>
      )}

      {claims.length === 0 && section.claim_count > 0 && (
        <p className="mt-3 text-sm italic text-ink-500 dark:text-ink-400">
          {section.claim_count} finding{section.claim_count === 1 ? "" : "s"} in this
          section are hidden by the current filter.
        </p>
      )}
    </section>
  );
}

interface ReferenceItem {
  citation_text: string;
  url?: string | null;
  verified: boolean;
  supports_claim?: string;
}

function ReferenceList({ references }: { references: ReferenceItem[] }) {
  if (references.length === 0) {
    return (
      <p className="mt-2 text-sm italic text-ink-500 dark:text-ink-400">
        No citations were produced for this analysis.
      </p>
    );
  }

  const verified = references.filter((reference) => reference.verified);
  const unverified = references.filter((reference) => !reference.verified);

  return (
    <div className="mt-4 space-y-5">
      {verified.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">
            From the reference corpus
          </h3>
          <ul className="mt-2 space-y-2 text-sm">
            {verified.map((reference, index) => (
              <li key={index} className="text-ink-700 dark:text-ink-300">
                {reference.citation_text}
              </li>
            ))}
          </ul>
        </div>
      )}

      {unverified.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-terra-700 dark:text-terra-400">
            Unverified — check before citing
          </h3>
          <p className="mt-1 text-xs text-ink-600 dark:text-ink-400">
            These came from the language model rather than the curated corpus. Language
            models invent plausible-looking references, so confirm each one exists before
            relying on it.
          </p>
          <ul className="mt-2 space-y-2 text-sm">
            {unverified.map((reference, index) => (
              <li key={index} className="text-ink-700 dark:text-ink-300">
                {reference.citation_text}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

interface FurtherReadingItem {
  title: string;
  citation: string;
  why: string;
  source: string;
}

function FurtherReading({ items }: { items: FurtherReadingItem[] }) {
  if (items.length === 0) {
    return (
      <p className="mt-2 text-sm italic text-ink-500 dark:text-ink-400">
        No further reading was suggested.
      </p>
    );
  }
  return (
    <ul className="mt-4 space-y-4">
      {items.map((item, index) => (
        <li key={index}>
          <p className="font-medium">{item.title}</p>
          <p className="text-sm text-ink-600 dark:text-ink-400">{item.citation}</p>
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">{item.why}</p>
        </li>
      ))}
    </ul>
  );
}
