"use client";

import type { AnalysisStatusResponse } from "@/lib/types";

/**
 * Shown while an analysis runs.
 *
 * Named stages rather than a bare spinner: a user who can see "converting dates between
 * calendars" understands both that work is happening and what kind. The stage labels are
 * the backend's, so they never drift from what is actually running.
 */
const STAGES = [
  { key: "language", label: "Detecting language" },
  { key: "source_identification", label: "Identifying the source" },
  { key: "entities", label: "Extracting people, places and symbols" },
  { key: "calendar", label: "Converting dates between calendars" },
  { key: "astronomy", label: "Checking the sky for those dates" },
  { key: "historical_context", label: "Establishing historical context" },
  { key: "interpretation", label: "Gathering interpretations" },
  { key: "evidence", label: "Weighing the evidence" },
];

export function ProgressPanel({ status }: { status: AnalysisStatusResponse | null }) {
  const progress = Math.round((status?.progress ?? 0) * 100);
  const currentIndex = STAGES.findIndex((stage) => stage.key === status?.current_stage);

  return (
    <div className="card p-8 text-center">
      <div
        className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600 dark:border-slate-700 dark:border-t-blue-400"
        aria-hidden="true"
      />

      <h1 className="mt-6 text-xl font-semibold">Analysing your text</h1>
      <p className="mt-2 text-slate-600 dark:text-slate-400" aria-live="polite">
        {status?.stage_label ?? "Getting started…"}
      </p>

      <div
        className="mt-6 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Analysis progress"
      >
        <div
          className="h-full bg-blue-600 transition-[width] duration-500 ease-out dark:bg-blue-500"
          style={{ width: `${Math.max(progress, 3)}%` }}
        />
      </div>
      <p className="mt-2 text-sm tabular-nums text-slate-500 dark:text-slate-400">
        {progress}%
      </p>

      <ol className="mx-auto mt-8 max-w-sm space-y-2 text-left text-sm">
        {STAGES.map((stage, index) => {
          const done = currentIndex > index || status?.status === "completed";
          const active = currentIndex === index;
          return (
            <li
              key={stage.key}
              className={`flex items-center gap-3 rounded-lg px-3 py-1.5 ${
                active ? "bg-blue-50 dark:bg-blue-950" : ""
              }`}
            >
              <span
                aria-hidden="true"
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs ${
                  done
                    ? "bg-green-600 text-white"
                    : active
                      ? "bg-blue-600 text-white"
                      : "bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400"
                }`}
              >
                {done ? "✓" : index + 1}
              </span>
              <span
                className={
                  done
                    ? "text-slate-500 dark:text-slate-400"
                    : active
                      ? "font-medium"
                      : "text-slate-400 dark:text-slate-500"
                }
              >
                {stage.label}
              </span>
            </li>
          );
        })}
      </ol>

      <p className="mt-8 text-xs text-slate-500 dark:text-slate-400">
        This usually takes under a minute. You can leave this page open — it will update
        on its own.
      </p>
    </div>
  );
}
