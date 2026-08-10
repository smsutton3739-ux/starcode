"use client";

import { useMemo, useState } from "react";
import { entityTypeLabel, formatYear } from "@/lib/claims";
import type { Entity } from "@/lib/types";

export function EntityTable({ entities }: { entities: Entity[] }) {
  const [filter, setFilter] = useState<string>("all");

  const grouped = useMemo(() => {
    const groups = new Map<string, Entity[]>();
    entities.forEach((entity) => {
      const list = groups.get(entity.entity_type) ?? [];
      list.push(entity);
      groups.set(entity.entity_type, list);
    });
    return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [entities]);

  if (entities.length === 0) {
    return (
      <p className="mt-2 text-sm italic text-slate-500 dark:text-slate-400">
        No entities were extracted from this text.
      </p>
    );
  }

  const visible = filter === "all" ? grouped : grouped.filter(([type]) => type === filter);

  return (
    <div className="mt-4">
      <div className="no-print flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => setFilter("all")}
          aria-pressed={filter === "all"}
          className={`badge ${
            filter === "all"
              ? "border-blue-500 bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-100"
              : "border-slate-300 bg-white text-slate-600 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
          }`}
        >
          All {entities.length}
        </button>
        {grouped.map(([type, list]) => (
          <button
            key={type}
            type="button"
            onClick={() => setFilter(type)}
            aria-pressed={filter === type}
            className={`badge ${
              filter === type
                ? "border-blue-500 bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-100"
                : "border-slate-300 bg-white text-slate-600 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
            }`}
          >
            {entityTypeLabel(type)} {list.length}
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-6">
        {visible.map(([type, list]) => (
          <div key={type}>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {entityTypeLabel(type)}
            </h3>
            <ul className="mt-2 divide-y divide-slate-200 dark:divide-slate-800">
              {list
                .sort((a, b) => b.mention_count - a.mention_count)
                .map((entity) => (
                  <li key={entity.id} className="py-3">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="font-medium">{entity.name}</span>
                      {entity.mention_count > 1 && (
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          mentioned {entity.mention_count} times
                        </span>
                      )}
                      {entity.earliest_year != null && (
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          {formatYear(entity.earliest_year)}
                          {entity.latest_year != null && ` – ${formatYear(entity.latest_year)}`}
                        </span>
                      )}
                    </div>
                    {entity.description && (
                      <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                        {entity.description}
                      </p>
                    )}
                    {/* Two different questions, kept separate: is it in the text, and
                        which referent is it? "Babylon" is certain as a mention and often
                        ambiguous as a referent. */}
                    <div className="mt-1.5 flex flex-wrap gap-x-4 text-xs text-slate-500 dark:text-slate-400">
                      <span>
                        Found in text: {Math.round(entity.extraction_confidence * 100)}%
                      </span>
                      {entity.identification_confidence != null && (
                        <span>
                          Identified as this specific referent:{" "}
                          {Math.round(entity.identification_confidence * 100)}%
                        </span>
                      )}
                    </div>
                    {typeof entity.attributes?.ambiguity === "string" && (
                      <p className="mt-1 text-xs italic text-amber-700 dark:text-amber-400">
                        Could also refer to: {entity.attributes.ambiguity as string}
                      </p>
                    )}
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
