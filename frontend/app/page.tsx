import { AnalyzeBox } from "@/components/AnalyzeBox";
import { Logo } from "@/components/Logo";

/**
 * The homepage.
 *
 * Large logo. One sentence. One large text box. One button.
 *
 * Everything else on this page is below the fold or hidden behind a disclosure. The
 * measure of success here is that a visitor who has never seen the product can paste
 * something and press ANALYZE without reading anything first. The AnalyzeBox therefore
 * stays immediately below the headline — the tablet-split illustration further down is
 * supporting evidence for a visitor who scrolls, not a detour before the real tool.
 */
export default function HomePage() {
  return (
    <div className="mx-auto max-w-3xl px-4 pb-24 pt-10 sm:pt-16">
      <div className="animate-fade-in text-center">
        <Logo className="mx-auto h-20 w-20 sm:h-24 sm:w-24" />
        <p className="eyebrow mt-5">Ancient text &amp; sky analysis</p>
        <h1 className="mt-3 text-5xl font-normal tracking-tight sm:text-6xl">
          Paste the text.
          <br />
          Read the <em className="italic text-gold-600 dark:text-gold-400">sky</em> behind it.
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-lg text-ink-600 dark:text-ink-300">
          Paste an ancient text, manuscript, prophecy, or historical document. Every
          finding in the report is labelled with what it rests on, so you can check it.
        </p>
      </div>

      <AnalyzeBox />

      <section className="mt-20" aria-labelledby="how-it-reads">
        <h2 id="how-it-reads" className="eyebrow text-center">
          How a finding reads
        </h2>
        <p className="mx-auto mt-3 max-w-lg text-center text-sm text-ink-600 dark:text-ink-400">
          Every result is split the same way: what the text or the sky actually shows,
          and what that has been read to mean.
        </p>

        <div
          className="tablet mt-6"
          role="img"
          aria-label="Example split between an established fact and its interpretation"
        >
          <div className="tablet-half">
            <span className="eyebrow !text-ink-500 dark:!text-ink-400">Established</span>
            <p className="mt-2 font-display text-xl leading-snug sm:text-2xl">
              A total lunar eclipse occurred on 15 June 763 BCE, computed from the Meeus
              lunar algorithm.
            </p>
          </div>
          <div className="tablet-wedge" aria-hidden="true" />
          <div className="tablet-half">
            <span className="eyebrow !text-ink-500 dark:!text-ink-400">Interpreted</span>
            <p className="mt-2 font-display text-xl leading-snug sm:text-2xl">
              Assyriology has long associated this eclipse with the Bur-Sagale revolt
              recorded in the Assyrian eponym canon.
            </p>
          </div>
        </div>
      </section>

      <section
        className="mt-16 border-t border-ink-200 pt-10 dark:border-ink-800"
        aria-labelledby="what-you-get"
      >
        <h2 id="what-you-get" className="eyebrow text-center">
          What you get back
        </h2>
        <div className="mt-6 grid gap-5 sm:grid-cols-3">
          {[
            {
              title: "Everything is labelled",
              body: "Each finding is marked as source text, a calculation, verified history, a tradition's reading, scholarship, or an AI hypothesis. Speculation is never dressed up as fact.",
            },
            {
              title: "Real astronomy",
              body: "Eclipses, moon phases, planetary positions and conjunctions are computed from published algorithms, with the accuracy of each result stated alongside it.",
            },
            {
              title: "Dates you can check",
              body: "Twelve calendar systems convert to Gregorian dates. Where an exact conversion is impossible, the report says so and explains exactly what is blocking it.",
            },
          ].map((item) => (
            <div key={item.title} className="card p-5">
              <h3 className="font-display text-lg font-normal">{item.title}</h3>
              <p className="mt-2 text-sm text-ink-600 dark:text-ink-400">{item.body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
