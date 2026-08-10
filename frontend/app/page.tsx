import { AnalyzeBox } from "@/components/AnalyzeBox";
import { Logo } from "@/components/Logo";

/**
 * The homepage.
 *
 * Large logo. One sentence. One large text box. One button.
 *
 * Everything else on this page is below the fold or hidden behind a disclosure. The
 * measure of success here is that a visitor who has never seen the product can paste
 * something and press ANALYZE without reading anything first.
 */
export default function HomePage() {
  return (
    <div className="mx-auto max-w-3xl px-4 pb-20 pt-10 sm:pt-16">
      <div className="animate-fade-in text-center">
        <Logo className="mx-auto h-20 w-20 sm:h-24 sm:w-24" />
        <h1 className="mt-5 text-4xl font-semibold tracking-tight sm:text-5xl">
          Starcode
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-lg text-slate-600 dark:text-slate-300">
          Paste any ancient text, manuscript, prophecy, or historical document.
        </p>
      </div>

      <AnalyzeBox />

      <section
        className="mt-16 border-t border-slate-200 pt-10 dark:border-slate-800"
        aria-labelledby="what-you-get"
      >
        <h2
          id="what-you-get"
          className="text-center text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
        >
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
              <h3 className="font-medium">{item.title}</h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{item.body}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
