import Link from "next/link";

export const metadata = {
  title: "Pricing",
  description:
    "What each plan includes. The deterministic half of every analysis — language, entities, calendars and the full astronomy engine — is free and always will be.",
};

/**
 * The plan comparison.
 *
 * Written to be checkable rather than persuasive, which is the same standard the reports
 * are held to. The free column lists what it genuinely includes rather than what it
 * lacks, because the deterministic half of this product is the half that can be verified
 * and it is not a teaser — it is the part the platform is most confident about.
 */

type Plan = {
  name: string;
  price: string;
  cadence?: string;
  summary: string;
  includes: string[];
  excludes?: string[];
  cta: { label: string; href: string } | null;
  featured?: boolean;
  note?: string;
};

const PLANS: Plan[] = [
  {
    name: "Free",
    price: "£0",
    summary:
      "Everything the platform can compute rather than infer. No account needed to start.",
    includes: [
      "Language and script detection",
      "People, places, symbols and sacred numbers",
      "Date parsing across twelve calendar systems",
      "The full astronomy engine — eclipses, phases, conjunctions, planetary positions",
      "Corpus matching with real citations",
      "Every export format: PDF, DOCX, CSV, Markdown, JSON",
    ],
    excludes: [
      "Traditional interpretations",
      "Scholarly positions",
      "AI hypotheses and alternative readings",
    ],
    cta: { label: "Analyse a text", href: "/" },
  },
  {
    name: "Paid",
    price: "£9",
    cadence: "/month",
    summary:
      "Adds the interpretive sections: what traditions have held, what scholars argue, and where the analysis is willing to conjecture.",
    includes: [
      "Everything in Free",
      "Traditional interpretations, attributed",
      "Modern scholarly positions, with the disagreements reported",
      "AI hypotheses — confidence capped by policy, never presented as findings",
      "The full executive summary",
    ],
    cta: { label: "Subscribe", href: "/billing" },
    featured: true,
  },
  {
    name: "Bring your own key",
    price: "£0",
    summary:
      "Supply your own Anthropic API key and pay Anthropic directly for the model calls.",
    includes: [
      "Everything in Paid",
      "Your key is used per request and never stored — only its last four characters, so you can tell which key is in use",
    ],
    cta: null,
    note: "Coming soon.",
  },
];

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-16">
      <p className="eyebrow">Plans</p>
      <h1 className="mt-3 text-4xl font-normal tracking-tight sm:text-5xl">
        Pay for the interpretation.
        <br />
        The <em className="italic text-gold-600 dark:text-gold-400">calculation</em> is free.
      </h1>
      <p className="mt-5 max-w-2xl text-lg text-ink-600 dark:text-ink-300">
        Everything this platform can compute — the astronomy, the calendars, the extraction,
        the corpus citations — costs nothing and needs no account. What a subscription adds
        is the part a language model produced: how traditions have read a text, what scholars
        argue about it, and where the analysis is prepared to speculate.
      </p>

      <div className="mt-12 grid gap-6 md:grid-cols-3">
        {PLANS.map((plan) => (
          <section
            key={plan.name}
            className={`card flex flex-col p-6 ${
              plan.featured
                ? "border-lapis-400 ring-1 ring-lapis-400 dark:border-lapis-500 dark:ring-lapis-500"
                : ""
            }`}
            aria-labelledby={`plan-${plan.name.replace(/\s+/g, "-").toLowerCase()}`}
          >
            <h2
              id={`plan-${plan.name.replace(/\s+/g, "-").toLowerCase()}`}
              className="font-display text-2xl"
            >
              {plan.name}
            </h2>

            <p className="mt-3">
              <span className="font-display text-3xl">{plan.price}</span>
              {plan.cadence && (
                <span className="text-sm text-ink-500 dark:text-ink-400">{plan.cadence}</span>
              )}
            </p>

            <p className="mt-3 text-sm text-ink-600 dark:text-ink-300">{plan.summary}</p>

            <ul className="mt-5 space-y-2 text-sm">
              {plan.includes.map((item) => (
                <li key={item} className="flex gap-2">
                  {/* Icon plus text, never colour alone — the accessibility suite checks
                      that every distinction survives with colour stripped out. */}
                  <span aria-hidden="true" className="text-verdigris-600 dark:text-verdigris-400">
                    ✓
                  </span>
                  <span className="text-ink-700 dark:text-ink-300">
                    <span className="sr-only">Included: </span>
                    {item}
                  </span>
                </li>
              ))}
              {plan.excludes?.map((item) => (
                <li key={item} className="flex gap-2">
                  <span aria-hidden="true" className="text-ink-400 dark:text-ink-500">
                    🔒
                  </span>
                  <span className="text-ink-500 dark:text-ink-400">
                    <span className="sr-only">Locked: </span>
                    {item}
                  </span>
                </li>
              ))}
            </ul>

            <div className="mt-6 flex-1" />

            {plan.cta ? (
              <Link href={plan.cta.href} className={plan.featured ? "btn-primary" : "btn-secondary"}>
                {plan.cta.label}
              </Link>
            ) : (
              <p className="rounded-md border border-dashed border-ink-300 px-3 py-2 text-center text-sm text-ink-500 dark:border-ink-700 dark:text-ink-400">
                {plan.note}
              </p>
            )}
          </section>
        ))}
      </div>

      <section className="mt-16 max-w-2xl">
        <h2 className="font-display text-2xl">What a subscription does not change</h2>
        <p className="mt-3 text-ink-600 dark:text-ink-300">
          Paying does not make the platform more certain. Interpretive claims stay labelled
          as interpretation, AI hypotheses stay capped in confidence and marked as not
          evidence, and a locked claim is locked rather than absent — you can always see
          that it exists, what kind of claim it is, and how many sources it cites. Nothing
          here adjudicates a religious or interpretive question, on any plan.
        </p>
        <p className="mt-4 text-sm text-ink-500 dark:text-ink-400">
          Read{" "}
          <Link href="/about" className="underline underline-offset-4">
            how the claim types work
          </Link>{" "}
          before deciding whether the interpretive half is worth it to you.
        </p>
      </section>
    </div>
  );
}
