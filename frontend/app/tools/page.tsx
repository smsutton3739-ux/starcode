import Link from "next/link";
import { headers } from "next/headers";
import {
  ASTRO_CHARTS_AFFILIATE_ID,
  ASTRO_CHARTS_ORIGIN,
  IFRAME_RESIZER_SRC,
  widgetUrl,
} from "@/lib/embeds";

export const metadata = {
  title: "Chart tools",
  description:
    "Third-party birth chart and synastry calculators, offered alongside Starcode's own analysis and clearly separated from it.",
};

const WIDGETS = [
  {
    tool: "birth-chart" as const,
    heading: "Birth chart",
    minHeight: 520,
    blurb:
      "Where the Sun, Moon and planets stood at a given date, time and place, drawn in the conventional chart form.",
  },
  {
    tool: "synastry" as const,
    heading: "Synastry chart",
    minHeight: 760,
    blurb:
      "Two charts overlaid, showing the angular relationships between one set of positions and the other.",
  },
];

export default async function ToolsPage() {
  // Minted per request by middleware.ts. The embed's resize helper is a third-party
  // script, so it is admitted the same way every other script here is — by nonce — rather
  // than by opening script-src to an external origin.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const configured = Boolean(ASTRO_CHARTS_AFFILIATE_ID);

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">Chart tools</h1>

      <p className="prose-report mt-4">
        These are calculators from{" "}
        <a
          href={ASTRO_CHARTS_ORIGIN}
          className="font-medium text-lapis-700 underline-offset-4 hover:underline dark:text-lapis-400"
          rel="noopener noreferrer external"
          target="_blank"
        >
          Astro·Charts
        </a>
        , a separate service. They are on their own page, and not part of any Starcode
        report, for a reason worth stating plainly.
      </p>

      <div className="mt-6 rounded-lg border border-gold-300 bg-gold-50 p-4 dark:border-gold-800 dark:bg-gold-950">
        <h2 className="text-sm font-semibold text-gold-900 dark:text-gold-200">
          What these are, and what they are not
        </h2>
        <p className="mt-2 text-sm text-gold-900 dark:text-gold-200">
          Computing where the planets were at a moment in time is astronomy, and Starcode
          does it too. See{" "}
          <Link href="/explore" className="underline underline-offset-4">
            Astronomy &amp; calendars
          </Link>
          . Reading meaning into those positions is astrology: a tradition with a long
          documented history, and not a finding about the world.
        </p>
        <p className="mt-2 text-sm text-gold-900 dark:text-gold-200">
          Starcode reports what traditions hold, attributed as such, and never as
          established fact. Nothing produced on this page is a Starcode analysis, is
          checked by its evidence rules, or carries a confidence score. It does not appear
          in your saved analyses.
        </p>
      </div>

      {configured ? (
        <>
          {WIDGETS.map(({ tool, heading, minHeight, blurb }) => (
            <section key={tool} className="mt-10">
              <h2 className="text-xl font-semibold">{heading}</h2>
              <p className="mt-2 text-sm text-ink-600 dark:text-ink-400">{blurb}</p>
              <iframe
                src={widgetUrl(tool)}
                title={`Astro·Charts ${heading.toLowerCase()}`}
                loading="lazy"
                // Sandboxed to what a chart calculator actually needs. Without this an
                // embedded document may navigate the top-level page out from under the
                // reader; allow-scripts and allow-forms are what make the widget work,
                // and allow-same-origin keeps it able to reach its own service.
                sandbox="allow-scripts allow-forms allow-same-origin allow-popups allow-popups-to-escape-sandbox"
                referrerPolicy="strict-origin-when-cross-origin"
                className="mt-4 block w-full rounded-lg border border-ink-200 dark:border-ink-800"
                style={{ minHeight }}
              />
            </section>
          ))}

          {/* One resizer covers every embed on the page. Third-party, so it is nonced
              rather than host-allowlisted, and it only ever runs on this route. */}
          <script src={IFRAME_RESIZER_SRC} nonce={nonce} async suppressHydrationWarning />
        </>
      ) : (
        <div className="mt-10 rounded-lg border border-ink-200 bg-ink-50 p-4 text-sm text-ink-600 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-400">
          <p className="font-medium text-ink-900 dark:text-ink-100">
            The chart tools are not configured on this deployment.
          </p>
          <p className="mt-2">
            They need <code className="font-mono">NEXT_PUBLIC_ASTRO_CHARTS_AFF</code> set
            at build time. Nothing is embedded until it is, rather than shipping a
            placeholder that loads but credits nobody.
          </p>
        </div>
      )}

      <p className="mt-10 border-t border-ink-200 pt-6 text-xs text-ink-500 dark:border-ink-800 dark:text-ink-400">
        <strong className="font-semibold">Disclosure:</strong> these embeds carry an
        affiliate identifier, so Starcode may earn a commission if you go on to buy
        something from Astro·Charts. It costs you nothing extra, and it does not influence
        anything Starcode reports. The analysis engine has no knowledge of this page.
        Whatever you enter into these charts goes to Astro·Charts, under their privacy
        policy and not Starcode&rsquo;s.
      </p>

      <p className="mt-6 text-center">
        <Link
          href="/"
          className="text-sm text-ink-500 underline-offset-4 hover:underline dark:text-ink-400"
        >
          Back to analysis
        </Link>
      </p>
    </div>
  );
}
