import { PHASE_PRODUCTION_BUILD } from "next/constants.js";

/**
 * Fail the build rather than ship a bundle pointing at localhost.
 *
 * NEXT_PUBLIC_API_URL is inlined into the browser bundle at build time. If it is unset
 * on a hosting platform, the fallback silently bakes in http://localhost:8000 and the
 * deployed site looks fine until every API call is refused by the CSP — an error that
 * points at the browser rather than at the missing variable. Better to stop here, where
 * the message can say exactly what to set.
 *
 * Only an actual compile is checked. `next start` and `next lint` load this file too and
 * both report NODE_ENV=production, but neither produces a bundle: by the time `next start`
 * runs the value is already baked into .next, and the runtime container has no reason to
 * carry a build argument. An earlier version keyed the check on NODE_ENV, which made a
 * correctly built Docker image refuse to boot.
 *
 * `next lint` reports the production-build phase as well, so the phase alone cannot tell
 * the two apart and the CLI verb is read from argv to separate them. Linting a checkout
 * should not require deployment configuration.
 */
function isBuildingABundle(phase) {
  if (phase !== PHASE_PRODUCTION_BUILD) return false;
  return process.argv[2] !== "lint";
}

function resolveApiUrl(phase) {
  const url = process.env.NEXT_PUBLIC_API_URL;
  const isCheckedBuild =
    isBuildingABundle(phase) && process.env.NEXT_PUBLIC_ALLOW_LOCALHOST !== "true";

  if (!url) {
    if (isCheckedBuild) {
      throw new Error(
        "NEXT_PUBLIC_API_URL is not set.\n\n" +
          "It is compiled into the browser bundle, so it must be present at BUILD time, " +
          "not just at runtime. On Vercel, add it under Settings → Environment Variables " +
          "and redeploy; in Docker, pass it as a --build-arg.\n\n" +
          "It must be the public URL of the API (for example https://api.example.com), " +
          "and it must match the backend's CORS_ORIGINS. Note that localhost and " +
          "127.0.0.1 are different origins for CORS and CSP.\n\n" +
          "Set NEXT_PUBLIC_ALLOW_LOCALHOST=true to build against localhost deliberately.",
      );
    }
    return "http://localhost:8000";
  }

  if (isCheckedBuild &&/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])/.test(url)) {
    throw new Error(
      `NEXT_PUBLIC_API_URL is "${url}", which will not resolve for anyone but you.\n\n` +
        "Set it to the public URL of your API, or set NEXT_PUBLIC_ALLOW_LOCALHOST=true " +
        "if you are deliberately building a local production bundle.",
    );
  }

  if (isCheckedBuild &&url.startsWith("http://")) {
    // Not fatal — a private network or a proxy in front is legitimate — but the browser
    // will block a plain-HTTP call from an HTTPS page, so say so now.
    console.warn(
      `\n⚠  NEXT_PUBLIC_API_URL is "${url}" (plain HTTP).\n` +
        "   A browser on an HTTPS page will block requests to it as mixed content.\n" +
        "   Use https:// unless the API sits behind a proxy that terminates TLS.\n",
    );
  }

  return url;
}

/** 
 * @type {import('next').NextConfig}
 */
const nextConfig = {
  // Content-Security-Policy is set per request in middleware.ts, where a nonce can be
// minted. These are the static headers that need no request context.
}
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
];

export default function config(phase) {
  return {
    reactStrictMode: true,
    poweredByHeader: false,
    // Node.js Middleware opt-in (see middleware.ts for why): some Next.js 15.x releases
    // still gate this behind the experimental flag even though the feature is stable.
    experimental: { nodeMiddleware: true },
    env: { NEXT_PUBLIC_API_URL: resolveApiUrl(phase) },
    async headers() {
      return [{ source: "/:path*", headers: securityHeaders }];
    },
  };
}
