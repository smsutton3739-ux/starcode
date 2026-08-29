import Link from "next/link";

export const metadata = {
  title: "Terms",
  description:
    "What Starcode is, what it is not, and what you can expect from it. The limits stated here are the same ones enforced in the code.",
};

/**
 * Terms of use.
 *
 * Deliberately short, and deliberately consistent with the epistemic contract rather than
 * pretending to more authority than the product claims elsewhere. A terms page that
 * quietly disclaimed everything would sit oddly beside a README whose whole argument is
 * that this tool tells you exactly how much to trust each sentence.
 */

export default function TermsPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16">
      <p className="eyebrow">Terms</p>
      <h1 className="mt-3 font-display text-4xl">Terms of use</h1>

      <p className="mt-5 text-lg text-ink-600 dark:text-ink-300">
        Starcode is a research aid. It is not a scholarly authority, and nothing it
        produces should be cited as one without checking the sources it names.
      </p>

      <section className="prose-report mt-10 space-y-4">
        <h2 className="font-display text-2xl">What you can expect</h2>
        <p>
          Every statement in a report is labelled by kind. Calculations are reproducible
          and name the algorithm that produced them. Claims that require a citation cannot
          be stored without one. Model conjecture is capped in confidence and marked as not
          evidence. Those are properties of the software, not promises about tone — they
          are described in <Link href="/about">how it works</Link>.
        </p>
        <p>
          What that does <em>not</em> mean is that everything here is correct. Dating is
          disputed for most ancient material, translations of ancient languages are
          uncertain, the reference corpus is a small demonstration set, and planetary
          positions are approximations. Where the platform knows it is uncertain it says
          so; it cannot know everything it does not know.
        </p>

        <h2 className="mt-10 font-display text-2xl">What it will not do</h2>
        <p>
          Starcode does not adjudicate religious or interpretive questions. It reports what
          traditions have held and what scholars argue, attributed. It makes no claims
          about future events, and a prophetic reading is never presented as a prediction.
        </p>

        <h2 className="mt-10 font-display text-2xl">Your text</h2>
        <p>
          You keep whatever rights you have in the text you submit. Submitting it grants us
          only what running the analysis requires — storing it, processing it, and showing
          you the result. Do not submit material you have no right to, and do not submit
          anything you would be unwilling to have processed by a third-party model
          provider; the <Link href="/privacy">privacy page</Link> says exactly who sees
          what.
        </p>

        <h2 className="mt-10 font-display text-2xl">Accounts and fair use</h2>
        <p>
          Requests are rate limited. Do not attempt to circumvent those limits, extract the
          corpus wholesale, or use the service to generate material presented as
          authoritative scholarship that it is not. An account may be suspended for any of
          those.
        </p>

        <h2 className="mt-10 font-display text-2xl">Availability</h2>
        <p>
          This service runs on free infrastructure. It sleeps when idle and takes a
          noticeable moment to wake. There is no uptime guarantee, and you should keep your
          own copy of anything that matters to you — every report can be exported as PDF,
          DOCX, CSV, Markdown or JSON, and every format keeps the claim-type labelling.
        </p>

        <h2 className="mt-10 font-display text-2xl">Liability</h2>
        <p>
          The service is provided as is, without warranty. Decisions you make on the basis
          of a report are yours. Given what this tool is for, that is worth stating
          concretely: do not rely on it for anything where being wrong about an ancient
          date, an astronomical event or a contested reading would cause you real harm.
        </p>

        <h2 className="mt-10 font-display text-2xl">Contact</h2>
        <p>
          <a href="mailto:smsutton3739@gmail.com" className="underline underline-offset-4">
            smsutton3739@gmail.com
          </a>
        </p>
      </section>

      <p className="mt-12 rounded-lg border border-ink-200 bg-ink-50 p-4 text-sm text-ink-600 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-400">
        Plain-language terms describing how this service actually behaves. Not legal
        advice, and not reviewed by a lawyer.
      </p>

      <p className="mt-8">
        <Link href="/" className="text-sm underline underline-offset-4">
          Back to Starcode
        </Link>
      </p>
    </div>
  );
}
