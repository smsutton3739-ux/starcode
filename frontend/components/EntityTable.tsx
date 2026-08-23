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
      <p className="mt-2 text-sm italic text-ink-500 dark:text-ink-400">
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
              ? "border-lapis-500 bg-lapis-100 text-lapis-900 dark:bg-lapis-900 dark:text-lapis-100"
              : "border-ink-300 bg-ink-50 text-ink-600 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-300"
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
                ? "border-lapis-500 bg-lapis-100 text-lapis-900 dark:bg-lapis-900 dark:text-lapis-100"
                : "border-ink-300 bg-ink-50 text-ink-600 dark:border-ink-600 dark:bg-ink-900 dark:text-ink-300"
            }`}
          >
            {entityTypeLabel(type)} {list.length}
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-6">
        {visible.map(([type, list]) => (
          <div key={type}>
            <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">
              {entityTypeLabel(type)}
            </h3>
            <ul className="mt-2 divide-y divide-ink-200 dark:divide-ink-800">
              {list
                .sort((a, b) => b.mention_count - a.mention_count)
                .map((entity) => (
                  <li key={entity.id} className="py-3">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="font-medium">{entity.name}</span>
                      {entity.mention_count > 1 && (
                        <span className="text-xs text-ink-500 dark:text-ink-400">
                          mentioned {entity.mention_count} times
                        </span>
                      )}
                      {entity.earliest_year != null && (
                        <span className="text-xs text-ink-500 dark:text-ink-400">
                          {formatYear(entity.earliest_year)}
                          {entity.latest_year != null && ` – ${formatYear(entity.latest_year)}`}
                        </span>
                      )}
                    </div>
                    {entity.description && (
                      <p className="mt-1 text-sm text-ink-600 dark:text-ink-400">
                        {entity.description}
                      </p>
                    )}
                    {/* Two different questions, kept separate: is it in the text, and
                        which referent is it? "Babylon" is certain as a mention and often
                        ambiguous as a referent. */}
                    <div className="mt-1.5 flex flex-wrap gap-x-4 text-xs text-ink-500 dark:text-ink-400">
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
                      <p className="mt-1 text-xs italic text-gold-700 dark:text-gold-400">
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
