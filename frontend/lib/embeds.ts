/**
 * Third-party embeds, and the single place their origin is written down.
 *
 * The middleware has to name this host in `frame-src` and the page has to name it in the
 * iframe `src`. If those two ever disagree the widget silently fails to load with only a
 * console message to explain it, so both read the same constant.
 */

/** The only external origin any embed is permitted to come from. */
export const ASTRO_CHARTS_ORIGIN = "https://astro-charts.com";

/**
 * Routes where third-party frames are allowed. Everything else keeps the strict policy.
 *
 * This is deliberately not site-wide. The embed host's script runs with full access to
 * whatever page it is on, and most pages here can be holding someone's submitted text and
 * their analysis history. A widget that helps on a tools page has no business being able
 * to read those, so it is confined to a route that has none of them.
 */
export const EMBED_ROUTES = ["/tools"];

export function routeAllowsEmbeds(pathname: string): boolean {
  return EMBED_ROUTES.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

/**
 * The affiliate identifier, read at build time.
 *
 * Absent means the widgets are not rendered at all. Shipping the literal placeholder
 * would produce a page that looks fine, earns nothing, and might not even load — better
 * to show nothing and say why.
 */
export const ASTRO_CHARTS_AFFILIATE_ID = process.env.NEXT_PUBLIC_ASTRO_CHARTS_AFF ?? "";

export function widgetUrl(tool: "birth-chart" | "synastry"): string {
  const affiliate = ASTRO_CHARTS_AFFILIATE_ID
    ? `?aff=${encodeURIComponent(ASTRO_CHARTS_AFFILIATE_ID)}`
    : "";
  return `${ASTRO_CHARTS_ORIGIN}/tools/widget/iframe/${tool}/${affiliate}`;
}

export const IFRAME_RESIZER_SRC = `${ASTRO_CHARTS_ORIGIN}/static/iframe-resizer.js`;
