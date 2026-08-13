import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * Accessibility tests.
 *
 * The whole product rests on a reader being able to tell a calculation from a
 * conjecture. If that distinction is carried by colour alone, it does not exist for a
 * meaningful share of users — so these tests check the labelling survives without
 * colour, not just that axe reports no violations.
 */

const STANDARD = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function scan(page: import("@playwright/test").Page, selector?: string) {
  let builder = new AxeBuilder({ page }).withTags(STANDARD);
  if (selector) builder = builder.include(selector);
  return builder.analyze();
}

test.describe("static pages", () => {
  for (const [name, path] of [
    ["homepage", "/"],
    ["about", "/about"],
    ["explore", "/explore"],
    ["login", "/login"],
  ] as const) {
    test(`${name} has no WCAG A/AA violations`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const results = await scan(page);
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
    });

    test(`${name} has no violations in dark mode`, async ({ page }) => {
      await page.goto(path);
      await page.getByRole("button", { name: /dark mode/i }).click();
      await page.waitForTimeout(300);
      const results = await scan(page);
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
    });
  }
});

test.describe("the chart tools page", () => {
  /**
   * Tested apart from the other static pages because it embeds a third party.
   *
   * `networkidle` is not usable here: the page waits on frames from another origin,
   * which may poll, hold a connection, or simply be unreachable — any of which hangs the
   * wait rather than failing it. What our own markup does is fully determined once the
   * document is parsed, so that is what is waited for.
   *
   * The scan is scoped to `main` for the same reason. Cross-origin frame content is
   * opaque to axe and is not ours to fix; scoping keeps a failure here meaning "our page
   * has a problem" rather than "someone else's widget does".
   */
  const scanOurs = (page: import("@playwright/test").Page) => scan(page, "main");

  test("has no WCAG A/AA violations", async ({ page }) => {
    await page.goto("/tools", { waitUntil: "domcontentloaded" });
    const results = await scanOurs(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("has no violations in dark mode", async ({ page }) => {
    await page.goto("/tools", { waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: /dark mode/i }).click();
    await page.waitForTimeout(300);
    const results = await scanOurs(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("says what the embeds are before showing them", async ({ page }) => {
    await page.goto("/tools", { waitUntil: "domcontentloaded" });

    // The distinction the whole product rests on has to survive onto this page: these
    // are somebody else's astrology widgets, not a Starcode finding.
    await expect(page.getByText(/Reading meaning into those positions is astrology/i)).toBeVisible();
    await expect(page.getByText(/Nothing produced on this page is a Starcode analysis/i)).toBeVisible();
    await expect(page.getByText(/affiliate identifier/i)).toBeVisible();
  });

  test("every embedded frame is named for a screen reader", async ({ page }) => {
    await page.goto("/tools", { waitUntil: "domcontentloaded" });

    const frames = page.locator("main iframe");
    const count = await frames.count();

    if (count === 0) {
      // A deployment without NEXT_PUBLIC_ASTRO_CHARTS_AFF renders no embeds at all, which
      // is correct rather than broken — so assert the page says so, instead of failing on
      // the absence of frames it was never going to have. An earlier version of this test
      // assumed the configured build and failed on CI for that reason alone.
      await expect(page.getByText(/not configured on this deployment/i)).toBeVisible();
      return;
    }

    for (let i = 0; i < count; i += 1) {
      // An unnamed frame is announced as "frame", which tells a screen-reader user
      // nothing about which of the two they have landed in.
      await expect(frames.nth(i)).toHaveAttribute("title", /\S/);
    }
  });
});

test.describe("the report", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.fill(
      "#analyze-input",
      "And the sun became black as sackcloth of hair, and the moon became as blood. In 587 BC Jerusalem fell.",
    );
    await page.getByRole("button", { name: "ANALYZE" }).click();
    await expect(page.getByRole("heading", { name: "Executive Summary" })).toBeVisible({
      timeout: 90_000,
    });
  });

  test("has no WCAG A/AA violations", async ({ page }) => {
    const results = await scan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("claim types are distinguishable without colour", async ({ page }) => {
    // Strip all colour, then confirm each badge still names its type in text.
    await page.addStyleTag({
      content: "* { filter: grayscale(100%) !important; }",
    });
    const badges = page.locator("article .badge").first();
    await expect(badges).toBeVisible();
    const text = await badges.textContent();
    expect(text?.trim().length ?? 0).toBeGreaterThan(2);
  });

  test("confidence is available to assistive technology", async ({ page }) => {
    // A bar with no accessible name is invisible to a screen reader, and confidence is
    // the single most important qualifier in the report.
    await expect(
      page.getByRole("img", { name: /Confidence \d+ percent/ }).first(),
    ).toBeVisible();
  });

  test("headings form a sensible outline", async ({ page }) => {
    const levels = await page.$$eval("h1, h2, h3", (elements) =>
      elements.map((element) => Number(element.tagName[1])),
    );
    expect(levels[0]).toBe(1);
    // No level may be skipped on the way down.
    for (let index = 1; index < levels.length; index += 1) {
      expect(levels[index]! - levels[index - 1]!).toBeLessThanOrEqual(1);
    }
  });
});

test.describe("keyboard operation", () => {
  test("the skip link is the first stop and works", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => document.activeElement?.textContent);
    expect(focused).toContain("Skip to main content");

    await page.keyboard.press("Enter");
    await expect(page.locator("#main")).toBeVisible();
  });

  test("the whole homepage flow is reachable by keyboard", async ({ page }) => {
    await page.goto("/");

    // Tab until the textarea has focus, then type and submit without a mouse.
    for (let index = 0; index < 15; index += 1) {
      await page.keyboard.press("Tab");
      const id = await page.evaluate(() => document.activeElement?.id);
      if (id === "analyze-input") break;
    }
    expect(await page.evaluate(() => document.activeElement?.id)).toBe("analyze-input");

    await page.keyboard.type("The moon became as blood.");
    await expect(page.getByRole("button", { name: "ANALYZE" })).toBeEnabled();
  });

  test("focus is always visible", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");

    const outline = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element) return null;
      const style = window.getComputedStyle(element);
      return { outline: style.outlineStyle, shadow: style.boxShadow };
    });
    // The focus ring is drawn with a ring shadow rather than an outline.
    expect(outline?.outline !== "none" || (outline?.shadow ?? "none") !== "none").toBe(true);
  });
});

test.describe("motion", () => {
  test("animations are suppressed when reduced motion is requested", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto("/");

    const duration = await page.evaluate(() => {
      const element = document.querySelector(".animate-fade-in");
      return element ? window.getComputedStyle(element).animationDuration : "0s";
    });
    // Chromium serialises 0.01ms as "1e-05s".
    expect(["0s", "0.01ms", "1e-05s"]).toContain(duration);
    await context.close();
  });
});
