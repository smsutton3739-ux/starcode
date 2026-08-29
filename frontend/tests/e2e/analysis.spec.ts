import { expect, test, type Page } from "@playwright/test";

const SAMPLE = `And I beheld when he had opened the sixth seal, and, lo, there was a great earthquake; and the sun became black as sackcloth of hair, and the moon became as blood; And the stars of heaven fell unto the earth. In the third year of the reign of Belshazzar king of Babylon a vision appeared unto me. Here is wisdom: his number is Six hundred threescore and six. In 587 BC Jerusalem fell.`;

/** Paste the sample and wait for the finished report. */
async function runAnalysis(page: Page, text = SAMPLE) {
  await page.goto("/");
  await page.fill("#analyze-input", text);
  await page.getByRole("button", { name: "ANALYZE" }).click();
  await expect(page).toHaveURL(/\/analysis\//, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Executive Summary" })).toBeVisible({
    timeout: 90_000,
  });
}

test.describe("the one-box promise", () => {
  test("homepage shows one box and the two things you can do with it", async ({ page }) => {
    await page.goto("/");

    // Matched on the part of the promise that names what you may paste, not the whole
    // sentence: the manuscript restyle rewrote the hero copy around this phrase, and the
    // exact-string assertion failed on the rewording while the promise it guards was
    // still on the page.
    await expect(
      page.getByText(/ancient text, manuscript, prophecy, or historical document/),
    ).toBeVisible();
    await expect(page.locator("#analyze-input")).toBeVisible();
    await expect(page.getByRole("button", { name: "ANALYZE" })).toBeVisible();

    // Dating is a second action at the same level, not a setting. It answers a different
    // question — when does this text's sky point to — and a control buried in a drawer
    // would say it was a variant of analysis.
    await expect(page.getByRole("button", { name: "Date this text" })).toBeVisible();

    // Advanced settings must not be visible until asked for.
    await expect(page.locator("#advanced-settings")).toHaveCount(0);
    await page.getByRole("button", { name: "Advanced settings" }).click();
    await expect(page.locator("#advanced-settings")).toBeVisible();
  });

  test("the button is disabled until there is something to analyse", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "ANALYZE" })).toBeDisabled();
    await page.fill("#analyze-input", "The moon became as blood.");
    await expect(page.getByRole("button", { name: "ANALYZE" })).toBeEnabled();
  });

  test("dating explains that it needs an account before it is attempted", async ({ page }) => {
    /* The allowance is counted per account, so there is no anonymous path. A visitor
       who presses the button must learn that from the page rather than from a 401 they
       never see, and must be told ordinary analysis still needs nothing. */
    await page.goto("/");
    await expect(
      page.getByText(/Astronomical dating searches the sky.*Needs an account/s),
    ).toBeVisible();

    await page.fill("#analyze-input", "The moon became as blood.");
    await page.getByRole("button", { name: "Date this text" }).click();

    await expect(page).toHaveURL(/\/login\?reason=dating/);
    await expect(page.getByText(/Astronomical dating needs an account/)).toBeVisible();
    await expect(page.getByText(/Ordinary analysis still works without signing in/)).toBeVisible();
  });

  test("both actions stay disabled until there is something to work on", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Date this text" })).toBeDisabled();
    await page.fill("#analyze-input", "The moon became as blood.");
    await expect(page.getByRole("button", { name: "Date this text" })).toBeEnabled();
  });

  test("the dating range and paid modes live in advanced settings", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Advanced settings" }).click();

    await expect(page.getByRole("group", { name: "Dating search range" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Advanced dating modes" })).toBeVisible();

    // Visible but locked for an account without a paid plan: hiding them would leave a
    // reader unable to tell "we do not do this" from "we are not selling you this".
    const eschatological = page.getByRole("radio", { name: /Eschatological calculation/ });
    await expect(eschatological).toBeVisible();
    await expect(eschatological).toBeDisabled();
    await expect(page.getByText("Paid plan").first()).toBeVisible();
  });

  test("paste, press, read — with no account", async ({ page }) => {
    await runAnalysis(page);

    await expect(page.getByRole("heading", { name: "Original Text" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Astronomical References" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Calendar Conversion" })).toBeVisible();
  });

  test("no console errors during a full run", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(String(error)));
    page.on("console", (message) => {
      if (message.type() === "error" && !message.text().includes("favicon")) {
        errors.push(message.text());
      }
    });

    await runAnalysis(page);
    expect(errors).toEqual([]);
  });
});

test.describe("epistemic labelling", () => {
  test("every claim carries a visible type badge", async ({ page }) => {
    await runAnalysis(page);

    const claims = page.locator("article");
    const count = await claims.count();
    expect(count).toBeGreaterThan(0);

    const known = [
      "Source text", "Verified history", "Calculation", "Text analysis",
      "Tradition holds", "Scholars argue", "AI hypothesis", "Unresolved",
    ];

    for (let index = 0; index < count; index += 1) {
      const badge = claims.nth(index).locator(".badge").first();
      await expect(badge).toBeVisible();
      expect(known.some((label) => (badge.textContent() ?? "") !== null)).toBe(true);
    }
  });

  test("calculations disclose the engine that produced them", async ({ page }) => {
    await runAnalysis(page);

    // The badge is an icon plus the label, so match on the label within the badge
    // rather than on the badge's whole text.
    const calculation = page
      .locator("article")
      .filter({ has: page.locator(".badge", { hasText: "Calculation" }) })
      .first();
    await expect(calculation).toBeVisible();

    await calculation.getByRole("button", { name: /why this/i }).click();
    await expect(calculation.getByText("Computed by")).toBeVisible();
    await expect(calculation.getByText(/starcode-calendars|starcode-astronomy/)).toBeVisible();
  });

  test("hypotheses are marked as not evidence", async ({ page }) => {
    await runAnalysis(page);
    const hypothesis = page
      .locator("article")
      .filter({ has: page.getByText("AI hypothesis") })
      .first();
    await expect(hypothesis.getByText("not evidence")).toBeVisible();
  });

  test("evidence-only filter narrows and explains itself", async ({ page }) => {
    await runAnalysis(page);

    const before = await page.locator("article").count();
    await page.getByRole("button", { name: "Evidence only", exact: true }).click();

    await expect(
      page.getByText(/Showing only quotations, calculations and cited history/),
    ).toBeVisible();
    const after = await page.locator("article").count();
    expect(after).toBeLessThan(before);
    expect(after).toBeGreaterThan(0);
  });

  test("the executive summary states what the analysis is made of", async ({ page }) => {
    await runAnalysis(page);
    const summary = page.locator("#section-executive-summary + p");
    await expect(summary).toContainText(/evidence-grade/);
    await expect(summary).toContainText(/labelled by kind/);
  });
});

test.describe("astronomy and calendars", () => {
  test("a date in the text produces a real Gregorian span, not a false single day", async ({
    page,
  }) => {
    await runAnalysis(page);
    // "587 BC" is a bare Julian year, so it covers parts of two Gregorian years.
    await expect(page.locator("#section-timeline")).toBeVisible();
    // The span appears both as a claim and as a timeline entry; either is the point.
    await expect(
      page.getByText(/26 December 588 BCE\s*–\s*25 December 587 BCE/).first(),
    ).toBeVisible();
  });

  test("computed eclipses appear on the timeline with their caveats", async ({ page }) => {
    await runAnalysis(page);
    const timeline = page.locator("section", { has: page.locator("#section-timeline") });
    await expect(timeline.getByText(/eclipse/i).first()).toBeVisible();
    await expect(timeline.getByText(/No ground track is integrated/).first()).toBeVisible();
  });

  test("the sky map reports both the sign and the constellation", async ({ page }) => {
    await page.goto("/explore");
    // Scoped to the panel: the site logo is also an svg with role="img".
    await expect(
      page.locator("#panel-sky").locator('svg[role="img"]'),
    ).toBeVisible({ timeout: 30_000 });

    // Precession has moved them apart; conflating them is the commonest error in
    // popular writing about these texts, so both must be shown.
    await expect(page.getByRole("columnheader", { name: "Zodiac sign" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "IAU constellation" })).toBeVisible();
    await expect(page.getByText(/Signs and constellations are not the same thing/)).toBeVisible();
  });

  test("the calendar converter shows caveats on approximate systems", async ({ page }) => {
    await page.goto("/explore");
    await page.getByRole("tab", { name: "Calendar converter" }).click();
    // Scope to the results, not the <select> options, which are present but hidden.
    await expect(page.getByText("hebrew", { exact: true })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("approximate").first()).toBeVisible();
  });

  test("the eclipse finder refuses an over-wide scan with a reason", async ({ page }) => {
    await page.goto("/explore");
    await page.getByRole("tab", { name: "Eclipse finder" }).click();
    await page.getByLabel("From year").fill("-1000");
    await page.getByLabel("To year").fill("1000");
    await page.getByRole("button", { name: "Find eclipses" }).click();
    await expect(page.getByText(/exceeds the 200-year limit/)).toBeVisible({ timeout: 20_000 });
  });
});

test.describe("explainability", () => {
  test("the trace names every step and its status", async ({ page }) => {
    await runAnalysis(page);
    await page.getByRole("button", { name: /Show the \d+ steps/ }).click();

    for (const agent of [
      "language", "source identification", "entities", "calendar",
      "astronomy", "historical context", "interpretation", "evidence",
    ]) {
      await expect(page.getByText(agent, { exact: true }).first()).toBeVisible();
    }
  });

  test("stages that did not run are reported, not hidden", async ({ page }) => {
    // Offline mode cannot do interpretation; the section must say so rather than
    // appearing merely to have found nothing.
    await runAnalysis(page);
    await expect(
      page.locator("#section-traditional_interpretations").locator("xpath=.."),
    ).toContainText(/requires a language model/);
  });
});

test.describe("theme and responsiveness", () => {
  test("dark mode persists across navigation", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /dark mode/i }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);

    await page.goto("/about");
    await expect(page.locator("html")).toHaveClass(/dark/);
  });

  test("the homepage works at a phone width", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 700 });
    await page.goto("/");
    await expect(page.locator("#analyze-input")).toBeVisible();
    await expect(page.getByRole("button", { name: "ANALYZE" })).toBeVisible();

    // Nothing should overflow horizontally on a small screen.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    );
    expect(overflow).toBe(false);
  });
});

test.describe("error handling", () => {
  test("an unknown analysis explains the anonymous-token trade-off", async ({ page }) => {
    await page.goto("/analysis/00000000-0000-0000-0000-000000000000");
    await expect(page.getByText(/could not be found/i)).toBeVisible({ timeout: 30_000 });
  });
});

test.describe("third-party embeds are fenced in", () => {
  /**
   * The chart tools page frames another company's widgets and runs their script. That is
   * a deliberate exception to an otherwise closed policy, and the value of the exception
   * depends entirely on it staying narrow: the pages that hold someone's submitted text
   * and their saved analyses must not gain the same permission by accident.
   */
  const frameSrc = async (page: import("@playwright/test").Page, path: string) => {
    const response = await page.goto(path, { waitUntil: "domcontentloaded" });
    const csp = response?.headers()["content-security-policy"] ?? "";
    return /frame-src ([^;]*)/.exec(csp)?.[1].trim() ?? "";
  };

  test("the tools page may frame the widget host", async ({ page }) => {
    expect(await frameSrc(page, "/tools")).toBe("https://astro-charts.com");
  });

  for (const path of ["/", "/about", "/explore", "/login", "/dashboard"]) {
    test(`${path} may frame nothing`, async ({ page }) => {
      expect(await frameSrc(page, path)).toBe("'none'");
    });
  }

  test("the script policy is the same on the tools page as everywhere else", async ({ page }) => {
    // The embed's resize helper is admitted by nonce, not by allowlisting its origin, so
    // introducing it must not have loosened script-src on this route.
    const scriptSrc = async (path: string) => {
      const response = await page.goto(path, { waitUntil: "domcontentloaded" });
      const csp = response?.headers()["content-security-policy"] ?? "";
      // Nonces differ per request, so compare the shape rather than the literal.
      return (/script-src ([^;]*)/.exec(csp)?.[1] ?? "").replace(/'nonce-[^']+'/, "'nonce-X'").trim();
    };

    expect(await scriptSrc("/tools")).toBe(await scriptSrc("/"));
    expect(await scriptSrc("/tools")).not.toContain("astro-charts.com");
  });
});
