"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiRequestError, authCapabilities, login, oauthUrl, register } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [providers, setProviders] = useState<Array<{ name: string; configured: boolean }>>([]);
  // Null until known, so the form is not rendered and then yanked away.
  const [canRegister, setCanRegister] = useState<boolean | null>(null);
  const [registrationNote, setRegistrationNote] = useState<string | null>(null);

  useEffect(() => {
    authCapabilities()
      .then((data) => {
        setProviders(data.providers);
        setCanRegister(data.password_registration_enabled);
        setRegistrationNote(data.note);
        if (!data.password_registration_enabled) setMode("login");
      })
      .catch(() => {
        setProviders([]);
        setCanRegister(false);
      });
  }, []);

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

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">
        {mode === "login" ? "Sign in" : "Create an account"}
      </h1>
      <p className="mt-2 text-sm text-ink-600 dark:text-ink-400">
        An account saves your analyses and lets you search across them. You can analyse
        texts without one.
      </p>

      {configured.length > 0 && (
        <>
          <div className="mt-6 space-y-2">
            {configured.map((provider) => (
              <a key={provider.name} href={oauthUrl(provider.name)} className="btn-secondary w-full">
                Continue with {provider.name[0]!.toUpperCase() + provider.name.slice(1)}
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

      <form onSubmit={submit} className="mt-6 space-y-4">
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
            <span id="email-error" className="mt-1 block text-sm text-crimson-700 dark:text-crimson-400">
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
            <span id="password-error" className="mt-1 block text-sm text-crimson-700 dark:text-crimson-400">
              {fieldErrors.password.join(" ")}
            </span>
          )}
        </label>

        {error && (
          <p role="alert" className="rounded-lg border border-crimson-300 bg-crimson-50 p-3 text-sm text-crimson-900 dark:border-crimson-800 dark:bg-crimson-950 dark:text-crimson-200">
            {error}
          </p>
        )}

        <button type="submit" disabled={busy} className="btn-primary w-full">
          {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>

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

      <p className="mt-8 text-center">
        <Link href="/" className="text-sm text-ink-500 underline-offset-4 hover:underline dark:text-ink-400">
          Continue without an account
        </Link>
      </p>
    </div>
  );
}
