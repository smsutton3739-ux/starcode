"use client";

import type { AnalysisOptions } from "@/lib/types";

interface Props {
  value: AnalysisOptions;
  onChange: (next: AnalysisOptions) => void;
}

/**
 * Advanced settings, hidden by default.
 *
 * Every option here has a defensible default, and nothing in this panel is required to
 * get a complete analysis. It exists for the researcher who needs to pin the Maya
 * correlation constant or widen the astronomical search window — not as a step in the
 * normal path.
 */
export function AdvancedSettings({ value, onChange }: Props) {
  const set = <K extends keyof AnalysisOptions>(key: K, next: AnalysisOptions[K]) =>
    onChange({ ...value, [key]: next });

  return (
    <div className="card space-y-5 p-5 text-sm">
      <p className="text-ink-600 dark:text-ink-400">
        These are optional. The defaults produce a full analysis.
      </p>

      <fieldset className="space-y-3">
        <legend className="font-medium">Include</legend>
        {(
          [
            ["include_traditional_interpretations", "Traditional interpretations", "What religious and cultural traditions have held about this text."],
            ["include_scholarly", "Scholarly views", "Positions argued in academic literature, with citations."],
            ["include_alternative_interpretations", "Alternative readings", "Other possible interpretations, clearly marked as hypotheses."],
            ["include_astronomical_correlation", "Astronomical correlation", "Check dates found in the text against computed celestial events."],
          ] as const
        ).map(([key, label, help]) => {
          // "Scholarly views" is not a separate backend flag; it travels with the
          // traditional-interpretations agent. Kept visible because users look for it.
          const field = key === "include_scholarly" ? "include_traditional_interpretations" : key;
          const checked = value[field as keyof AnalysisOptions] !== false;
          return (
            <label key={key} className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={checked}
                onChange={(event) =>
                  set(field as keyof AnalysisOptions, event.target.checked as never)
                }
                className="mt-1 h-4 w-4 rounded border-ink-300 text-lapis-700 dark:border-ink-600"
              />
              <span>
                <span className="font-medium">{label}</span>
                <span className="block text-xs text-ink-500 dark:text-ink-400">{help}</span>
              </span>
            </label>
          );
        })}
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="font-medium">Detail level</span>
          <select
            value={value.detail_level ?? "standard"}
            onChange={(event) =>
              set("detail_level", event.target.value as AnalysisOptions["detail_level"])
            }
            className="input mt-1"
          >
            <option value="brief">Brief</option>
            <option value="standard">Standard</option>
            <option value="exhaustive">Exhaustive</option>
          </select>
        </label>

        <label className="block">
          <span className="font-medium">Output language</span>
          <select
            value={value.output_language ?? "en"}
            onChange={(event) => set("output_language", event.target.value)}
            className="input mt-1"
          >
            <option value="en">English</option>
            <option value="es">Español</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
            <option value="pt">Português</option>
            <option value="ar">العربية</option>
            <option value="he">עברית</option>
            <option value="zh">中文</option>
          </select>
        </label>

        <label className="block">
          <span className="font-medium">Astronomical search window</span>
          <input
            type="number"
            min={0}
            max={200}
            value={value.astronomical_search_window_years ?? 5}
            onChange={(event) =>
              set("astronomical_search_window_years", Number(event.target.value))
            }
            className="input mt-1"
          />
          <span className="mt-1 block text-xs text-ink-500 dark:text-ink-400">
            Years either side of a date found in the text. A wider window finds more
            events — and makes any match weaker evidence, because coincidences become
            easy.
          </span>
        </label>

        <label className="block">
          <span className="font-medium">Maya correlation constant</span>
          <select
            value={value.maya_correlation ?? 584283}
            onChange={(event) => set("maya_correlation", Number(event.target.value))}
            className="input mt-1"
          >
            <option value={584283}>584283 — GMT (standard)</option>
            <option value={584285}>584285 — GMT variant</option>
          </select>
          <span className="mt-1 block text-xs text-ink-500 dark:text-ink-400">
            Every Long Count conversion depends on this. The two options differ by two
            days.
          </span>
        </label>
      </div>
    </div>
  );
}
