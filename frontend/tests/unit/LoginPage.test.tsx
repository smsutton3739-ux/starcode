import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

/**
 * The sign-in page's one job when things go wrong: do not lie about what exists.
 *
 * This page reads the available sign-in methods from the API on mount. It used to treat
 * a *failed* call the same as a successful one that returned nothing — the catch set
 * `canRegister = false`, which is precisely the condition that renders "New accounts are
 * not available yet". A visitor was told sign-in did not exist when the truth was that
 * the server had not answered.
 *
 * That is not a rare edge. The API sleeps after about fifteen minutes idle and takes the
 * better part of a minute to wake, so the first visitor after any quiet spell hit it —
 * which is exactly how it was found: the Google button had "disappeared" from a site
 * whose backend was reporting Google as configured the whole time.
 */

const authCapabilities = vi.fn();

vi.mock("@/lib/api", () => ({
  authCapabilities: () => authCapabilities(),
  login: vi.fn(),
  register: vi.fn(),
  oauthUrl: (name: string) => `https://api.example.com/auth/oauth/${name}/authorize`,
  ApiRequestError: class extends Error {
    fieldErrors = {};
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import LoginPage from "@/app/login/page";

const GOOGLE_CONFIGURED = {
  password_registration_enabled: false,
  anonymous_analysis_enabled: true,
  note: "Password accounts are disabled on this deployment.",
  providers: [
    { name: "google", configured: true, authorize_url: "/x" },
    { name: "github", configured: false, authorize_url: "/y" },
  ],
};

describe("the sign-in page", () => {
  beforeEach(() => {
    authCapabilities.mockReset();
  });

  it("offers the providers the API reports as configured", async () => {
    authCapabilities.mockResolvedValue(GOOGLE_CONFIGURED);
    render(<LoginPage />);

    expect(
      await screen.findByRole("link", { name: /Continue with Google/ }),
    ).toBeInTheDocument();
    // GitHub is reported but not configured, so it must not be offered.
    expect(screen.queryByRole("link", { name: /Continue with GitHub/ })).toBeNull();
  });

  it("never claims accounts are unavailable when the API did not answer", async () => {
    /* The regression. A server that did not respond tells you nothing about what it
       offers, so the page must not turn silence into a statement about the product. */
    authCapabilities.mockRejectedValue(new Error("network"));
    render(<LoginPage />);

    await waitFor(() =>
      expect(screen.queryByText(/Checking which sign-in methods/)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/New accounts are not available yet/)).toBeNull();
    expect(screen.queryByText(/no sign-in provider configured/)).toBeNull();
  });

  it("still says accounts are unavailable when the API actually says so", async () => {
    /* The honest version of the same panel: the API answered, and the answer was that
       there is genuinely nothing to sign in with. That message must survive the fix. */
    authCapabilities.mockResolvedValue({
      ...GOOGLE_CONFIGURED,
      providers: [{ name: "google", configured: false, authorize_url: "/x" }],
    });
    render(<LoginPage />);

    expect(
      await screen.findByText(/New accounts are not available yet/),
    ).toBeInTheDocument();
  });

  it("tells the visitor the wait is a sleeping server, not a hang", async () => {
    authCapabilities.mockRejectedValue(new Error("network"));
    render(<LoginPage />);

    expect(
      await screen.findByText(/The server sleeps when idle/),
    ).toBeInTheDocument();
  });

  it("retries rather than giving up on the first failure", async () => {
    /* A cold start fails the first call and succeeds a few seconds later. Giving up
       immediately is what made the page wrong; one attempt is not enough. */
    authCapabilities
      .mockRejectedValueOnce(new Error("cold start"))
      .mockResolvedValue(GOOGLE_CONFIGURED);
    render(<LoginPage />);

    expect(
      await screen.findByRole("link", { name: /Continue with Google/ }, { timeout: 15000 }),
    ).toBeInTheDocument();
    expect(authCapabilities.mock.calls.length).toBeGreaterThan(1);
  }, 20000);
});
