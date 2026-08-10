"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiRequestError, skyOnDate } from "@/lib/api";

interface Body {
  body: string;
  ecliptic_longitude: number;
  ecliptic_latitude: number;
  zodiac_sign: string;
  degrees_in_sign: number;
  ecliptic_constellation: string;
  distance_au: number;
  accuracy_degrees: number;
  retrograde?: boolean;
}

interface Sky {
  bodies: Body[];
  moon_phase: string;
  moon_illuminated_fraction: number;
  active_meteor_showers: Array<{ name: string; peak: string; zenithal_hourly_rate: number }>;
  sign_vs_constellation_note: string;
  time_uncertainty: { note: string; uncertainty_minutes: number };
}

const BODY_COLOR: Record<string, string> = {
  Sun: "#f59e0b",
  Moon: "#cbd5e1",
  Mercury: "#a8a29e",
  Venus: "#fcd34d",
  Mars: "#ef4444",
  Jupiter: "#fb923c",
  Saturn: "#facc15",
};

const BODY_RADIUS: Record<string, number> = {
  Sun: 9,
  Moon: 7,
  Jupiter: 6,
  Venus: 5.5,
  Saturn: 5.5,
  Mars: 4.5,
  Mercury: 4,
};

const SIGNS = [
  "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
  "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
];

/**
 * An ecliptic-plane chart: the zodiac as a ring, bodies placed by ecliptic longitude.
 *
 * This is a positional diagram, not a horizon view — it shows where bodies were relative
 * to each other along the ecliptic, which is what ancient texts actually describe. A
 * horizon view would require an observer location and would imply a precision the
 * underlying model does not have for ancient dates.
 */
export function SkyMap() {
  const [year, setYear] = useState(-6);
  const [month, setMonth] = useState(4);
  const [day, setDay] = useState(17);
  const [sky, setSky] = useState<Sky | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSky((await skyOnDate({ year, month, day })) as unknown as Sky);
    } catch (cause) {
      setError(cause instanceof ApiRequestError ? cause.message : "Could not load the sky.");
    } finally {
      setLoading(false);
    }
  }, [year, month, day]);

  useEffect(() => {
    void load();
  }, [load]);

  const size = 460;
  const centre = size / 2;
  const ringRadius = 168;

  // Ecliptic longitude 0 (the vernal point) is drawn at the left, increasing
  // anticlockwise, which is the conventional orientation for an ecliptic chart.
  const position = (longitude: number, radius: number) => {
    const angle = ((longitude + 180) * Math.PI) / 180;
    return {
      x: centre + radius * Math.cos(angle),
      y: centre - radius * Math.sin(angle),
    };
  };

  return (
    <div className="space-y-6">
      <div className="card p-4">
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="block text-sm">
            <span className="font-medium">Year</span>
            <input
              type="number"
              value={year}
              min={-3000}
              max={3000}
              onChange={(event) => setYear(Number(event.target.value))}
              className="input mt-1"
            />
            <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">
              {year <= 0 ? `${1 - year} BCE` : `${year} CE`} · 0 means 1 BCE
            </span>
          </label>
          <label className="block text-sm">
            <span className="font-medium">Month</span>
            <input
              type="number"
              value={month}
              min={1}
              max={12}
              onChange={(event) => setMonth(Number(event.target.value))}
              className="input mt-1"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Day</span>
            <input
              type="number"
              value={day}
              min={1}
              max={31}
              onChange={(event) => setDay(Number(event.target.value))}
              className="input mt-1"
            />
          </label>
          <div className="flex items-end">
            <button type="button" onClick={() => void load()} className="btn-primary w-full">
              {loading ? "Computing…" : "Show the sky"}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}

      {sky && (
        <>
          <div className="card overflow-hidden p-4">
            <svg
              viewBox={`0 0 ${size} ${size}`}
              className="mx-auto h-auto w-full max-w-lg"
              role="img"
              aria-label={`Positions along the ecliptic for ${day}/${month}/${year}. ${sky.bodies
                .map((b) => `${b.body} in ${b.zodiac_sign}`)
                .join(". ")}`}
            >
              <circle cx={centre} cy={centre} r={ringRadius + 26} className="fill-slate-900 dark:fill-slate-950" />

              {SIGNS.map((sign, index) => {
                const start = index * 30;
                const mid = position(start + 15, ringRadius + 12);
                const edge = position(start, ringRadius + 26);
                const inner = position(start, ringRadius - 14);
                return (
                  <g key={sign}>
                    <line
                      x1={inner.x}
                      y1={inner.y}
                      x2={edge.x}
                      y2={edge.y}
                      className="stroke-slate-700"
                      strokeWidth={0.6}
                    />
                    <text
                      x={mid.x}
                      y={mid.y}
                      textAnchor="middle"
                      dominantBaseline="middle"
                      className="fill-slate-400"
                      fontSize={9}
                    >
                      {sign.slice(0, 3)}
                    </text>
                  </g>
                );
              })}

              <circle
                cx={centre}
                cy={centre}
                r={ringRadius - 14}
                className="fill-none stroke-slate-700"
                strokeWidth={0.8}
              />
              <text
                x={centre}
                y={centre - 6}
                textAnchor="middle"
                className="fill-slate-500"
                fontSize={10}
              >
                Earth
              </text>
              <text
                x={centre}
                y={centre + 8}
                textAnchor="middle"
                className="fill-slate-600"
                fontSize={8}
              >
                ecliptic longitude
              </text>

              {sky.bodies.map((body, index) => {
                // Stagger radii so a tight conjunction stays legible instead of
                // overlapping into a single blob.
                const radius = ringRadius - 32 - (index % 3) * 20;
                const { x, y } = position(body.ecliptic_longitude, radius);
                return (
                  <g key={body.body}>
                    <circle
                      cx={x}
                      cy={y}
                      r={BODY_RADIUS[body.body] ?? 4}
                      fill={BODY_COLOR[body.body] ?? "#94a3b8"}
                    />
                    <text
                      x={x}
                      y={y - (BODY_RADIUS[body.body] ?? 4) - 4}
                      textAnchor="middle"
                      className="fill-slate-200"
                      fontSize={9}
                    >
                      {body.body}
                      {body.retrograde ? " ℞" : ""}
                    </text>
                  </g>
                );
              })}
            </svg>

            <p className="mt-3 text-center text-sm text-slate-600 dark:text-slate-400">
              Moon phase: {sky.moon_phase} ·{" "}
              {Math.round(sky.moon_illuminated_fraction * 100)}% illuminated
            </p>
          </div>

          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">
                Positions of the Sun, Moon and naked-eye planets
              </caption>
              <thead className="border-b border-slate-200 text-left dark:border-slate-800">
                <tr>
                  <th scope="col" className="p-3 font-medium">Body</th>
                  <th scope="col" className="p-3 font-medium">Zodiac sign</th>
                  <th scope="col" className="p-3 font-medium">IAU constellation</th>
                  <th scope="col" className="p-3 font-medium">Longitude</th>
                  <th scope="col" className="p-3 font-medium">Accuracy</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {sky.bodies.map((body) => (
                  <tr key={body.body}>
                    <td className="p-3 font-medium">
                      {body.body}
                      {body.retrograde && (
                        // orange-600 on white measures 3.55:1 at this size, under the
                        // 4.5:1 minimum for body text; orange-700/300 clears it in both
                        // themes.
                        <span className="ml-2 text-xs text-orange-700 dark:text-orange-300">
                          retrograde
                        </span>
                      )}
                    </td>
                    <td className="p-3">
                      {body.zodiac_sign} {body.degrees_in_sign.toFixed(1)}°
                    </td>
                    <td className="p-3">{body.ecliptic_constellation}</td>
                    <td className="p-3 tabular-nums">
                      {body.ecliptic_longitude.toFixed(2)}°
                    </td>
                    <td className="p-3 tabular-nums text-slate-500 dark:text-slate-400">
                      ±{body.accuracy_degrees}°
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card space-y-3 p-4 text-sm text-slate-600 dark:text-slate-400">
            <p>
              <strong className="text-slate-900 dark:text-slate-100">
                Signs and constellations are not the same thing.
              </strong>{" "}
              {sky.sign_vs_constellation_note}
            </p>
            <p>{sky.time_uncertainty.note}</p>
            {sky.active_meteor_showers.length > 0 && (
              <p>
                <strong className="text-slate-900 dark:text-slate-100">
                  Meteor showers active on this date:
                </strong>{" "}
                {sky.active_meteor_showers
                  .map((shower) => `${shower.name} (peaks ${shower.peak})`)
                  .join(", ")}
                .
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
