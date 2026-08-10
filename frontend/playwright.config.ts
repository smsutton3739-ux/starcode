import { defineConfig, devices } from "@playwright/test";

const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 3100);
const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8100";
const BASE_URL = `http://127.0.0.1:${WEB_PORT}`;

/**
 * End-to-end and accessibility tests.
 *
 * These run against the real stack — a real FastAPI process, a real database, the real
 * analysis pipeline in offline mode. Nothing is mocked, because the bugs worth catching
 * here are integration bugs: a field the API renames, a CSP that blocks the app, a claim
 * shape the report view cannot read. A mocked API would have passed while the product
 * was broken.
 *
 * Start the backend separately (see scripts/e2e-backend.sh); the web server is started
 * by Playwright.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  timeout: 90_000,
  expect: { timeout: 15_000 },

  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined,
    },
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],

  webServer: {
    command: `npx next start -p ${WEB_PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { NEXT_PUBLIC_API_URL: API_URL, NEXT_PUBLIC_ALLOW_LOCALHOST: "true" },
  },
});
