"use client";

import { useState } from "react";
import Link from "next/link";
import { claimStyle, confidenceBand, confidenceColor } from "@/lib/claims";
import type { Claim } from "@/lib/types";

/**
 * One claim.
 *
 * The claim type badge is always visible and never optional. Reasoning, provenance and
 * citations sit behind a disclosure, because most readers want the statement and its
 * label; the ones who want to check the working can open it.
 */
export function ClaimCard({ claim }: { claim: Claim }) {
  const [open, setOpen] = useState(false);
  const style = claimStyle(claim.claim_type);

  // Claims reach this component from two places — the API's ClaimOut and the claim
  // dicts embedded in a stored report — so the array is read defensively. A missing
  // citation list should render an empty section, never white-screen the report.
  const references = claim.references ?? [];

  // A withheld claim keeps its type, confidence and citations — only the readable
  // fields were replaced — so it renders as a real card with the content masked rather
  // than disappearing. A shorter report would misrepresent what the analysis found.
  const locked = claim.locked === true;

  // Locked claims keep their citations, and the inner sections already guard on the
  // fields that were cleared, so the disclosure opens onto the sources alone.
  const hasDetail =
    Boolean(claim.reasoning) ||
    Boolean(claim.confidence_basis) ||
    Boolean(claim.engine) ||
    references.length > 0;

  return (
    <article
      className={`rounded-lg border border-l-4 border-ink-200 bg-ink-50 p-4 dark:border-ink-800 dark:bg-ink-900 ${style.border}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className={`badge ${style.badge}`} title={style.description}>
          <span aria-hidden="true">{style.icon}</span>
          {style.label}
        </span>

        <span className="flex items-center gap-1.5 text-xs text-ink-500 dark:text-ink-400">
          <span
            className="h-1.5 w-16 overflow-hidden rounded-full bg-ink-200 dark:bg-ink-700"
            role="img"
            aria-label={`Confidence ${Math.round(claim.confidence * 100)} percent, ${confidenceBand(claim.confidence)}`}
          >
            <span
              className={`block h-full ${confidenceColor(claim.confidence)}`}
              style={{ width: `${Math.round(claim.confidence * 100)}%` }}
            />
          </span>
          {Math.round(claim.confidence * 100)}% · {confidenceBand(claim.confidence)}
        </span>

        {!style.isEvidence && (
          <span className="text-xs italic text-ink-500 dark:text-ink-400">
            not evidence
          </span>
        )}
      </div>

      {locked ? (
        <div className="mt-3 rounded-lg border border-dashed border-gold-400 bg-gold-50/60 p-4 dark:border-gold-600 dark:bg-gold-950/30">
          <p className="flex items-center gap-2 font-display text-sm text-gold-900 dark:text-gold-200">
            {/* Icon and text together: the accessibility suite checks that meaning
                survives with colour stripped out, so the lock is never the only signal. */}
            <span aria-hidden="true">🔒</span>
            <span className="font-semibold">Interpretation locked</span>
          </p>
          <p className="mt-2 text-sm text-ink-700 dark:text-ink-300">
            This {style.label.toLowerCase()} was produced by the analysis and is included
            in your report — the text is held back on the free plan.
            {references.length > 0 && (
              <>
                {" "}
                It cites {references.length}{" "}
                {references.length === 1 ? "source" : "sources"}, listed below.
              </>
            )}
          </p>
          <Link
            href="/pricing"
            className="mt-3 inline-block rounded-md bg-lapis-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-lapis-700 dark:bg-lapis-500 dark:hover:bg-lapis-400"
          >
            Unlock interpretations
          </Link>
        </div>
      ) : (
        <p className="prose-report mt-3 whitespace-pre-wrap">{claim.statement}</p>
      )}

      {!locked && claim.quoted_text && claim.claim_type === "source_text" && (
        <blockquote className="mt-3 border-l-2 border-ink-300 pl-4 font-serif text-ink-700 dark:border-ink-600 dark:text-ink-300">
          {claim.quoted_text}
        </blockquote>
      )}

      {hasDetail && (
        <>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="mt-3 text-xs font-medium text-lapis-700 underline-offset-4 hover:underline dark:text-lapis-400"
          >
            {open ? "Hide the reasoning" : "Why this, and how sure?"}
          </button>

          {open && (
            <div className="mt-3 animate-fade-in space-y-3 rounded-lg bg-ink-50 p-4 text-sm dark:bg-ink-800/60">
              {claim.reasoning && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">
                    Reasoning
                  </p>
                  <p className="mt-1 text-ink-700 dark:text-ink-300">{claim.reasoning}</p>
                </div>
              )}

              {claim.confidence_basis && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">
                    What the confidence is based on
                  </p>
                  <p className="mt-1 text-ink-700 dark:text-ink-300">
                    {claim.confidence_basis}
                  </p>
                </div>
              )}

              {claim.engine && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">
                    Computed by
                  </p>
                  <p className="mt-1 font-mono text-xs text-ink-700 dark:text-ink-300">
                    {claim.engine}
                    {claim.algorithm_reference && (
                      <span className="block font-sans not-italic">
                        {claim.algorithm_reference}
                      </span>
                    )}
                  </p>
                </div>
              )}

              {references.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">
                    Sources
                  </p>
                  <ul className="mt-1 space-y-1.5">
                    {references.map((reference, index) => (
                      <li key={reference.id ?? index} className="text-ink-700 dark:text-ink-300">
                        {reference.url ? (
                          <a
                            href={reference.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline underline-offset-2"
                          >
                            {reference.citation_text}
                          </a>
                        ) : (
                          reference.citation_text
                        )}
                        {!reference.verified && (
                          // A model-supplied citation must never look like a checked one.
                          <span className="ml-2 badge border-terra-300 bg-terra-50 text-terra-900 dark:border-terra-700 dark:bg-terra-950 dark:text-terra-200">
                            unverified — check before citing
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="border-t border-ink-200 pt-2 text-xs text-ink-500 dark:border-ink-700 dark:text-ink-400">
                Produced by the <span className="font-mono">{claim.produced_by}</span> step.
              </p>
            </div>
          )}
        </>
      )}
    </article>
  );
}
