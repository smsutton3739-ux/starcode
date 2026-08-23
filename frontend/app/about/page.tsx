import Link from "next/link";

export const metadata = { title: "How it works" };

// These hex values are the claim palette and MUST stay in sync with the `claim.*`
// tokens in tailwind.config.ts and `tone_colors` in backend/app/services/export.py —
// three independent renderers (this page, the live report UI, and PDF/DOCX exports)
// all need to agree on what each claim type looks like.
const CLAIM_TYPES = [
  ["Source text", "Quoted verbatim from what you submitted. No interpretation added.", "#494A50"],
  ["Verified history", "Attested in the historical record and citable. Requires a real citation to exist at all.", "#256149"],
  ["Calculation", "Computed by the ephemeris and calendar engines. Reproducible, and reported with its accuracy.", "#2E5AA8"],
  ["Text analysis", "An observation about the text itself — its language, structure or vocabulary.", "#216568"],
  ["Tradition holds", "What a religious or cultural tradition has understood this to mean. Reported, not endorsed.", "#855A1C"],
  ["Scholars argue", "A position argued in academic literature. Where scholars disagree, the disagreement is reported.", "#563E74"],
  ["AI hypothesis", "Model-generated conjecture. Not evidence. Confidence is capped by design.", "#8E4325"],
  ["Unresolved", "Genuinely undetermined on the available evidence.", "#656257"],
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">How Starcode works</h1>

      <section className="mt-8">
        <h2 className="text-xl font-semibold">The rule everything is built around</h2>
        <p className="prose-report mt-3">
          Speculation is never presented as established fact. That is not a matter of
          careful wording — wording drifts, and a confident sentence reads the same
          whether or not anything backs it. So it is enforced structurally: every
          statement the platform makes is stored with an explicit type, and the rules for
          each type are checked in code before anything reaches you.
        </p>
        <p className="prose-report mt-3">
          A claim typed as verified history <em>cannot exist</em> without a citation. If
          the model produces one anyway, it is downgraded to a hypothesis and the
          downgrade is recorded. A calculation must name the engine and algorithm that
          produced it. Confidence for AI hypotheses is clamped, so a model cannot talk its
          way into certainty about an interpretive question.
        </p>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">The eight kinds of statement</h2>
        <ul className="mt-4 space-y-3">
          {CLAIM_TYPES.map(([label, description, color]) => (
            <li key={label} className="flex gap-4 rounded-lg border-l-4 bg-ink-50 p-4 dark:bg-ink-900" style={{ borderLeftColor: color }}>
              <div>
                <p className="font-medium">{label}</p>
                <p className="mt-1 text-sm text-ink-600 dark:text-ink-400">{description}</p>
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-sm text-ink-600 dark:text-ink-400">
          The first three are <strong>evidence</strong>. The rest are commentary, however
          plausible. Reports separate them, and you can filter to evidence alone.
        </p>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">What actually runs</h2>
        <p className="prose-report mt-3">
          Eight specialist steps run in order: language and translation, source
          identification, entity extraction, calendar conversion, astronomical
          correlation, historical context, interpretation, and an evidence audit that
          checks the other seven.
        </p>
        <p className="prose-report mt-3">
          The calendar and astronomy steps consult no language model at all. Their output
          is arithmetic — Meeus&apos; algorithms for eclipses and lunar phases, the JPL
          Keplerian approximation for planets, Rata Die day-numbering for calendars —
          and routing that through a model would add nothing but a way for it to be wrong.
        </p>
        <p className="prose-report mt-3">
          Every report carries a trace: which step produced each finding, on which model,
          how long it took, and its own account of how it reached its conclusion.
        </p>
      </section>

      <section className="mt-10" id="limitations">
        <h2 className="text-xl font-semibold">What this cannot do</h2>
        <p className="prose-report mt-3">
          Stated plainly, so nothing here is mistaken for an oversight.
        </p>
        <ul className="prose-report mt-4 list-disc space-y-3 pl-6">
          <li>
            <strong>It does not compute eclipse visibility from a named place.</strong> It
            establishes that an eclipse occurred, when, and of what type. For ancient
            dates the uncertainty in the Earth&apos;s rotation (ΔT) is tens of minutes,
            which moves the ground track by tens of degrees of longitude. Any tool showing
            you a precise ancient eclipse path is overselling its precision.
          </li>
          <li>
            <strong>Planetary positions are approximations.</strong> Accurate to roughly
            0.3–0.6° over five millennia. For a slow pair like Jupiter and Saturn that
            translates into about two weeks of uncertainty in the date of a conjunction —
            which each result tells you.
          </li>
          <li>
            <strong>It does not adjudicate religious or interpretive questions.</strong> It
            reports what traditions have held and what scholars argue, attributed and
            sourced. It does not rule on which reading is correct.
          </li>
          <li>
            <strong>It makes no claims about the future.</strong> Prophetic material is
            described and interpretations are attributed, but a prediction is never
            presented as a fact about what will happen.
          </li>
          <li>
            <strong>The reference corpus is a demonstration set.</strong> A few dozen
            curated works. If your text is not in it, that says nothing about your text.
          </li>
          <li>
            <strong>Model-supplied citations are marked unverified.</strong> Language
            models invent references that look real. Anything not drawn from the curated
            corpus is labelled, and should be confirmed before you cite it.
          </li>
        </ul>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">Privacy</h2>
        <p className="prose-report mt-3">
          You can analyse a text without an account. Anonymous analyses are reachable only
          via a token stored in your browser — if you clear your browser storage, that
          analysis genuinely becomes unreachable, because there is no account to tie it
          to. That is the price of not requiring a signup, and it is worth knowing before
          you rely on it.
        </p>
      </section>

      <div className="mt-12 flex gap-3">
        <Link href="/" className="btn-primary">Analyse a text</Link>
        <Link href="/explore" className="btn-secondary">Try the astronomy tools</Link>
      </div>
    </div>
  );
}
