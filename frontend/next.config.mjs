/**
 * Fail the build rather than ship a bundle pointing at localhost.
 *
 * NEXT_PUBLIC_API_URL is inlined into the browser bundle at build time. If it is unset
 * on a hosting platform, the fallback silently bakes in http://localhost:8000 and the
 * deployed site looks fine until every API call is refused by the CSP — an error that
 * points at the browser rather than at the missing variable. Better to stop here, where
 * the message can say exactly what to set.
 */
function resolveApiUrl() {
  const url = process.env.NEXT_PUBLIC_API_URL;
  const isProductionBuild =
    process.env.NODE_ENV === "production" && process.env.NEXT_PUBLIC_ALLOW_LOCALHOST !== "true";

  if (!url) {
    if (isProductionBuild) {
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

  if (isProductionBuild && /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])/.test(url)) {
    throw new Error(
      `NEXT_PUBLIC_API_URL is "${url}", which will not resolve for anyone but you.\n\n` +
        "Set it to the public URL of your API, or set NEXT_PUBLIC_ALLOW_LOCALHOST=true " +
        "if you are deliberately building a local production bundle.",
    );
  }

  if (isProductionBuild && url.startsWith("http://")) {
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

const API_URL = resolveApiUrl();

/** @type {import('next').NextConfig} */
// Content-Security-Policy is set per request in middleware.ts, where a nonce can be
// minted. These are the static headers that need no request context.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
];

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Re-exported so middleware.ts and the client read the same validated value rather
  // than each re-deriving it from the environment.
  env: { NEXT_PUBLIC_API_URL: API_URL },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
