import Link from "next/link";

export const metadata = {
  title: "Privacy",
  description:
    "What Starcode stores, why, and how to get rid of it. Written from what the code actually does.",
};

/**
 * The privacy policy.
 *
 * Every factual claim here was written against the code rather than from a template, and
 * the ones most likely to drift are noted with where they live:
 *
 *   - OAuth profile fields          backend/app/api/v1/routers/auth.py (the callback)
 *   - requested scopes              PROVIDERS in that same file
 *   - hashed IPs in the audit trail backend/app/core/security.py, hash_ip
 *   - anonymous capability token    Analysis.anonymous_token_hash
 *   - cascade deletion on account   the relationships on User
 *
 * If any of those change, this page is wrong until it is changed too. Google requires a
 * reachable privacy policy before an OAuth consent screen can be published, so this is
 * load-bearing for sign-in, not decoration.
 */

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-16">
      <p className="eyebrow">Privacy</p>
      <h1 className="mt-3 font-display text-4xl">What we store, and why</h1>

      <p className="mt-5 text-lg text-ink-600 dark:text-ink-300">
        Short version: you can use Starcode without an account, and without telling us who
        you are. If you make an account, we keep your email address, your display name and
        the analyses you ran. We do not sell anything to anyone.
      </p>

      <section className="prose-report mt-10 space-y-4">
        <h2 className="font-display text-2xl">If you never sign in</h2>
        <p>
          Analysing a text needs no account. When you submit one we store the text itself,
          along with the report produced from it, because that is the thing you came back
          to read.
        </p>
        <p>
          Access to that report is held by a <strong>capability token</strong> kept in your
          own browser. We store only a hash of it, which means we can check a token you
          present but cannot produce one ourselves. The practical consequence is worth
          stating plainly: <strong>if you clear your browser storage, that analysis is
          unreachable — by you and by us.</strong> There is no recovery, because there is
          no account it belongs to.
        </p>

        <h2 className="mt-10 font-display text-2xl">If you sign in with Google or GitHub</h2>
        <p>
          We ask the provider for the narrowest thing that works: your basic profile and
          your email address (<code className="font-mono text-sm">openid email profile</code>{" "}
          on Google, <code className="font-mono text-sm">read:user user:email</code> on
          GitHub). We never ask for, and cannot read, your mail, files, calendar,
          repositories or contacts.
        </p>
        <p>From what the provider returns, we keep:</p>
        <ul className="ml-6 list-disc space-y-1">
          <li>your email address</li>
          <li>your display name</li>
          <li>your avatar image URL</li>
          <li>
            the provider&rsquo;s account identifier, so we can recognise you next time
          </li>
        </ul>
        <p>
          We never receive your password. We do not store an access token for the provider
          after sign-in completes, and we do not act on your behalf there afterwards.
        </p>

        <h2 className="mt-10 font-display text-2xl">What an account accumulates</h2>
        <p>
          The texts you submit, the reports produced from them, any files you upload for
          text extraction, your saved collections and tags, and your settings. That is the
          product working as intended — an account exists so your analyses persist and can
          be searched.
        </p>

        <h2 className="mt-10 font-display text-2xl">Security and abuse records</h2>
        <p>
          We keep an append-only record of actions that change data or read someone
          else&rsquo;s, so an incident can be reconstructed. It stores{" "}
          <strong>a hash of your IP address rather than the address itself</strong> —
          enough to notice that many requests came from one source, not enough to identify
          a person from the record. Your browser&rsquo;s user-agent string is stored
          alongside it.
        </p>

        <h2 className="mt-10 font-display text-2xl">Who else sees your text</h2>
        <p>
          When an interpretive analysis runs, the relevant portion of your text is sent to{" "}
          <strong>Anthropic</strong> for processing. The deterministic half of the
          platform — language detection, entity extraction, calendar conversion and the
          whole astronomy engine — runs here and sends your text nowhere.
        </p>
        <p>
          The <Link href="/tools">chart tools page</Link> embeds a third-party widget from
          Astro&middot;Charts. Anything you type into those charts goes to them, not to us,
          and that page says so where you can see it. The embed is confined to that one
          page and cannot read any other.
        </p>
        <p>
          Our hosting providers necessarily process data in the course of running the
          service.
        </p>

        <h2 className="mt-10 font-display text-2xl">Getting rid of it</h2>
        <p>
          Deleting an analysis deletes its text, its report and its claims. Deleting your
          account removes everything attached to it — analyses, documents, uploads,
          collections, settings and linked sign-in identities — by cascade, in the same
          operation.
        </p>
        <p>
          The security record above is the deliberate exception: it survives account
          deletion, because a trail that disappears when the account does is not a trail.
          It holds the email address that acted, not the account.
        </p>
        <p>
          To delete an account, email the address below. If you signed in with a provider,
          revoking Starcode&rsquo;s access in your Google or GitHub settings stops future
          sign-ins but does not by itself delete what is stored here — ask us for that.
        </p>

        <h2 className="mt-10 font-display text-2xl">Cookies</h2>
        <p>
          There is no advertising or analytics tracking on this site. Sign-in state and
          your anonymous capability tokens are kept in your browser&rsquo;s own storage,
          and your theme preference alongside them.
        </p>

        <h2 className="mt-10 font-display text-2xl">Contact</h2>
        <p>
          Questions, corrections, or a deletion request:{" "}
          <a href="mailto:smsutton3739@gmail.com" className="underline underline-offset-4">
            smsutton3739@gmail.com
          </a>
          .
        </p>
      </section>

      <p className="mt-12 rounded-lg border border-ink-200 bg-ink-50 p-4 text-sm text-ink-600 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-400">
        This page describes what the software does, accurately and in plain terms. It is
        not legal advice, and it is not a substitute for a policy reviewed by a lawyer
        against the obligations that apply where you and your users live.
      </p>

      <p className="mt-8">
        <Link href="/" className="text-sm underline underline-offset-4">
          Back to Starcode
        </Link>
      </p>
    </div>
  );
}
