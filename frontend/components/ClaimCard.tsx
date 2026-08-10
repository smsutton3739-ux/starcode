"use client";

import { useState } from "react";
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

  const hasDetail =
    Boolean(claim.reasoning) ||
    Boolean(claim.confidence_basis) ||
    Boolean(claim.engine) ||
    references.length > 0;

  return (
    <article
      className={`rounded-lg border border-l-4 border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 ${style.border}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className={`badge ${style.badge}`} title={style.description}>
          <span aria-hidden="true">{style.icon}</span>
          {style.label}
        </span>

        <span className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
          <span
            className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
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
          <span className="text-xs italic text-slate-500 dark:text-slate-400">
            not evidence
          </span>
        )}
      </div>

      <p className="prose-report mt-3 whitespace-pre-wrap">{claim.statement}</p>

      {claim.quoted_text && claim.claim_type === "source_text" && (
        <blockquote className="mt-3 border-l-2 border-slate-300 pl-4 font-serif text-slate-700 dark:border-slate-600 dark:text-slate-300">
          {claim.quoted_text}
        </blockquote>
      )}

      {hasDetail && (
        <>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="mt-3 text-xs font-medium text-blue-700 underline-offset-4 hover:underline dark:text-blue-400"
          >
            {open ? "Hide the reasoning" : "Why this, and how sure?"}
          </button>

          {open && (
            <div className="mt-3 animate-fade-in space-y-3 rounded-lg bg-slate-50 p-4 text-sm dark:bg-slate-800/60">
              {claim.reasoning && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Reasoning
                  </p>
                  <p className="mt-1 text-slate-700 dark:text-slate-300">{claim.reasoning}</p>
                </div>
              )}

              {claim.confidence_basis && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    What the confidence is based on
                  </p>
                  <p className="mt-1 text-slate-700 dark:text-slate-300">
                    {claim.confidence_basis}
                  </p>
                </div>
              )}

              {claim.engine && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Computed by
                  </p>
                  <p className="mt-1 font-mono text-xs text-slate-700 dark:text-slate-300">
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
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Sources
                  </p>
                  <ul className="mt-1 space-y-1.5">
                    {references.map((reference, index) => (
                      <li key={reference.id ?? index} className="text-slate-700 dark:text-slate-300">
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
                          <span className="ml-2 badge border-orange-300 bg-orange-50 text-orange-900 dark:border-orange-700 dark:bg-orange-950 dark:text-orange-200">
                            unverified — check before citing
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="border-t border-slate-200 pt-2 text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
                Produced by the <span className="font-mono">{claim.produced_by}</span> step.
              </p>
            </div>
          )}
        </>
      )}
    </article>
  );
}
