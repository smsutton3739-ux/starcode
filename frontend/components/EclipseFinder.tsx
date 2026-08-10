"use client";

import { useState } from "react";
import { ApiRequestError, eclipsesInRange } from "@/lib/api";

interface EclipseEvent {
  label: string;
  gregorian_label: string;
  hour_ut: number;
  accuracy_note: string;
  details: {
    eclipse_kind: string;
    magnitude: number;
    gamma: number;
    zodiac_sign?: string;
    visibility_uncertainty?: string;
  };
}

export function EclipseFinder() {
  const [startYear, setStartYear] = useState(30);
  const [endYear, setEndYear] = useState(35);
  const [kind, setKind] = useState<"both" | "solar" | "lunar">("both");
  const [events, setEvents] = useState<EclipseEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const search = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await eclipsesInRange(startYear, endYear, kind);
      setEvents(data.events as unknown as EclipseEvent[]);
    } catch (cause) {
      setError(cause instanceof ApiRequestError ? cause.message : "Search failed.");
      setEvents(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="card p-4">
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="block text-sm">
            <span className="font-medium">From year</span>
            <input
              type="number"
              value={startYear}
              min={-3000}
              max={3000}
              onChange={(event) => setStartYear(Number(event.target.value))}
              className="input mt-1"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">To year</span>
            <input
              type="number"
              value={endYear}
              min={-3000}
              max={3000}
              onChange={(event) => setEndYear(Number(event.target.value))}
              className="input mt-1"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Type</span>
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value as typeof kind)}
              className="input mt-1"
            >
              <option value="both">Both</option>
              <option value="solar">Solar</option>
              <option value="lunar">Lunar</option>
            </select>
          </label>
          <div className="flex items-end">
            <button type="button" onClick={() => void search()} className="btn-primary w-full">
              {loading ? "Searching…" : "Find eclipses"}
            </button>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
          Ranges are capped at 200 years — a longer scan would take minutes of CPU without
          telling you anything a narrower one does not.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}

      {events && (
        <div className="card">
          <p className="border-b border-slate-200 p-4 text-sm dark:border-slate-800">
            {events.length} eclipse{events.length === 1 ? "" : "s"} found.
          </p>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {events.map((event, index) => (
              <li key={index} className="p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">{event.gregorian_label}</span>
                  <span className="text-sm text-slate-500 dark:text-slate-400">
                    {event.hour_ut.toFixed(1)}h UT
                  </span>
                </div>
                <p className="mt-1 text-sm">{event.label}</p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  magnitude {event.details.magnitude} · γ = {event.details.gamma}
                  {event.details.zodiac_sign && ` · in ${event.details.zodiac_sign}`}
                </p>
                <p className="mt-2 text-xs italic text-slate-500 dark:text-slate-400">
                  {event.accuracy_note}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
