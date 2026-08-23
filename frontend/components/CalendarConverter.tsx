"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiRequestError, convertCalendar, listCalendars } from "@/lib/api";

interface Conversion {
  system: string;
  label: string;
  is_exact: boolean;
  uncertainty_note?: string | null;
  extra?: Record<string, unknown>;
}

interface CalendarSpec {
  key: string;
  name: string;
  culture: string;
  epoch_description: string;
  caveat?: string | null;
}

export function CalendarConverter() {
  const [calendars, setCalendars] = useState<CalendarSpec[]>([]);
  const [system, setSystem] = useState("gregorian");
  const [year, setYear] = useState(2024);
  const [month, setMonth] = useState(10);
  const [day, setDay] = useState(3);
  const [result, setResult] = useState<{
    conversions: Conversion[];
    weekday: string;
    eras: Record<string, string>;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCalendars()
      .then((data) => setCalendars(data.calendars as unknown as CalendarSpec[]))
      .catch(() => setCalendars([]));
  }, []);

  const convert = useCallback(async () => {
    setError(null);
    try {
      const data = await convertCalendar({ system, year, month, day });
      setResult(data as never);
    } catch (cause) {
      setError(cause instanceof ApiRequestError ? cause.message : "Conversion failed.");
    }
  }, [system, year, month, day]);

  useEffect(() => {
    void convert();
  }, [convert]);

  return (
    <div className="space-y-6">
      <div className="card p-4">
        <div className="grid gap-3 sm:grid-cols-5">
          <label className="block text-sm sm:col-span-2">
            <span className="font-medium">From calendar</span>
            <select
              value={system}
              onChange={(event) => setSystem(event.target.value)}
              className="input mt-1"
            >
              {calendars.map((calendar) => (
                <option key={calendar.key} value={calendar.key}>
                  {calendar.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="font-medium">Year</span>
            <input
              type="number"
              value={year}
              onChange={(event) => setYear(Number(event.target.value))}
              className="input mt-1"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Month</span>
            <input
              type="number"
              min={1}
              max={19}
              value={month}
              onChange={(event) => setMonth(Number(event.target.value))}
              className="input mt-1"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Day</span>
            <input
              type="number"
              min={1}
              max={31}
              value={day}
              onChange={(event) => setDay(Number(event.target.value))}
              className="input mt-1"
            />
          </label>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-crimson-700 dark:text-crimson-400">
          {error}
        </p>
      )}

      {result && (
        <>
          <div className="card divide-y divide-ink-100 dark:divide-ink-800">
            {result.conversions.map((conversion) => (
              <div key={conversion.system} className="p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-xs uppercase tracking-wide text-ink-500 dark:text-ink-400">
                    {conversion.system.replace(/_/g, " ")}
                  </span>
                  {!conversion.is_exact && (
                    <span className="badge border-gold-300 bg-gold-50 text-gold-900 dark:border-gold-700 dark:bg-gold-950 dark:text-gold-200">
                      approximate
                    </span>
                  )}
                </div>
                <p className="mt-1 font-medium">{conversion.label}</p>
                {conversion.uncertainty_note && (
                  <p className="mt-1.5 text-xs text-ink-500 dark:text-ink-400">
                    {conversion.uncertainty_note}
                  </p>
                )}
              </div>
            ))}
          </div>

          <div className="card p-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">
              Era systems · {result.weekday}
            </h3>
            <ul className="mt-2 space-y-1.5 text-sm">
              {Object.entries(result.eras).map(([key, value]) => (
                <li key={key}>
                  <span className="text-ink-500 dark:text-ink-400">
                    {key.replace(/_/g, " ")}:
                  </span>{" "}
                  {value}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
