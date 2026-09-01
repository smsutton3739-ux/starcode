"use client";

import { useState } from "react";
import { formatDuration } from "@/lib/claims";
import type { TraceStep } from "@/lib/types";

const STATUS_STYLE: Record<string, string> = {
  succeeded: "border-verdigris-300 bg-verdigris-50 text-verdigris-900 dark:border-verdigris-700 dark:bg-verdigris-950 dark:text-verdigris-200",
  skipped: "border-ink-300 bg-ink-50 text-ink-700 dark:border-ink-600 dark:bg-ink-800 dark:text-ink-300",
  failed: "border-crimson-300 bg-crimson-50 text-crimson-900 dark:border-crimson-700 dark:bg-crimson-950 dark:text-crimson-200",
};

/**
 * The explainability panel. Every conclusion in the report traces back to a step here,
 * with the model and prompt version that produced it.
 */
export function ReasoningTrace({ steps }: { steps: TraceStep[] }) {
  const [open, setOpen] = useState(false);
  if (steps.length === 0) return null;

  return (
    <section className="card p-6" aria-labelledby="section-trace">
      <div className="flex items-center justify-between gap-4">
        <h2 id="section-trace" className="text-xl font-semibold">
          How this report was produced
        </h2>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="btn-secondary text-sm no-print"
        >
          {open ? "Hide" : "Show"} the {steps.length} steps
        </button>
      </div>

      <p className="mt-2 text-sm text-ink-600 dark:text-ink-400">
        Each step is a specialist agent. The calendar and astronomy steps consult no
        language model at all. Their output is arithmetic.
      </p>

      {open && (
        <ol className="mt-4 animate-fade-in space-y-3">
          {steps.map((step) => (
            <li
              key={step.step}
              className="rounded-lg border border-ink-200 p-4 dark:border-ink-800"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-ink-500 dark:text-ink-400">
                  {step.step}.
                </span>
                <span className="font-medium">{step.agent.replace(/_/g, " ")}</span>
                <span className={`badge ${STATUS_STYLE[step.status] ?? STATUS_STYLE.skipped}`}>
                  {step.status}
                </span>
                <span className="ml-auto text-xs tabular-nums text-ink-500 dark:text-ink-400">
                  {formatDuration(step.duration_ms)}
                  {step.claims_produced > 0 && ` · ${step.claims_produced} findings`}
                </span>
              </div>
              <p className="mt-2 text-sm text-ink-700 dark:text-ink-300">
                {step.reasoning}
              </p>
              {step.error && (
                <p className="mt-2 text-sm text-crimson-700 dark:text-crimson-400">{step.error}</p>
              )}
              {step.model && (
                <p className="mt-2 font-mono text-xs text-ink-500 dark:text-ink-400">
                  {step.provider} · {step.model}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
