"use client";

import { useState } from "react";
import { SkyMap } from "@/components/SkyMap";
import { CalendarConverter } from "@/components/CalendarConverter";
import { EclipseFinder } from "@/components/EclipseFinder";

type Tab = "sky" | "calendars" | "eclipses";

const TABS: Array<{ key: Tab; label: string; blurb: string }> = [
  {
    key: "sky",
    label: "Sky map",
    blurb:
      "Where the Sun, Moon and naked-eye planets were on any date between 3000 BCE and 3000 CE.",
  },
  {
    key: "calendars",
    label: "Calendar converter",
    blurb:
      "Convert a date between twelve calendar systems, with the caveats each conversion carries.",
  },
  {
    key: "eclipses",
    label: "Eclipse finder",
    blurb:
      "Every solar and lunar eclipse in a range of years, with type, magnitude and the uncertainty on each.",
  },
];

/**
 * The reference tools, usable on their own without submitting a text. A historian who
 * only wants to know what the sky looked like in 33 CE should not have to paste
 * something first.
 */
export default function ExplorePage() {
  const [tab, setTab] = useState<Tab>("sky");
  const active = TABS.find((entry) => entry.key === tab)!;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Astronomy &amp; calendars</h1>
      <p className="mt-2 max-w-2xl text-ink-600 dark:text-ink-400">
        The same engines the analysis uses, available directly. Everything here is
        computed from published algorithms, and every result states its own accuracy.
      </p>

      <div
        role="tablist"
        aria-label="Reference tools"
        className="mt-6 flex flex-wrap gap-2 border-b border-ink-200 dark:border-ink-800"
      >
        {TABS.map((entry) => (
          <button
            key={entry.key}
            role="tab"
            id={`tab-${entry.key}`}
            aria-selected={tab === entry.key}
            aria-controls={`panel-${entry.key}`}
            onClick={() => setTab(entry.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === entry.key
                ? "border-lapis-600 text-lapis-700 dark:border-lapis-400 dark:text-lapis-300"
                : "border-transparent text-ink-600 hover:text-ink-900 dark:text-ink-400 dark:hover:text-ink-100"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <p className="mt-4 text-sm text-ink-600 dark:text-ink-400">{active.blurb}</p>

      <div
        role="tabpanel"
        id={`panel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        className="mt-6 animate-fade-in"
      >
        {tab === "sky" && <SkyMap />}
        {tab === "calendars" && <CalendarConverter />}
        {tab === "eclipses" && <EclipseFinder />}
      </div>
    </div>
  );
}
