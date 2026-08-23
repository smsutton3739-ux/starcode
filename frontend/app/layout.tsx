import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { Bodoni_Moda, Spectral, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";

/**
 * Self-hosted via next/font at build time — no request to fonts.googleapis.com at
 * runtime, so nothing here needs an entry in middleware.ts's font-src, and there is no
 * render-blocking third-party request or layout shift while a font swaps in.
 */
const bodoniModa = Bodoni_Moda({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-display",
  display: "swap",
});

const spectral = Spectral({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-body",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Starcode — Analyse ancient texts and prophecies",
    template: "%s · Starcode",
  },
  description:
    "Paste any ancient text, manuscript, prophecy, or historical document and get a sourced analysis that separates evidence from interpretation.",
  applicationName: "Starcode",
  robots: { index: true, follow: true },
  openGraph: {
    title: "Starcode",
    description:
      "Analyse ancient texts, historical documents, astronomical references and traditional prophecies.",
    type: "website",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F6F2E9" },
    { media: "(prefers-color-scheme: dark)", color: "#0C1628" },
  ],
};

/**
 * Applied before paint so a user who has chosen dark mode never sees a white flash.
 * Inline because it must run before React hydrates; it touches only the class list.
 */
const themeScript = `
(function () {
  try {
    var stored = localStorage.getItem('starcode.theme');
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (stored === 'dark' || (stored !== 'light' && prefersDark)) {
      document.documentElement.classList.add('dark');
    }
  } catch (e) {}
})();
`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Minted per request by middleware.ts so this inline script satisfies the CSP
  // without opening script-src to all inline script.
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${bodoniModa.variable} ${spectral.variable} ${ibmPlexMono.variable}`}
    >
      <head>
        {/* React deliberately does not expose `nonce` to the client, so the attribute
            is present in the server HTML and absent after hydration. That difference is
            expected and is suppressed here rather than by weakening the CSP. */}
        <script
          nonce={nonce}
          suppressHydrationWarning
          dangerouslySetInnerHTML={{ __html: themeScript }}
        />
      </head>
      <body className="flex min-h-screen flex-col">
        <a href="#main" className="skip-link">
          Skip to main content
        </a>
        <ThemeProvider>
          <SiteHeader />
          <main id="main" className="flex-1">
            {children}
          </main>
          <SiteFooter />
        </ThemeProvider>
      </body>
    </html>
  );
}
