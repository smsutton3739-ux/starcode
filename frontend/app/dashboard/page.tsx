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
  completed: "border-verdigris-300 bg-verdigris-50 text-verdigris-900 dark:border-verdigris-700 dark:bg-verdigris-950 dark:text-verdigris-200",
  partial: "border-gold-300 bg-gold-50 text-gold-900 dark:border-gold-700 dark:bg-gold-950 dark:text-gold-200",
  running: "border-lapis-300 bg-lapis-50 text-lapis-900 dark:border-lapis-700 dark:bg-lapis-950 dark:text-lapis-200",
  queued: "border-ink-300 bg-ink-50 text-ink-700 dark:border-ink-600 dark:bg-ink-800 dark:text-ink-300",
  failed: "border-crimson-300 bg-crimson-50 text-crimson-900 dark:border-crimson-700 dark:bg-crimson-950 dark:text-crimson-200",
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
        <p className="mt-2 text-sm text-ink-500 dark:text-ink-400">
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
          <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
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
        <p className="mt-10 text-center text-ink-500 dark:text-ink-400">Loading…</p>
      ) : error ? (
        <p className="mt-10 text-center text-crimson-700 dark:text-crimson-400">{error}</p>
      ) : items.length === 0 ? (
        <div className="card mt-10 p-10 text-center">
          <p className="text-ink-600 dark:text-ink-400">
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
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-500 dark:text-ink-400">
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
                        className="badge border-ink-300 bg-ink-50 text-ink-600 dark:border-ink-600 dark:bg-ink-800 dark:text-ink-300"
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
                    className="btn-ghost h-9 w-9 !px-0 text-ink-400 hover:text-crimson-600"
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
