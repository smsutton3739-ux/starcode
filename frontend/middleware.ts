// Production history, so the next person (or Claude) doesn't re-diagnose this from
// scratch: this file previously shipped broken in production twice in a row —
// ERR_MODULE_NOT_FOUND on "next/server" (caused by package.json's stale
// `"type": "module"`), then "Cannot use import statement outside a module" on the very
// next deploy even after that field was removed. The second failure was Vercel reusing
// a cached webpack compilation of this exact file from the prior, broken build — the
// fix that time was a genuine content change here to force cache invalidation, which is
// this comment block. If middleware ever 500s again in production after a config-only
// fix (no change to this file), suspect stale build cache before suspecting the fix.
import { NextResponse, type NextRequest } from "next/server";
// Inlined rather than imported from @/lib/embeds: Vercel's Edge Function bundler for
// this project fails to resolve that cross-module import ("referencing unsupported
// modules"), even though nothing in that file is actually Edge-incompatible. The values
// are duplicated here as the Edge-safe copy; lib/embeds.ts remains the source of truth
// for everything else in the app (page components, widget URLs), which run in a normal
// runtime and are unaffected.
const ASTRO_CHARTS_ORIGIN = "https://astro-charts.com";
const EMBED_ROUTES = ["/tools"];
function routeAllowsEmbeds(pathname: string): boolean {
  return EMBED_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}
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
 // crypto.randomUUID() alone, not wrapped in Buffer.from(...).toString("base64"): Buffer
// is a Node.js global unavailable in the Edge Runtime middleware always runs under.
// Next's bundler polyfills it when it sees the reference, but that polyfill itself uses
// __dirname, which has no Edge shim either, so it throws at request time instead of at
// build time — a working build that 500s on every request. A UUID is already unique and
// unpredictable per request, which is everything a CSP nonce requires; base64 added
// nothing but the Node dependency.
const nonce = crypto.randomUUID();
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const isDev = process.env.NODE_ENV === "development";

  // Third-party embeds are allowed on a small set of routes and nowhere else. `frame-src`
  // is what actually admits them: without it they fall back to `default-src 'self'` and
  // the browser refuses to load the frame at all.
  //
  // No `script-src` change is needed for the embed's resize helper. Under
  // `strict-dynamic` a browser ignores host expressions entirely, so allowlisting the
  // origin there would do nothing — the script is admitted by carrying the request nonce,
  // which the page attaches. That keeps one policy for scripts everywhere rather than a
  // second, weaker one on this route.
  const embedsAllowed = routeAllowsEmbeds(request.nextUrl.pathname);
  const frameSrc = embedsAllowed ? `frame-src ${ASTRO_CHARTS_ORIGIN}` : "frame-src 'none'";

  const csp = [
    "default-src 'self'",
    // 'unsafe-eval' is required by React Refresh in development only.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${isDev ? "'unsafe-eval'" : ""}`,
    // Tailwind injects style attributes at runtime; there is no nonce path for those.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self' ${apiBase}${isDev ? " ws: wss:" : ""}`,
    frameSrc,
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
  // Node.js runtime, not Edge: Next.js bundles next/server with a copy of ua-parser-js
  // that references __dirname, a Node-only global with no Edge Runtime shim — a
  // long-standing framework bug that crashes middleware on every request in the Edge
  // Runtime regardless of anything in this file's own code. Running on the Node.js
  // runtime (stable as of Next.js 15.5) sidesteps the whole bug class, since __dirname
  // genuinely exists there.
  runtime: "nodejs",
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
