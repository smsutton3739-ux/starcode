"use client";

import { useEffect, useState } from "react";
import { ApiRequestError, getAccessToken } from "@/lib/api";

const API = `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1`;

async function adminFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { Authorization: `Bearer ${getAccessToken() ?? ""}` },
  });
  const body = await response.json();
  if (!response.ok) throw new ApiRequestError(response.status, body);
  return body as T;
}

type Tab = "system" | "usage" | "users" | "audit";

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("system");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const path =
      tab === "system"
        ? "/admin/system"
        : tab === "usage"
          ? "/admin/usage?days=30"
          : tab === "users"
            ? "/admin/users?limit=50"
            : "/admin/audit?limit=50";

    setLoading(true);
    adminFetch<Record<string, unknown>>(path)
      .then((payload) => {
        setData(payload);
        setError(null);
      })
      .catch((cause: unknown) =>
        setError(
          cause instanceof ApiRequestError
            ? cause.status === 403
              ? "This area is for administrators."
              : cause.message
            : "Could not load admin data.",
        ),
      )
      .finally(() => setLoading(false));
  }, [tab]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">Administration</h1>

      <div role="tablist" aria-label="Admin sections" className="mt-6 flex flex-wrap gap-2 border-b border-slate-200 dark:border-slate-800">
        {(["system", "usage", "users", "audit"] as Tab[]).map((key) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium capitalize transition-colors ${
              tab === key
                ? "border-blue-600 text-blue-700 dark:border-blue-400 dark:text-blue-300"
                : "border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            }`}
          >
            {key}
          </button>
        ))}
      </div>

      {loading && <p className="mt-8 text-slate-500 dark:text-slate-400">Loading…</p>}
      {error && (
        <p role="alert" className="mt-8 text-red-700 dark:text-red-400">
          {error}
        </p>
      )}

      {data && !error && (
        <div className="mt-6 space-y-4">
          {tab === "usage" && typeof data.evidence_ratio === "number" && (
            <div className="card p-5">
              <h2 className="font-medium">Evidence ratio</h2>
              <p className="mt-1 text-3xl font-semibold tabular-nums">
                {Math.round((data.evidence_ratio as number) * 100)}%
              </p>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
                {data.evidence_ratio_note as string}
              </p>
            </div>
          )}

          {/* The raw payload is shown deliberately: an operator debugging a live system
              is better served by the exact response than by a prettified subset of it. */}
          <div
            className="card overflow-x-auto p-4"
            tabIndex={0}
            role="group"
            aria-label="Raw response, scrolls horizontally"
          >
            <pre className="whitespace-pre-wrap font-mono text-xs text-slate-700 dark:text-slate-300">
              {JSON.stringify(data, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
