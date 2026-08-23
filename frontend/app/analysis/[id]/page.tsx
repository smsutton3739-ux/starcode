"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  ApiRequestError,
  createShare,
  downloadExport,
  getAnalysis,
  pollAnalysis,
  storeAnonymousToken,
} from "@/lib/api";
import type { AnalysisDetail, AnalysisStatusResponse } from "@/lib/types";
import { ReportView } from "@/components/ReportView";
import { ProgressPanel } from "@/components/ProgressPanel";

export default function AnalysisPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const id = params.id;

  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [status, setStatus] = useState<AnalysisStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  // A share link carries its token in the query string; persist it so the rest of the
  // page's requests (and any export) can authenticate too.
  const tokenFromUrl = searchParams.get("token");
  useEffect(() => {
    if (tokenFromUrl) storeAnonymousToken(id, tokenFromUrl);
  }, [id, tokenFromUrl]);

  const load = useCallback(async () => {
    try {
      setAnalysis(await getAnalysis(id, tokenFromUrl));
    } catch (cause) {
      setError(
        cause instanceof ApiRequestError
          ? cause.status === 404
            ? "This analysis could not be found. If you submitted it without an account, it can only be opened from the browser you used — the retrieval token is stored there and nowhere else."
            : cause.message
          : "Could not load this analysis.",
      );
    }
  }, [id, tokenFromUrl]);

  useEffect(() => {
    abort.current = new AbortController();
    const controller = abort.current;

    (async () => {
      try {
        const final = await pollAnalysis(id, setStatus, { signal: controller.signal });
        if (!controller.signal.aborted) {
          setStatus(final);
          await load();
        }
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError(
          cause instanceof ApiRequestError
            ? cause.status === 404
              ? "This analysis could not be found, or you do not have access to it."
              : cause.message
            : "Lost contact with the server while waiting for this analysis.",
        );
      }
    })();

    return () => controller.abort();
  }, [id, load]);

  const onExport = async (format: string) => {
    setExporting(format);
    try {
      await downloadExport(id, format);
    } catch (cause) {
      setError(cause instanceof ApiRequestError ? cause.message : "Export failed.");
    } finally {
      setExporting(null);
    }
  };

  const onShare = async () => {
    try {
      const share = await createShare(id, 30);
      setShareUrl(share.url);
      await navigator.clipboard?.writeText(share.url);
    } catch (cause) {
      setError(
        cause instanceof ApiRequestError
          ? cause.isAuth
            ? "Sign in to create a share link."
            : cause.message
          : "Could not create a share link.",
      );
    }
  };

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16">
        <div className="card p-6">
          <h1 className="text-xl font-semibold">Cannot open this analysis</h1>
          <p className="prose-report mt-3">{error}</p>
          <Link href="/" className="btn-primary mt-5">
            Analyse something new
          </Link>
        </div>
      </div>
    );
  }

  const isRunning =
    !status || status.status === "queued" || status.status === "running";

  if (isRunning || !analysis) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16">
        <ProgressPanel status={status} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <header className="mb-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">{analysis.title}</h1>
            <p className="mt-1 text-sm text-ink-500 dark:text-ink-400">
              {analysis.document?.word_count.toLocaleString()} words
              {analysis.detected_language && ` · ${analysis.detected_language}`}
              {analysis.duration_ms != null &&
                ` · analysed in ${(analysis.duration_ms / 1000).toFixed(1)}s`}
              {analysis.status === "partial" && " · partially complete"}
            </p>
          </div>

          <div className="no-print flex flex-wrap items-center gap-2">
            {["pdf", "docx", "csv"].map((format) => (
              <button
                key={format}
                type="button"
                onClick={() => void onExport(format)}
                disabled={exporting !== null}
                className="btn-secondary text-sm"
              >
                {exporting === format ? "Preparing…" : format.toUpperCase()}
              </button>
            ))}
            <button type="button" onClick={() => void onShare()} className="btn-secondary text-sm">
              Share
            </button>
          </div>
        </div>

        {shareUrl && (
          <div className="mt-4 animate-rise rounded-lg border border-verdigris-300 bg-verdigris-50 p-4 text-sm dark:border-verdigris-700 dark:bg-verdigris-950">
            <p className="font-medium text-verdigris-900 dark:text-verdigris-200">
              Share link created and copied to your clipboard.
            </p>
            <p className="mt-1 break-all font-mono text-xs text-verdigris-800 dark:text-verdigris-300">
              {shareUrl}
            </p>
            <p className="mt-2 text-xs text-verdigris-800 dark:text-verdigris-300">
              Anyone with this link can read the report. It expires in 30 days, and you
              can revoke it at any time from your dashboard.
            </p>
          </div>
        )}

        {analysis.document?.ocr_applied && (
          <div className="mt-4 rounded-lg border border-gold-300 bg-gold-50 p-4 text-sm text-gold-900 dark:border-gold-700 dark:bg-gold-950 dark:text-gold-200">
            <strong>This text came from OCR.</strong> Optical recognition of historical
            documents makes predictable errors — similar letterforms are confused,
            diacritics are dropped, marginalia get interleaved. Verify anything the
            analysis turns on against the original.
            {analysis.document.ocr_confidence != null && (
              <span className="ml-1">
                Average recognition confidence was{" "}
                {Math.round(analysis.document.ocr_confidence)}%.
              </span>
            )}
          </div>
        )}
      </header>

      <ReportView analysis={analysis} />
    </div>
  );
}
