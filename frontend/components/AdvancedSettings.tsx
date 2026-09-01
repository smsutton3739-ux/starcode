"use client";

import Link from "next/link";
import { formatYear } from "@/lib/claims";
import type { AnalysisMode, AnalysisOptions } from "@/lib/types";

interface Props {
  value: AnalysisOptions;
  onChange: (next: AnalysisOptions) => void;
  /** Whether this account may run the paid dating modes. */
  paidModesAvailable?: boolean;
}

/** The three paid dating modes, and what each one is for. */
const DATING_MODES: { value: AnalysisMode; label: string; help: string }[] = [
  {
    value: "rectification",
    label: "Rectification",
    help: "Narrows the match to the tightest window the evidence supports, instead of naming a single best date.",
  },
  {
    value: "eschatological",
    label: "Eschatological calculation",
    help: "Applies the search to prophetic material, reporting what each interpretive framework yields, never what will happen.",
  },
  {
    value: "historicizing",
    label: "Historicizing",
    help: "Proposes concrete historical groundings for symbolic material, offered for assessment rather than asserted.",
  },
];

/**
 * Advanced settings, hidden by default.
 *
 * Every option here has a defensible default, and nothing in this panel is required to
 * get a complete analysis. It exists for the researcher who needs to pin the Maya
 * correlation constant or widen the astronomical search window — not as a step in the
 * normal path.
 */
export function AdvancedSettings({ value, onChange, paidModesAvailable = false }: Props) {
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
            events, and makes any match weaker evidence, because coincidences become
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
            <option value={584283}>584283 (GMT standard)</option>
            <option value={584285}>584285 (GMT variant)</option>
          </select>
          <span className="mt-1 block text-xs text-ink-500 dark:text-ink-400">
            Every Long Count conversion depends on this. The two options differ by two
            days.
          </span>
        </label>
      </div>

      <DatingRange value={value} onChange={onChange} />
      <DatingModes value={value} onChange={onChange} available={paidModesAvailable} />
    </div>
  );
}

/**
 * The era to search when dating a text.
 *
 * A *narrowing* control. The server clamps the span to the plan's limit whatever is
 * asked for here, so a wider range produces a smaller search rather than an error — and
 * a user who already knows the century gets a far better search than the default window
 * can give, because a dating search gets less meaningful the wider it runs.
 */
function DatingRange({ value, onChange }: Pick<Props, "value" | "onChange">) {
  const start = value.date_range_start ?? null;
  const end = value.date_range_end ?? null;

  const set = (key: "date_range_start" | "date_range_end", raw: string) => {
    const parsed = raw.trim() === "" ? null : Number(raw);
    const next = { ...value, [key]: Number.isFinite(parsed as number) ? parsed : null };
    // The backend requires both ends or neither: a half-open range has no defensible
    // other end, so clearing one clears both rather than sending something it rejects.
    if (next.date_range_start === null || next.date_range_end === null) {
      next.date_range_start = null;
      next.date_range_end = null;
    }
    onChange(next);
  };

  return (
    <fieldset className="space-y-3 border-t border-ink-200 pt-5 dark:border-ink-700">
      <legend className="font-medium">Dating search range</legend>
      <p className="text-xs text-ink-500 dark:text-ink-400">
        Only used by the dating searches. Astronomical year numbering, so year 0 is 1 BCE
        and negative numbers are earlier, so enter −586 for 587 BCE. Leave both blank and
        the range is taken from dates in the text, or from a default window if the text
        gives none.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="font-medium">Earliest year</span>
          <input
            type="number"
            min={-3000}
            max={3000}
            value={start ?? ""}
            placeholder="−800"
            onChange={(event) => set("date_range_start", event.target.value)}
            className="input mt-1"
          />
          {start !== null && (
            <span className="mt-1 block text-xs text-ink-500 dark:text-ink-400">
              {formatYear(start)}
            </span>
          )}
        </label>

        <label className="block">
          <span className="font-medium">Latest year</span>
          <input
            type="number"
            min={-3000}
            max={3000}
            value={end ?? ""}
            placeholder="200"
            onChange={(event) => set("date_range_end", event.target.value)}
            className="input mt-1"
          />
          {end !== null && (
            <span className="mt-1 block text-xs text-ink-500 dark:text-ink-400">
              {formatYear(end)}
            </span>
          )}
        </label>
      </div>
    </fieldset>
  );
}

/**
 * The three paid dating modes.
 *
 * Visible but disabled for a free account rather than hidden. Hiding them would leave a
 * reader unable to tell the product does not do this from the product not selling it to
 * them, and the locked treatment here is the same one interpretive claims already use:
 * the thing stays in place, its content is withheld, and what is being withheld is named.
 */
function DatingModes({
  value,
  onChange,
  available,
}: Pick<Props, "value" | "onChange"> & { available: boolean }) {
  const selected = value.mode && value.mode !== "analyze" ? value.mode : null;

  return (
    <fieldset className="space-y-3 border-t border-ink-200 pt-5 dark:border-ink-700">
      <legend className="font-medium">Advanced dating modes</legend>
      <p className="text-xs text-ink-500 dark:text-ink-400">
        Variants of the dating search. Choosing one changes what “Date this text” runs.
        {!available && " These require a paid plan."}
      </p>

      <div className="space-y-2">
        <label className="flex items-start gap-3">
          <input
            type="radio"
            name="dating-mode"
            checked={selected === null}
            onChange={() => onChange({ ...value, mode: "date" })}
            className="mt-1 h-4 w-4 border-ink-300 text-lapis-700 dark:border-ink-600"
          />
          <span>
            <span className="font-medium">Standard dating</span>
            <span className="block text-xs text-ink-500 dark:text-ink-400">
              Finds dates whose real sky matches the phenomena the text describes.
            </span>
          </span>
        </label>

        {DATING_MODES.map((mode) => (
          <label
            key={mode.value}
            className={`flex items-start gap-3 ${available ? "" : "opacity-60"}`}
          >
            <input
              type="radio"
              name="dating-mode"
              disabled={!available}
              checked={selected === mode.value}
              onChange={() => onChange({ ...value, mode: mode.value })}
              className="mt-1 h-4 w-4 border-ink-300 text-lapis-700 disabled:cursor-not-allowed dark:border-ink-600"
            />
            <span>
              <span className="font-medium">
                {mode.label}
                {!available && (
                  <span className="ml-2 badge border-gold-400 bg-gold-50 text-gold-900 dark:border-gold-600 dark:bg-gold-950 dark:text-gold-200">
                    {/* An icon and a word, never colour alone. */}
                    <span aria-hidden="true">🔒</span> Paid plan
                  </span>
                )}
              </span>
              <span className="block text-xs text-ink-500 dark:text-ink-400">{mode.help}</span>
            </span>
          </label>
        ))}
      </div>

      {!available && (
        <p className="text-xs">
          <Link href="/pricing" className="text-lapis-700 underline dark:text-lapis-300">
            See what a paid plan includes
          </Link>
        </p>
      )}
    </fieldset>
  );
}
