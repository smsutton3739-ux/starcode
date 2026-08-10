"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { setTokens } from "@/lib/api";

/**
 * OAuth landing page. Tokens arrive in the URL fragment, which browsers never send to
 * a server and which stays out of referrer headers and access logs.
 */
export default function OAuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");

    if (access && refresh) {
      setTokens(access, refresh);
      // Clear the fragment so the tokens are not left in browser history.
      window.history.replaceState({}, "", "/auth/callback");
      router.replace("/dashboard");
    } else {
      setError("Sign-in did not complete. Please try again.");
    }
  }, [router]);

  return (
    <div className="mx-auto max-w-md px-4 py-24 text-center">
      {error ? (
        <>
          <h1 className="text-xl font-semibold">Sign-in failed</h1>
          <p className="mt-2 text-slate-600 dark:text-slate-400">{error}</p>
          <a href="/login" className="btn-primary mt-6">Back to sign in</a>
        </>
      ) : (
        <p className="text-slate-600 dark:text-slate-400">Signing you in…</p>
      )}
    </div>
  );
}
