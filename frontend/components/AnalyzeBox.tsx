"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiRequestError,
  createAnalysis,
  ingestUrl,
  uploadFile,
} from "@/lib/api";
import type { AnalysisOptions } from "@/lib/types";
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

  const submit = useCallback(async () => {
    if (!canSubmit) return;
    setError(null);
    setBusy(true);

    try {
      let payload: Parameters<typeof createAnalysis>[0];

      if (attachment) {
        payload = { document_id: attachment.documentId, options };
      } else if (looksLikeUrl) {
        setBusyLabel("Fetching the page…");
        const fetched = await ingestUrl(text.trim());
        payload = { document_id: fetched.document_id, options };
      } else {
        payload = { text, options };
      }

      setBusyLabel("Starting analysis…");
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
      } else {
        setError("Something went wrong. Try again.");
      }
    }
  }, [attachment, canSubmit, looksLikeUrl, options, router, text]);

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
          dragging ? "border-blue-500 ring-2 ring-blue-500/30" : ""
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
          className="w-full resize-y border-0 bg-transparent p-5 text-base leading-relaxed placeholder:text-slate-400 focus:outline-none focus:ring-0 disabled:opacity-60 dark:placeholder:text-slate-500"
          onKeyDown={(event) => {
            // Enter inserts a newline — people paste multi-line texts here. Submitting
            // needs the modifier, so a stray Enter never fires an analysis early.
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              void submit();
            }
          }}
          aria-describedby="analyze-help"
        />

        {attachment && (
          <div className="mx-5 mb-4 animate-rise rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium">
                  {attachment.kind === "file" ? attachment.name : attachment.url}
                </p>
                <p className="text-sm text-slate-600 dark:text-slate-400">
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
              <ul className="mt-3 space-y-2 border-t border-slate-200 pt-3 text-sm text-amber-800 dark:border-slate-700 dark:text-amber-300">
                {attachment.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 bg-slate-50 px-5 py-3 dark:border-slate-800 dark:bg-slate-900/60">
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
          <span className="text-xs text-slate-500 dark:text-slate-400" id="analyze-help">
            PDF, Word, images and scans. Or paste a link.
          </span>
          <span className="ml-auto text-xs text-slate-400 dark:text-slate-500">
            {!attachment && text.length > 0 && `${text.length.toLocaleString()} characters`}
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit}
        className="mt-5 flex w-full items-center justify-center gap-3 rounded-xl bg-blue-700 px-6 py-4 text-lg font-semibold text-white shadow-sm transition-colors hover:bg-blue-800 disabled:cursor-not-allowed disabled:bg-slate-300 dark:bg-blue-600 dark:hover:bg-blue-500 dark:disabled:bg-slate-700"
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

      {error && (
        <div
          role="alert"
          className="mt-4 animate-rise rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
        >
          {error}
        </div>
      )}

      {looksLikeUrl && !attachment && (
        <p className="mt-3 text-center text-sm text-slate-500 dark:text-slate-400">
          That looks like a link — the page will be fetched and its text extracted.
        </p>
      )}

      <div className="mt-6 text-center">
        <button
          type="button"
          onClick={() => setShowAdvanced((open) => !open)}
          aria-expanded={showAdvanced}
          aria-controls="advanced-settings"
          className="text-sm text-slate-500 underline-offset-4 hover:underline dark:text-slate-400"
        >
          {showAdvanced ? "Hide advanced settings" : "Advanced settings"}
        </button>
      </div>

      {showAdvanced && (
        <div id="advanced-settings" className="mt-4 animate-rise">
          <AdvancedSettings value={options} onChange={setOptions} />
        </div>
      )}
    </div>
  );
}
