"use client";

import { claimStyle, confidenceColor } from "@/lib/claims";
import type { ClaimType, ConfidenceSummary } from "@/lib/types";

export function ConfidencePanel({ summary }: { summary: ConfidenceSummary }) {
  const entries = Object.entries(summary.by_type);
  const total = summary.total_claim_count || 1;

  return (
    <div className="mt-4 space-y-5">
      {summary.overall !== null && (
        <div>
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-medium">Overall confidence</span>
            <span className="text-2xl font-semibold tabular-nums">
              {Math.round(summary.overall * 100)}%
            </span>
          </div>
          <div
            className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
            role="img"
            aria-label={`Overall confidence ${Math.round(summary.overall * 100)} percent, ${summary.band}`}
          >
            <div
              className={`h-full ${confidenceColor(summary.overall)}`}
              style={{ width: `${Math.round(summary.overall * 100)}%` }}
            />
          </div>
          <p className="mt-1 text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            {summary.band}
          </p>
        </div>
      )}

      {/* The rationale is the most important thing here: a bare percentage invites a
          reader to treat interpretation as measurement. */}
      <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
        {summary.rationale}
      </p>

      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          What this analysis is made of
        </h3>
        <ul className="mt-3 space-y-2">
          {entries
            .sort(([, a], [, b]) => b.count - a.count)
            .map(([type, info]) => {
              const style = claimStyle(type as ClaimType);
              const share = Math.round((info.count / total) * 100);
              return (
                <li key={type} className="flex items-center gap-3 text-sm">
                  <span className={`badge shrink-0 ${style.badge}`}>
                    <span aria-hidden="true">{style.icon}</span>
                    {style.label}
                  </span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                    <span
                      className={`block h-full ${style.isEvidence ? "bg-green-600" : "bg-slate-400"}`}
                      style={{ width: `${share}%` }}
                    />
                  </span>
                  <span className="w-24 shrink-0 text-right tabular-nums text-slate-600 dark:text-slate-400">
                    {info.count} · {share}%
                  </span>
                </li>
              );
            })}
        </ul>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Green bars are evidence-grade: direct quotation, reproducible calculation, or
          cited history. Grey bars are interpretation and conjecture.
        </p>
      </div>
    </div>
  );
}
