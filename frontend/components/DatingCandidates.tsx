"use client";

import { useState } from "react";
import { claimStyle, confidenceColor } from "@/lib/claims";
import type { Claim, CriterionOutcome, DateCandidatePayload } from "@/lib/types";

/**
 * Ranked candidate dates from an astronomical dating search.
 *
 * A different shape from the rest of the report on purpose. A claim card presents one
 * statement and how confident the platform is in it; a candidate date is a comparison —
 * these dates, ranked, each meeting some criteria and failing others — and the thing a
 * reader needs is not the top answer but the ability to see why the second one lost.
 * Forcing that into a stack of claim cards would bury the only part that matters.
 *
 * The misses are given the same visual weight as the matches. They are what makes a
 * candidate arguable rather than an assertion with an ephemeris behind it, and the whole
 * feature is worthless if a reader skims past them.
 */

const CRITERION_LABELS: Record<string, string> = {
  eclipse: "Eclipse",
  conjunction: "Conjunction",
  recurrence: "Repeated passes",
  moon_phase: "Moon phase",
  comet: "Comet",
  season: "Season",
  unusual_darkness: "Prolonged darkness",
};

function criterionLabel(key: string): string {
  return CRITERION_LABELS[key] ?? key.replace(/_/g, " ");
}

function isCandidate(claim: Claim): boolean {
  return claim.claim_type === "astronomical_dating_candidate";
}

function payloadOf(claim: Claim): DateCandidatePayload | null {
  const payload = claim.payload as unknown as DateCandidatePayload | undefined;
  return payload && Array.isArray(payload.matched_criteria) ? payload : null;
}

export function DatingCandidates({ claims }: { claims: Claim[] }) {
  const candidates = claims.filter(isCandidate);
  if (candidates.length === 0) return null;

  return (
    <div className="mt-4 space-y-4">
      <p className="text-sm text-ink-600 dark:text-ink-400">
        Ranked by how much of the description each date&rsquo;s real sky satisfies. The sky is
        computed and reproducible; that this text describes it is a proposal, so every
        candidate lists what it failed to match as well as what it met.
      </p>

      <ol className="space-y-3">
        {candidates.map((claim, index) => (
          // Claims embedded in a stored report carry no database id — the report is
          // assembled before they are persisted — so the key falls back to position.
          <CandidateRow
            key={claim.id ?? `candidate-${index}`}
            claim={claim}
            rank={index + 1}
            fallbackId={`candidate-${index}`}
          />
        ))}
      </ol>
    </div>
  );
}

function CandidateRow({
  claim,
  rank,
  fallbackId,
}: {
  claim: Claim;
  rank: number;
  fallbackId: string;
}) {
  const [open, setOpen] = useState(rank === 1);
  const payload = payloadOf(claim);
  const style = claimStyle(claim.claim_type);

  // A locked claim keeps its id, type and ordering but loses its readable content, so
  // there is a row to show and nothing to show in it.
  if (!payload || claim.locked) {
    return (
      <li className={`rounded-lg border border-ink-200 border-l-4 ${style.border} p-4 dark:border-ink-700`}>
        <p className="text-sm text-ink-600 dark:text-ink-400">{claim.statement}</p>
      </li>
    );
  }

  const fit = Math.round(payload.fit * 100);
  const matched = payload.matched_criteria ?? [];
  const unmatched = payload.unmatched_criteria ?? [];
  const detailId = `candidate-detail-${claim.id ?? fallbackId}`;

  return (
    <li
      className={`overflow-hidden rounded-lg border border-ink-200 border-l-4 ${style.border} dark:border-ink-700`}
    >
      <div className="p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
          <h3 className="font-display text-lg">
            <span className="mr-2 tabular-nums text-ink-400 dark:text-ink-500">{rank}.</span>
            {payload.gregorian_label}
            {payload.hour_ut != null && (
              <span className="ml-2 text-sm font-normal text-ink-500 dark:text-ink-400">
                {formatHour(payload.hour_ut)} UT
              </span>
            )}
          </h3>

          <div className="flex items-center gap-2">
            <span className="badge border-ink-300 bg-ink-50 text-ink-700 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-300">
              <span aria-hidden="true">{style.icon}</span>
              {style.label}
            </span>
            <span className="text-sm tabular-nums text-ink-600 dark:text-ink-400">
              {matched.length} of {matched.length + unmatched.length} criteria
            </span>
          </div>
        </div>

        {/* Fit is a bar and a percentage and a sentence — never colour alone. */}
        <div className="mt-3">
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-ink-200 dark:bg-ink-700"
            role="img"
            aria-label={`Fit ${fit} per cent: matches ${matched.length} of ${
              matched.length + unmatched.length
            } criteria`}
          >
            <div
              className={`h-full rounded-full ${confidenceColor(payload.fit)}`}
              style={{ width: `${fit}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-ink-500 dark:text-ink-400">
            Fit {fit}%
            {payload.recurrences >= 3 &&
              ` · the configuration recurs ${payload.recurrences} times this year`}
          </p>
        </div>

        {payload.framework && (
          <p className="mt-3 rounded border border-gold-300 bg-gold-50 p-2 text-xs text-gold-900 dark:border-gold-700 dark:bg-gold-950 dark:text-gold-200">
            Produced by {payload.framework}. This is what applying that method yields. It is not
            a statement that the text refers to this date, and not a prediction.
          </p>
        )}

        <CriterionList outcomes={matched} matched />
        <CriterionList outcomes={unmatched} matched={false} />

        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={detailId}
          className="mt-3 text-sm text-lapis-700 underline-offset-4 hover:underline dark:text-lapis-300"
        >
          {open ? "Hide the detail" : "What this rests on"}
        </button>
      </div>

      <div
        id={detailId}
        hidden={!open}
        className="border-t border-ink-200 bg-ink-50 p-4 text-sm dark:border-ink-700 dark:bg-ink-900/60"
      >
        <dl className="space-y-3">
          {[...matched, ...unmatched].map((outcome) => (
            <div key={outcome.criterion}>
              <dt className="font-medium">
                {criterionLabel(outcome.criterion)}{" "}
                <span className="font-normal text-ink-500 dark:text-ink-400">
                  {outcome.matched ? "(matched)" : outcome.searchable ? "(not matched)" : "(not checkable)"}
                </span>
              </dt>
              <dd className="text-ink-700 dark:text-ink-300">{outcome.detail}</dd>
            </div>
          ))}
        </dl>

        {payload.notes.length > 0 && (
          <ul className="mt-4 space-y-2 border-t border-ink-200 pt-3 text-ink-600 dark:border-ink-700 dark:text-ink-400">
            {payload.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        )}

        {payload.uncertainty_note && (
          <p className="mt-4 border-t border-ink-200 pt-3 text-xs text-ink-600 dark:border-ink-700 dark:text-ink-400">
            {payload.uncertainty_note}
          </p>
        )}
      </div>
    </li>
  );
}

function CriterionList({
  outcomes,
  matched,
}: {
  outcomes: CriterionOutcome[];
  matched: boolean;
}) {
  if (outcomes.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-ink-500 dark:text-ink-400">
        {matched ? "Matched" : "Not matched"}
      </span>
      {outcomes.map((outcome) => (
        <span
          key={outcome.criterion}
          title={outcome.detail}
          className={`badge ${
            matched
              ? "border-verdigris-300 bg-verdigris-50 text-verdigris-900 dark:border-verdigris-700 dark:bg-verdigris-950 dark:text-verdigris-200"
              : "border-ink-300 bg-ink-50 text-ink-600 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-400"
          }`}
        >
          {/* A glyph as well as the colour: the a11y suite strips colour entirely. */}
          <span aria-hidden="true">{matched ? "✓" : outcome.searchable ? "✕" : "—"}</span>
          {criterionLabel(outcome.criterion)}
        </span>
      ))}
    </div>
  );
}

function formatHour(hourUt: number): string {
  const hours = Math.floor(hourUt);
  const minutes = Math.round((hourUt - hours) * 60);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}
