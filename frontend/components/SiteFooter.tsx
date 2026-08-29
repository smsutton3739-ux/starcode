import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="no-print border-t border-ink-200 bg-ink-50 dark:border-ink-800 dark:bg-ink-900">
      <div className="mx-auto max-w-6xl px-4 py-8 text-sm text-ink-600 dark:text-ink-400">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-md">
            <p className="font-medium text-ink-900 dark:text-ink-100">Starcode</p>
            <p className="mt-1">
              A research aid for ancient texts, historical documents and astronomical
              references. Every finding is labelled by kind, and interpretation is never
              presented as established fact.
            </p>
          </div>
          <nav aria-label="Footer" className="flex flex-col gap-2">
            <Link href="/about" className="hover:underline">
              How it works
            </Link>
            <Link href="/explore" className="hover:underline">
              Astronomy &amp; calendars
            </Link>
            <Link href="/tools" className="hover:underline">
              Chart tools
            </Link>
            <Link href="/about#limitations" className="hover:underline">
              Known limitations
            </Link>
            <Link href="/privacy" className="hover:underline">
              Privacy
            </Link>
            <Link href="/terms" className="hover:underline">
              Terms
            </Link>
          </nav>
        </div>
        <p className="mt-6 border-t border-ink-200 pt-4 text-xs dark:border-ink-800">
          Starcode reports what sources say and what calculations show. It does not
          adjudicate religious or interpretive questions, and it makes no claims about
          future events.
        </p>
      </div>
    </footer>
  );
}
