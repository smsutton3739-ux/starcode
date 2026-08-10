"use client";

import { useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { storeAnonymousToken } from "@/lib/api";

/**
 * Share-link entry point. Stores the capability token, then hands off to the normal
 * analysis view so a shared report and an owned one look and behave identically.
 */
export default function SharedAnalysisPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    const token = searchParams.get("token");
    if (token) storeAnonymousToken(params.id, token);
    router.replace(`/analysis/${params.id}`);
  }, [params.id, router, searchParams]);

  return (
    <div className="mx-auto max-w-md px-4 py-24 text-center text-slate-600 dark:text-slate-400">
      Opening the shared report…
    </div>
  );
}
