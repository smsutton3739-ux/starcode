"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiRequestError, createCheckoutSession, createPortalSession, getBillingStatus } from "@/lib/api";
import type { BillingStatus } from "@/lib/types";

/**
 * The account's own billing page.
 *
 * Deliberately unopinionated about *why* a state exists: it reports the tier and Stripe's
 * own status string rather than translating them into reassurance. A subscription that is
 * `past_due` still says so, even though access continues, because a customer whose card
 * is failing should find that out here rather than when access stops.
 */

const TIER_LABELS: Record<string, string> = {
  free: "Free",
  paid: "Paid",
  byok: "Bring your own key",
};

/** Stripe's statuses, explained in the reader's terms rather than passed through raw. */
const STATUS_NOTES: Record<string, string> = {
  active: "Your subscription is active.",
  trialing: "You are in a trial period.",
  past_due:
    "A payment failed and Stripe is retrying your card. Access continues for now. Update your card in the portal to avoid losing it.",
  canceled: "This subscription has been cancelled.",
  unpaid: "Payment retries were exhausted, so the subscription lapsed.",
  incomplete: "Checkout was started but never completed.",
  incomplete_expired: "Checkout was started and expired before it completed.",
};

export default function BillingPage() {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"checkout" | "portal" | null>(null);
  const [needsSignIn, setNeedsSignIn] = useState(false);

  const load = useCallback(async () => {
    try {
      setStatus(await getBillingStatus());
      setNeedsSignIn(false);
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.isAuth) {
        setNeedsSignIn(true);
        return;
      }
      setError(caught instanceof Error ? caught.message : "Could not load billing status.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function go(kind: "checkout" | "portal") {
    setBusy(kind);
    setError(null);
    try {
      const url =
        kind === "checkout" ? await createCheckoutSession() : await createPortalSession();
      // Stripe hosts both flows, so this leaves the app entirely.
      window.location.href = url;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
      setBusy(null);
    }
  }

  if (needsSignIn) {
    return (
      <div className="mx-auto max-w-md px-4 py-16">
        <h1 className="font-display text-2xl">Billing</h1>
        <p className="mt-3 text-ink-600 dark:text-ink-300">
          Sign in to see your plan.
        </p>
        <Link href="/login" className="btn-primary mt-6 inline-block">
          Sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-16">
      <p className="eyebrow">Account</p>
      <h1 className="mt-3 font-display text-3xl">Billing</h1>

      {error && (
        <p
          role="alert"
          className="mt-6 rounded-lg border border-crimson-300 bg-crimson-50 p-3 text-sm text-crimson-800 dark:border-crimson-700 dark:bg-crimson-950 dark:text-crimson-200"
        >
          {error}
        </p>
      )}

      {status === null ? (
        <p className="mt-6 text-ink-500 dark:text-ink-400">Loading…</p>
      ) : (
        <>
          <section className="card mt-6 p-6">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">
              Current plan
            </p>
            <p className="mt-1 font-display text-2xl">
              {TIER_LABELS[status.tier] ?? status.tier}
            </p>

            {status.subscription_status && (
              <p className="mt-3 text-sm text-ink-600 dark:text-ink-300">
                {STATUS_NOTES[status.subscription_status] ?? (
                  <>
                    Stripe reports this subscription as{" "}
                    <span className="font-mono text-xs">{status.subscription_status}</span>.
                  </>
                )}
              </p>
            )}

            <p className="mt-3 text-sm text-ink-600 dark:text-ink-300">
              {status.unlocks_interpretation
                ? "Interpretive claims are visible on your reports: traditional readings, scholarly positions and AI hypotheses."
                : "Interpretive claims are locked on your reports. Everything computed is unaffected: astronomy, calendars, entities, citations."}
            </p>

            {status.byok_key_last4 && (
              <p className="mt-3 text-sm text-ink-500 dark:text-ink-400">
                Using your own API key ending{" "}
                <span className="font-mono">…{status.byok_key_last4}</span>. The key itself
                is never stored.
              </p>
            )}
          </section>

          <div className="mt-6 flex flex-wrap gap-3">
            {status.can_manage && (
              <button
                type="button"
                onClick={() => go("portal")}
                disabled={busy !== null}
                className="btn-secondary"
              >
                {busy === "portal" ? "Opening…" : "Manage subscription"}
              </button>
            )}

            {!status.unlocks_interpretation && status.billing_enabled && (
              <button
                type="button"
                onClick={() => go("checkout")}
                disabled={busy !== null}
                className="btn-primary"
              >
                {busy === "checkout" ? "Starting…" : "Subscribe"}
              </button>
            )}
          </div>

          {!status.billing_enabled && (
            <p className="mt-6 rounded-lg border border-ink-200 bg-ink-50 p-3 text-sm text-ink-600 dark:border-ink-800 dark:bg-ink-900 dark:text-ink-400">
              Subscriptions are not configured on this deployment, so there is nothing to
              buy here yet. The free tier works exactly as documented.
            </p>
          )}

          <p className="mt-8 text-sm text-ink-500 dark:text-ink-400">
            <Link href="/pricing" className="underline underline-offset-4">
              Compare the plans
            </Link>
          </p>
        </>
      )}
    </div>
  );
}
