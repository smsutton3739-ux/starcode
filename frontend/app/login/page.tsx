"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiRequestError, authCapabilities, login, oauthUrl, register } from "@/lib/api";

/**
 * Sign in, and the honest version of "you cannot".
 *
 * A deployment can end up with no way for a visitor to create an account at all: password
 * registration is off by default (there is no reset flow, and an unrecoverable account is
 * worse than none), and OAuth only works once a provider is configured. If neither is
 * available this page used to render a password form above a note saying password
 * accounts were disabled — a dead end that read as a contradiction, and that a visitor
 * could only resolve by giving up.
 *
 * The form is not removed in that state, because operator-created accounts
 * (backend/scripts/create_admin.py) are real and still sign in with a password. It moves
 * behind a disclosure instead, so the page leads with what a visitor can actually do.
 */

type Provider = { name: string; configured: boolean };

function providerLabel(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [providers, setProviders] = useState<Provider[]>([]);
  // Null until known, so the form is not rendered and then yanked away.
  const [canRegister, setCanRegister] = useState<boolean | null>(null);
  const [registrationNote, setRegistrationNote] = useState<string | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  // Distinct from "checked, and there is nothing" — see the effect below.
  const [unreachable, setUnreachable] = useState(false);
  const [checking, setChecking] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    // Read from window rather than useSearchParams: the latter forces this page into a
    // Suspense boundary or dynamic rendering, and all that is wanted is one line of
    // explanation for someone who arrived here from a button they pressed elsewhere.
    const params = new URLSearchParams(window.location.search);
    setReason(params.get("reason"));
  }, []);

  useEffect(() => {
    // "I could not ask" is not "there is nothing to offer", and this page used to
    // conflate them: a failed capabilities call set canRegister=false, which is exactly
    // the condition that renders "New accounts are not available yet" — so a visitor was
    // told sign-in did not exist when the truth was that the server had not answered.
    //
    // It fails routinely rather than rarely. The API runs on an instance that sleeps
    // after about fifteen minutes idle and takes the better part of a minute to wake, so
    // the first visitor after a quiet spell is the one who gets told, wrongly, that
    // there is no way in. Hence the retries: three attempts over roughly forty seconds
    // covers a cold start, and only after all of them do we admit we could not reach it.
    let cancelled = false;
    const delays = [0, 4000, 12000, 24000];

    (async () => {
      setChecking(true);
      for (let i = 0; i < delays.length; i += 1) {
        if (cancelled) return;
        if (delays[i]) await new Promise((r) => setTimeout(r, delays[i]));
        try {
          const data = await authCapabilities();
          if (cancelled) return;
          setProviders(data.providers);
          setCanRegister(data.password_registration_enabled);
          setRegistrationNote(data.note);
          if (!data.password_registration_enabled) setMode("login");
          setUnreachable(false);
          setChecking(false);
          return;
        } catch {
          // Keep trying; the last failure falls through to the unreachable state.
        }
      }
      if (cancelled) return;
      setUnreachable(true);
      setChecking(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
      router.push("/dashboard");
    } catch (cause) {
      if (cause instanceof ApiRequestError) {
        setError(cause.message);
        setFieldErrors(cause.fieldErrors);
      } else {
        setError("Something went wrong. Try again.");
      }
      setBusy(false);
    }
  };

  const configured = providers.filter((provider) => provider.configured);
  const loading = checking;

  // Nobody can create an account here: no provider to sign in with, and password
  // registration refused by the API. Requires having actually heard from the API —
  // `unreachable` is handled separately, because a server that did not answer tells you
  // nothing about what it offers.
  const noWayIn =
    !loading && !unreachable && configured.length === 0 && canRegister === false;

  const credentialsForm = (
    <form onSubmit={submit} className="space-y-4">
      <label className="block">
        <span className="text-sm font-medium">Email</span>
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          autoComplete="email"
          className="input mt-1"
          aria-invalid={Boolean(fieldErrors.email)}
          aria-describedby={fieldErrors.email ? "email-error" : undefined}
        />
        {fieldErrors.email && (
          <span
            id="email-error"
            className="mt-1 block text-sm text-crimson-700 dark:text-crimson-400"
          >
            {fieldErrors.email.join(" ")}
          </span>
        )}
      </label>

      <label className="block">
        <span className="text-sm font-medium">Password</span>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          minLength={mode === "register" ? 12 : undefined}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          className="input mt-1"
          aria-invalid={Boolean(fieldErrors.password)}
          aria-describedby={fieldErrors.password ? "password-error" : "password-help"}
        />
        {mode === "register" && (
          <span id="password-help" className="mt-1 block text-xs text-ink-500 dark:text-ink-400">
            At least 12 characters. Length matters far more than symbols — a memorable
            phrase beats a short scramble.
          </span>
        )}
        {fieldErrors.password && (
          <span
            id="password-error"
            className="mt-1 block text-sm text-crimson-700 dark:text-crimson-400"
          >
            {fieldErrors.password.join(" ")}
          </span>
        )}
      </label>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-crimson-300 bg-crimson-50 p-3 text-sm text-crimson-900 dark:border-crimson-800 dark:bg-crimson-950 dark:text-crimson-200"
        >
          {error}
        </p>
      )}

      <button type="submit" disabled={busy} className="btn-primary w-full">
        {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
      </button>
    </form>
  );

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        {mode === "login" ? "Sign in" : "Create an account"}
      </h1>
      <p className="mt-2 text-sm text-ink-600 dark:text-ink-400">
        An account saves your analyses and lets you search across them. You can analyse
        texts without one.
      </p>

      {reason === "dating" && (
        <p
          className="mt-4 rounded-lg border border-lapis-300 bg-lapis-50 p-3 text-sm text-lapis-900 dark:border-lapis-700 dark:bg-lapis-950 dark:text-lapis-200"
          role="status"
        >
          Astronomical dating needs an account — the free allowance of five searches is
          counted per account, so there is no anonymous path for it. Ordinary analysis
          still works without signing in.
        </p>
      )}

      {loading && (
        <p className="mt-6 text-sm text-ink-500 dark:text-ink-400" role="status">
          Checking which sign-in methods are available… The server sleeps when idle, so
          this can take up to a minute.
        </p>
      )}

      {!loading && unreachable && (
        <div
          className="mt-6 rounded-lg border border-gold-300 bg-gold-50/70 p-4 dark:border-gold-700 dark:bg-gold-950/30"
          role="status"
        >
          <p className="flex items-center gap-2 font-medium text-gold-900 dark:text-gold-200">
            <span aria-hidden="true">ⓘ</span>
            Could not reach the server
          </p>
          <p className="mt-2 text-sm text-ink-700 dark:text-ink-300">
            This is almost always the API waking from sleep rather than anything being
            wrong. Sign-in options cannot be listed until it answers — so none are shown
            below, and that is not a statement that none exist.
          </p>
          <button
            type="button"
            onClick={() => setAttempt((n) => n + 1)}
            className="btn-secondary mt-4"
          >
            Try again
          </button>
        </div>
      )}

      {!loading && noWayIn && (
        <>
          <div className="mt-6 rounded-lg border border-gold-300 bg-gold-50/70 p-4 dark:border-gold-700 dark:bg-gold-950/30">
            <p className="flex items-center gap-2 font-medium text-gold-900 dark:text-gold-200">
              {/* Icon and text together — the accessibility suite checks that meaning
                  survives with all colour stripped out. */}
              <span aria-hidden="true">ⓘ</span>
              New accounts are not available yet
            </p>
            <p className="mt-2 text-sm text-ink-700 dark:text-ink-300">
              This deployment has no sign-in provider configured, and password accounts are
              switched off because there is no way to reset a forgotten password. Nothing is
              broken and nothing is missing from the analysis itself — an account only saves
              your work and lets you search across it.
            </p>
          </div>

          <Link href="/" className="btn-primary mt-6 block w-full text-center">
            Analyse a text without an account
          </Link>

          <p className="mt-3 text-xs text-ink-500 dark:text-ink-400">
            Your result is kept in this browser. Clearing site data loses access to it,
            because there is no account to attach it to.
          </p>

          {/* Operator-created accounts are real and still sign in with a password, so the
              form stays reachable — just not as the first thing a visitor meets. */}
          <details className="mt-8 rounded-lg border border-ink-200 p-4 dark:border-ink-800">
            <summary className="cursor-pointer text-sm font-medium">
              I already have an account
            </summary>
            <div className="mt-4">{credentialsForm}</div>
          </details>
        </>
      )}

      {!loading && !noWayIn && (
        <>
          {configured.length > 0 && (
            <>
              <div className="mt-6 space-y-2">
                {configured.map((provider) => (
                  <a
                    key={provider.name}
                    href={oauthUrl(provider.name)}
                    className="btn-secondary w-full"
                  >
                    Continue with {providerLabel(provider.name)}
                  </a>
                ))}
              </div>
              <div className="my-6 flex items-center gap-3 text-xs uppercase tracking-wide text-ink-400">
                <span className="h-px flex-1 bg-ink-200 dark:bg-ink-800" />
                or
                <span className="h-px flex-1 bg-ink-200 dark:bg-ink-800" />
              </div>
            </>
          )}

          <div className="mt-6">{credentialsForm}</div>

          {canRegister && (
            <p className="mt-6 text-center text-sm text-ink-600 dark:text-ink-400">
              {mode === "login" ? "No account yet? " : "Already have an account? "}
              <button
                type="button"
                onClick={() => {
                  setMode(mode === "login" ? "register" : "login");
                  setError(null);
                  setFieldErrors({});
                }}
                className="font-medium text-lapis-700 underline-offset-4 hover:underline dark:text-lapis-400"
              >
                {mode === "login" ? "Create one" : "Sign in"}
              </button>
            </p>
          )}

          {canRegister === false && registrationNote && (
            <p className="mt-6 rounded-lg border border-ink-200 bg-ink-50 p-3 text-center text-xs text-ink-600 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-400">
              {registrationNote}
            </p>
          )}
        </>
      )}

      <p className="mt-8 text-center">
        <Link
          href="/"
          className="text-sm text-ink-500 underline-offset-4 hover:underline dark:text-ink-400"
        >
          Continue without an account
        </Link>
      </p>
    </div>
  );
}
