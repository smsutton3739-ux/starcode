"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ApiRequestError,
  deleteAnalysis,
  getAccessToken,
  listAnalyses,
  updateAnalysis,
} from "@/lib/api";
import type { AnalysisSummary } from "@/lib/types";

const STATUS_STYLE: Record<string, string> = {
  completed: "border-green-300 bg-green-50 text-green-900 dark:border-green-700 dark:bg-green-950 dark:text-green-200",
  partial: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200",
  running: "border-blue-300 bg-blue-50 text-blue-900 dark:border-blue-700 dark:bg-blue-950 dark:text-blue-200",
  queued: "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300",
  failed: "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950 dark:text-red-200",
};

export default function DashboardPage() {
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) {
      setLoading(false);
      setError("signin");
      return;
    }
    setLoading(true);
    listAnalyses({ q: query || undefined, favorites_only: favoritesOnly, limit: 50 })
      .then((page) => {
        setItems(page.items);
        setTotal(page.total);
        setError(null);
      })
      .catch((cause: unknown) =>
        setError(cause instanceof ApiRequestError ? cause.message : "Could not load your analyses."),
      )
      .finally(() => setLoading(false));
  }, [query, favoritesOnly]);

  if (error === "signin") {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <h1 className="text-2xl font-semibold">Your analyses</h1>
        <p className="prose-report mt-3">
          Sign in to keep your analyses, organise them into collections, and search across
          everything you have run.
        </p>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          Analyses you ran without an account are stored in this browser only, and are
          reachable from the link you were given.
        </p>
        <Link href="/login" className="btn-primary mt-6">
          Sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Your analyses</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {total} saved
          </p>
        </div>
        <Link href="/" className="btn-primary">
          New analysis
        </Link>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <label className="flex-1">
          <span className="sr-only">Search your analyses by title</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by title…"
            className="input"
          />
        </label>
        <button
          type="button"
          onClick={() => setFavoritesOnly((value) => !value)}
          aria-pressed={favoritesOnly}
          className={favoritesOnly ? "btn-primary" : "btn-secondary"}
        >
          Favourites
        </button>
      </div>

      {loading ? (
        <p className="mt-10 text-center text-slate-500 dark:text-slate-400">Loading…</p>
      ) : error ? (
        <p className="mt-10 text-center text-red-700 dark:text-red-400">{error}</p>
      ) : items.length === 0 ? (
        <div className="card mt-10 p-10 text-center">
          <p className="text-slate-600 dark:text-slate-400">
            {query || favoritesOnly
              ? "Nothing matches that."
              : "You have not run any analyses yet."}
          </p>
          <Link href="/" className="btn-primary mt-5">
            Analyse a text
          </Link>
        </div>
      ) : (
        <ul className="mt-6 space-y-3">
          {items.map((item) => (
            <li key={item.id} className="card p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/analysis/${item.id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {item.title}
                  </Link>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                    <span className={`badge ${STATUS_STYLE[item.status] ?? ""}`}>
                      {item.status}
                    </span>
                    {item.overall_confidence != null && (
                      <span>{Math.round(item.overall_confidence * 100)}% confidence</span>
                    )}
                    <span>{new Date(item.created_at).toLocaleDateString()}</span>
                    {item.tags.map((tag) => (
                      <span
                        key={tag}
                        className="badge border-slate-300 bg-slate-50 text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    aria-label={item.is_favorite ? "Remove from favourites" : "Add to favourites"}
                    aria-pressed={item.is_favorite}
                    onClick={async () => {
                      const updated = await updateAnalysis(item.id, {
                        is_favorite: !item.is_favorite,
                      });
                      setItems((current) =>
                        current.map((entry) => (entry.id === item.id ? updated : entry)),
                      );
                    }}
                    className="btn-ghost h-9 w-9 !px-0"
                  >
                    <span aria-hidden="true">{item.is_favorite ? "★" : "☆"}</span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${item.title}`}
                    onClick={async () => {
                      if (!window.confirm(`Delete "${item.title}"? This cannot be undone.`)) return;
                      await deleteAnalysis(item.id);
                      setItems((current) => current.filter((entry) => entry.id !== item.id));
                      setTotal((value) => value - 1);
                    }}
                    className="btn-ghost h-9 w-9 !px-0 text-slate-400 hover:text-red-600"
                  >
                    <span aria-hidden="true">×</span>
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
