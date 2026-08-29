"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ApiRequestError,
  createAnalysis,
  getAccessToken,
  getDatingQuota,
  ingestUrl,
  uploadFile,
} from "@/lib/api";
import type { AnalysisMode, AnalysisOptions, DatingQuota } from "@/lib/types";
import { AdvancedSettings } from "./AdvancedSettings";

const ACCEPTED = ".txt,.md,.pdf,.docx,.png,.jpg,.jpeg,.tiff,.webp";
const URL_PATTERN = /^https?:\/\/\S+$/i;

type Attachment =
  | { kind: "file"; name: string; documentId: string; characters: number; warnings: string[] }
  | { kind: "url"; url: string; documentId: string; characters: number; warnings: string[] };

/**
 * The one box and the one button.
 *
 * It accepts pasted text, a pasted URL, or a dropped file, and works out which is which
 * without asking. Advanced settings exist but stay closed unless requested — the default
 * path is: paste, press, wait.
 */
export function AnalyzeBox() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [options, setOptions] = useState<AnalysisOptions>({});
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const [signedIn, setSignedIn] = useState(false);
  const [quota, setQuota] = useState<DatingQuota | null>(null);

  // Read after mount, never during render: the token lives in localStorage, and touching
  // it on the server would break the static render of the homepage.
  useEffect(() => {
    const token = getAccessToken();
    setSignedIn(token !== null);
    if (!token) return;
    // A failure here is not worth surfacing — the allowance is a courtesy shown before
    // submitting, and the request itself still returns a proper 402 with an explanation.
    getDatingQuota()
      .then(setQuota)
      .catch(() => setQuota(null));
  }, []);

  const datingExhausted =
    quota !== null && !quota.unlimited && (quota.remaining ?? 0) <= 0;

  const looksLikeUrl = URL_PATTERN.test(text.trim()) && !text.trim().includes(" ");
  const canSubmit = !busy && (attachment !== null || text.trim().length > 0);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setBusy(true);
    setBusyLabel(
      /\.(png|jpe?g|tiff?|webp)$/i.test(file.name)
        ? "Reading the image — this can take a moment for a scan…"
        : "Extracting text…",
    );
    try {
      const result = await uploadFile(file);
      setAttachment({
        kind: "file",
        name: file.name,
        documentId: result.document_id,
        characters: result.extracted_characters,
        warnings: result.warnings,
      });
      setText("");
    } catch (cause) {
      setError(
        cause instanceof ApiRequestError
          ? cause.message
          : "That file could not be read.",
      );
    } finally {
      setBusy(false);
      setBusyLabel("");
    }
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setDragging(false);
      const file = event.dataTransfer.files?.[0];
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  const submit = useCallback(
    async (mode: AnalysisMode = "analyze") => {
    if (!canSubmit) return;
    setError(null);
    setBusy(true);

    try {
      const withMode: AnalysisOptions = mode === "analyze" ? options : { ...options, mode };
      let payload: Parameters<typeof createAnalysis>[0];

      if (attachment) {
        payload = { document_id: attachment.documentId, options: withMode };
      } else if (looksLikeUrl) {
        setBusyLabel("Fetching the page…");
        const fetched = await ingestUrl(text.trim());
        payload = { document_id: fetched.document_id, options: withMode };
      } else {
        payload = { text, options: withMode };
      }

      setBusyLabel(mode === "analyze" ? "Starting analysis…" : "Searching the sky…");
      const created = await createAnalysis(payload);
      router.push(`/analysis/${created.id}`);
    } catch (cause) {
      setBusy(false);
      setBusyLabel("");
      if (cause instanceof ApiRequestError) {
        setError(
          cause.isRateLimit
            ? `${cause.message}`
            : cause.message || "Something went wrong. Try again.",
        );
        // A refused dating search means the allowance is gone; reflect that immediately
        // so the button stops inviting a second attempt that will also fail.
        if (cause.status === 402 && mode !== "analyze") {
          getDatingQuota()
            .then(setQuota)
            .catch(() => undefined);
        }
      } else {
        setError("Something went wrong. Try again.");
      }
    }
    },
    [attachment, canSubmit, looksLikeUrl, options, router, text],
  );

  return (
    <div className="mt-8">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`card overflow-hidden transition-colors ${
          dragging ? "border-lapis-500 ring-2 ring-lapis-500/30" : ""
        }`}
      >
        <label htmlFor="analyze-input" className="sr-only">
          Text to analyse. You can also paste a URL, or drop a file here.
        </label>
        <textarea
          id="analyze-input"
          value={attachment ? "" : text}
          onChange={(event) => setText(event.target.value)}
          disabled={busy || attachment !== null}
          rows={9}
          placeholder={
            attachment
              ? ""
              : "Paste your text here…\n\nYou can also paste a link, or drag a PDF, Word document or photograph of a manuscript onto this box."
          }
          className="w-full resize-y border-0 bg-transparent p-5 text-base leading-relaxed placeholder:text-ink-400 focus:outline-none focus:ring-0 disabled:opacity-60 dark:placeholder:text-ink-500"
          onKeyDown={(event) => {
            // Enter inserts a newline — people paste multi-line texts here. Submitting
            // needs the modifier, so a stray Enter never fires an analysis early.
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              void submit("analyze");
            }
          }}
          aria-describedby="analyze-help"
        />

        {attachment && (
          <div className="mx-5 mb-4 animate-rise rounded-lg border border-ink-200 bg-ink-50 p-4 dark:border-ink-700 dark:bg-ink-800">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium">
                  {attachment.kind === "file" ? attachment.name : attachment.url}
                </p>
                <p className="text-sm text-ink-600 dark:text-ink-400">
                  {attachment.characters.toLocaleString()} characters extracted
                </p>
              </div>
              <button
                type="button"
                className="btn-ghost shrink-0 text-sm"
                onClick={() => setAttachment(null)}
              >
                Remove
              </button>
            </div>
            {attachment.warnings.length > 0 && (
              <ul className="mt-3 space-y-2 border-t border-ink-200 pt-3 text-sm text-gold-800 dark:border-ink-700 dark:text-gold-300">
                {attachment.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-ink-200 bg-ink-50 px-5 py-3 dark:border-ink-800 dark:bg-ink-900/60">
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED}
            // Visually hidden but still in the accessibility tree, so it needs its own
            // name — the adjacent button is a separate element and does not label it.
            aria-label="Choose a document to analyse: PDF, Word, plain text or an image"
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleFile(file);
              event.target.value = "";
            }}
          />
          <button
            type="button"
            className="btn-ghost text-sm"
            onClick={() => fileInput.current?.click()}
            disabled={busy}
          >
            Attach a file
          </button>
          <span className="text-xs text-ink-500 dark:text-ink-400" id="analyze-help">
            PDF, Word, images and scans. Or paste a link.
          </span>
          <span className="ml-auto text-xs text-ink-400 dark:text-ink-500">
            {!attachment && text.length > 0 && `${text.length.toLocaleString()} characters`}
          </span>
        </div>
      </div>

      {/* Two actions at the same visual level, because they answer two different
          questions: "what is this text" and "when does its sky point to". Dating is not
          a variant of analysis and burying it in advanced settings would say it was. */}
      <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto]">
        <button
          type="button"
          onClick={() => void submit("analyze")}
          disabled={!canSubmit}
          className="flex w-full items-center justify-center gap-3 rounded-xl bg-lapis-700 px-6 py-4 text-lg font-semibold text-white shadow-sm transition-colors hover:bg-lapis-800 disabled:cursor-not-allowed disabled:bg-ink-300 dark:bg-lapis-600 dark:hover:bg-lapis-500 dark:disabled:bg-ink-700"
        >
          {busy ? (
            <>
              <span
                className="h-5 w-5 animate-spin rounded-full border-2 border-white/40 border-t-white"
                aria-hidden="true"
              />
              <span>{busyLabel || "Working…"}</span>
            </>
          ) : (
            "ANALYZE"
          )}
        </button>

        {datingExhausted ? (
          // Once the allowance is gone the button stops being live rather than staying
          // clickable and failing: an action that cannot succeed should not look like one.
          <Link
            href="/pricing"
            className="flex w-full items-center justify-center rounded-xl border-2 border-gold-500 px-6 py-4 text-center text-lg font-semibold text-gold-800 transition-colors hover:bg-gold-50 dark:text-gold-300 dark:hover:bg-gold-950 sm:w-auto"
          >
            Unlock dating
          </Link>
        ) : (
          <button
            type="button"
            onClick={() => {
              if (!signedIn) {
                // No anonymous path: the allowance is counted per account. Say so before
                // the request rather than letting the server's 401 be the explanation.
                router.push("/login?reason=dating");
                return;
              }
              void submit(
                options.mode && options.mode !== "analyze" ? options.mode : "date",
              );
            }}
            disabled={!canSubmit}
            className="flex w-full items-center justify-center rounded-xl border-2 border-lapis-700 px-6 py-4 text-lg font-semibold text-lapis-800 transition-colors hover:bg-lapis-50 disabled:cursor-not-allowed disabled:border-ink-300 disabled:text-ink-400 dark:border-lapis-500 dark:text-lapis-300 dark:hover:bg-lapis-950 dark:disabled:border-ink-700 dark:disabled:text-ink-600 sm:w-auto"
          >
            Date this text
          </button>
        )}
      </div>

      <p className="mt-2 text-center text-xs text-ink-500 dark:text-ink-400 sm:text-right">
        {!signedIn ? (
          <>Astronomical dating searches the sky for dates matching the text. Needs an account.</>
        ) : quota === null ? (
          <>Astronomical dating searches the sky for dates matching the text.</>
        ) : quota.unlimited ? (
          <>Astronomical dating: unlimited on your plan.</>
        ) : datingExhausted ? (
          <>
            You have used all {quota.limit} free dating searches on this account. The
            allowance does not reset.
          </>
        ) : (
          <>
            {quota.used} of {quota.limit} free dating searches used.
          </>
        )}
      </p>

      {error && (
        <div
          role="alert"
          className="mt-4 animate-rise rounded-lg border border-crimson-300 bg-crimson-50 p-4 text-sm text-crimson-900 dark:border-crimson-800 dark:bg-crimson-950 dark:text-crimson-200"
        >
          {error}
        </div>
      )}

      {looksLikeUrl && !attachment && (
        <p className="mt-3 text-center text-sm text-ink-500 dark:text-ink-400">
          That looks like a link — the page will be fetched and its text extracted.
        </p>
      )}

      <div className="mt-6 text-center">
        <button
          type="button"
          onClick={() => setShowAdvanced((open) => !open)}
          aria-expanded={showAdvanced}
          aria-controls="advanced-settings"
          className="text-sm text-ink-500 underline-offset-4 hover:underline dark:text-ink-400"
        >
          {showAdvanced ? "Hide advanced settings" : "Advanced settings"}
        </button>
      </div>

      {showAdvanced && (
        <div id="advanced-settings" className="mt-4 animate-rise">
          <AdvancedSettings
            value={options}
            onChange={setOptions}
            paidModesAvailable={quota?.paid_modes_available ?? false}
          />
        </div>
      )}
    </div>
  );
}
