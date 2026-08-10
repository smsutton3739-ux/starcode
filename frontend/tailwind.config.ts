import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Each claim type has its own colour, used identically in the web UI and in
        // exported PDFs and Word documents so a printed report reads the same way.
        claim: {
          source: "#475569",
          verified: "#15803d",
          calculated: "#1d4ed8",
          textual: "#0f766e",
          traditional: "#a16207",
          scholarly: "#7c3aed",
          hypothesis: "#c2410c",
          unknown: "#64748b",
        },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        serif: ["ui-serif", "Georgia", "Cambria", "serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "rise": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "translateY(0)" } },
      },
      animation: {
        // Deliberately short and subtle. Motion here should orient, never perform.
        "fade-in": "fade-in 180ms ease-out",
        rise: "rise 220ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
