import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * The sign-in page when a deployment offers no way to create an account.
 *
 * This is not a hypothetical state — it is what astro-decoded.com served for weeks.
 * Password registration is off by default (there is no reset flow, and an unrecoverable
 * account is worse than none) and OAuth only works once a provider is configured, so a
 * deployment that has done neither presents a visitor with a password form they can never
 * hold credentials for, above a note explaining that password accounts are disabled.
 *
 * The e2e backend configures no provider and leaves registration off, so it reproduces
 * that state exactly, which is what makes these assertions meaningful rather than
 * theoretical. If a future change makes the page lead with the form again, this fails.
 */

test.describe("sign-in with no available method", () => {
  test("explains the situation rather than showing an unusable form", async ({ page }) => {
    await page.goto("/login");

    await expect(page.getByText("New accounts are not available yet")).toBeVisible();

    // The visitor is pointed at what they can actually do. Anonymous analysis is the
    // main path and needs no account at all.
    await expect(
      page.getByRole("link", { name: /Analyse a text without an account/ }),
    ).toBeVisible();

    // The credentials form must not be the first thing they meet.
    await expect(page.locator('input[type="password"]')).toBeHidden();
  });

  test("still lets an operator-created account sign in", async ({ page }) => {
    // scripts/create_admin.py accounts are real and use a password, so the form has to
    // stay reachable — just not in front of visitors who cannot use it.
    await page.goto("/login");
    await page.getByText("I already have an account").click();

    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  for (const theme of ["light", "dark"] as const) {
    test(`has no WCAG violations in ${theme} mode`, async ({ page }) => {
      await page.goto("/login");
      if (theme === "dark") {
        await page.evaluate(() => document.documentElement.classList.add("dark"));
      }
      await expect(page.getByText("New accounts are not available yet")).toBeVisible();

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
});

/**
 * Navigation to the paid surfaces.
 *
 * Both pages were built, deployed and configured end to end while being reachable only
 * by typing the URL — nothing linked to them, so nobody could subscribe by using the
 * site. Tests covered what each page rendered and never that a visitor could arrive at
 * one, which is the gap this closes.
 */
test.describe("the paid surfaces are reachable", () => {
  test("pricing is linked from the homepage", async ({ page }) => {
    await page.goto("/");
    // Header nav collapses on narrow viewports, so the footer link is what guarantees
    // this is reachable at every width. Either satisfies the assertion.
    await expect(page.locator('a[href="/pricing"]').first()).toBeVisible();
  });

  test("following that link reaches the plan comparison", async ({ page }) => {
    await page.goto("/");
    await page.locator('a[href="/pricing"]').first().click();
    await expect(page).toHaveURL(/\/pricing$/);
    await expect(page.getByRole("heading", { name: /Free/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Paid/ })).toBeVisible();
  });
});
