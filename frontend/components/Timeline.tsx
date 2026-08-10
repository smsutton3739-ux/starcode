"use client";

import { formatYear } from "@/lib/claims";
import type { TimelineEvent } from "@/lib/types";

const KIND_STYLE: Record<string, { dot: string; label: string }> = {
  calendar_conversion: { dot: "bg-blue-600", label: "Date in the text" },
  astronomical_event: { dot: "bg-indigo-600", label: "Computed event" },
  historical_event: { dot: "bg-green-600", label: "Historical event" },
  entity_span: { dot: "bg-slate-400", label: "Entity date range" },
};

const CERTAINTY_NOTE: Record<string, string> = {
  calculated: "Computed, not inferred.",
  attested: "Attested in the historical record.",
  approximate: "Approximate — a conventional range, not a fixed date.",
  disputed: "Disputed among scholars.",
};

export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="mt-2 text-sm italic text-slate-500 dark:text-slate-400">
        No datable events were established, so no timeline could be built.
      </p>
    );
  }

  const years = events.map((event) => event.year);
  const span = { min: Math.min(...years), max: Math.max(...years) };

  return (
    <div className="mt-4">
      <p className="text-sm text-slate-600 dark:text-slate-400">
        {events.length} event{events.length === 1 ? "" : "s"} spanning{" "}
        {formatYear(span.min)} to {formatYear(span.max)}. Each entry says how firm its
        date is.
      </p>

      <ol className="relative mt-5 space-y-5 border-l-2 border-slate-200 pl-6 dark:border-slate-700">
        {events.map((event, index) => {
          const style = KIND_STYLE[event.kind] ?? { dot: "bg-slate-500", label: event.kind };
          return (
            <li key={`${event.year}-${index}`} className="relative">
              <span
                className={`absolute -left-[1.72rem] top-1.5 h-3 w-3 rounded-full ring-2 ring-white dark:ring-slate-900 ${style.dot}`}
                aria-hidden="true"
              />
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="font-mono text-sm font-semibold tabular-nums">
                  {event.label}
                </span>
                <span className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  {style.label}
                </span>
                <span className="badge border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {event.certainty}
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">
                {event.description}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                {CERTAINTY_NOTE[event.certainty] ?? ""}
                {event.note ? ` ${event.note}` : ""}
              </p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
