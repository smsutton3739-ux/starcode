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
  const nonce = (crypto.randomUUID()).toString("base64");
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
  // Everything except static assets and image optimisation, which are served directly
  // and need no policy of their own. A plain string matcher, not the extended
  // { source, missing } object form: Vercel's deployment packaging step rejects that
  // form on this project even though Next.js itself compiles it without complaint. The
  // only thing given up is skipping the CSP header on prefetch requests specifically —
  // a minor optimization, not a security property — so this is a safe, complete
  // equivalent rather than a workaround that quietly weakens the policy.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};