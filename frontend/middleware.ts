import { NextResponse, type NextRequest } from "next/server";

/**
 * Nonce-based Content Security Policy.
 *
 * Next.js App Router bootstraps with inline scripts carrying the RSC payload, so a CSP
 * without `unsafe-inline` blocks the app entirely unless each script is nonced. Rather
 * than open `script-src` to all inline script — which is the protection worth having in
 * an app that renders user-submitted text — a fresh nonce is minted per request here and
 * Next applies it to its own scripts automatically.
 *
 * `strict-dynamic` lets those nonced scripts load the chunks they need without
 * enumerating every hashed filename. Modern browsers ignore `'self'` alongside it; it is
 * kept for older ones that ignore `strict-dynamic` instead.
 *
 * The cost: reading a per-request value makes pages render on demand rather than being
 * prerendered at build time. For this app that is close to free — every page that
 * matters is already client-driven — and a real CSP is worth more than a static shell.
 */
export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const isDev = process.env.NODE_ENV === "development";

  const csp = [
    "default-src 'self'",
    // 'unsafe-eval' is required by React Refresh in development only.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${isDev ? "'unsafe-eval'" : ""}`,
    // Tailwind injects style attributes at runtime; there is no nonce path for those.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self' ${apiBase}${isDev ? " ws: wss:" : ""}`,
    "object-src 'none'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests",
  ]
    .join("; ")
    .replace(/\s{2,}/g, " ")
    .trim();

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("content-security-policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("content-security-policy", csp);
  return response;
}

export const config = {
  matcher: [
    // Everything except static assets and image optimisation, which are served
    // directly and need no policy of their own.
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
