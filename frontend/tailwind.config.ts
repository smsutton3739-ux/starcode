import type { Config } from "tailwindcss";

/**
 * Design tokens.
 *
 * The site's visual identity: a manuscript read by night — warm parchment in light mode,
 * deep night-sky ink in dark mode, with a lapis-blue primary accent (the colour of lapis
 * lazuli pigment used in illuminated manuscripts) and a gold accent for tradition and the
 * mark. Every colour family below is a full 50–950 Tailwind-style scale so existing
 * shade-number usage (e.g. `bg-X-50 dark:bg-X-950`) carries over with correct contrast at
 * every step — only the family name changes, e.g. `slate` → `ink`, `blue` → `lapis`.
 *
 * `ink` is the neutral scale and doubles as the light/dark surface scale: ink-50 is bone
 * parchment, ink-950 is night sky. `lapis` is the primary interactive colour. The
 * remaining families are the seven claim-type colours plus one danger colour, each
 * assigned to feel intentional rather than a stock Tailwind swap: verdigris (bronze
 * patina) for verified history, reed (papyrus) for textual analysis, gold for tradition,
 * plum (manuscript ink) for scholarship, terra (unfired clay) for AI hypothesis, and
 * crimson (seal wax) for errors/danger.
 */
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#F6F2E9",
          100: "#ECE5D5",
          200: "#DCD2BC",
          300: "#B9AF9B",
          400: "#8D8779",
          500: "#656257",
          600: "#494A50",
          700: "#33374A",
          800: "#202540",
          900: "#161B34",
          950: "#0C1628",
        },
        lapis: {
          50: "#EEF3FB",
          100: "#DCE7F6",
          200: "#B9CFEE",
          300: "#8FB0E0",
          400: "#5E86C8",
          500: "#3D68B0",
          600: "#2E5AA8",
          700: "#244780",
          800: "#1C3760",
          900: "#172C4A",
          950: "#0F1D33",
        },
        gold: {
          50: "#FBF4E5",
          100: "#F6E7C8",
          200: "#EDD096",
          300: "#E0B466",
          400: "#D19E42",
          500: "#C8952F",
          600: "#A97423",
          700: "#855A1C",
          800: "#664418",
          900: "#4F3514",
          950: "#2C1D0B",
        },
        verdigris: {
          50: "#EAF6EF",
          100: "#CDEBDA",
          200: "#9BD6B7",
          300: "#66BC91",
          400: "#3E9E72",
          500: "#2F7A5C",
          600: "#256149",
          700: "#1E4E3B",
          800: "#183E2F",
          900: "#143224",
          950: "#0C1E15",
        },
        reed: {
          50: "#E8F5F5",
          100: "#C9E8E9",
          200: "#96D2D4",
          300: "#62B7BA",
          400: "#3D9A9E",
          500: "#2A7D82",
          600: "#216568",
          700: "#1B5153",
          800: "#164042",
          900: "#123436",
          950: "#0B2223",
        },
        plum: {
          50: "#F1ECF6",
          100: "#E2D5EE",
          200: "#C7ADDD",
          300: "#A882C6",
          400: "#895FAE",
          500: "#6B4E8E",
          600: "#563E74",
          700: "#45325D",
          800: "#372849",
          900: "#2C203A",
          950: "#1A1323",
        },
        terra: {
          50: "#FBEEE6",
          100: "#F5D6C2",
          200: "#EAAF8A",
          300: "#DC8657",
          400: "#C96A3B",
          500: "#B0562E",
          600: "#8E4325",
          700: "#71351E",
          800: "#582A18",
          900: "#452213",
          950: "#29140B",
        },
        crimson: {
          50: "#FBEBEA",
          100: "#F5D0CD",
          200: "#E8A29B",
          300: "#D6746A",
          400: "#C24F42",
          500: "#A3342E",
          600: "#832A25",
          700: "#68221E",
          800: "#521B18",
          900: "#3F1512",
          950: "#250C0A",
        },
        // Each claim type has its own colour, used identically in the web UI and in
        // exported PDFs and Word documents so a printed report reads the same way.
        // These hex values MUST stay in sync with backend/app/services/export.py
        // (tone_colors) and frontend/app/about/page.tsx (the legend) — see the comment
        // at each of those locations.
        claim: {
          source: "#494A50", // ink-600
          verified: "#256149", // verdigris-600
          calculated: "#2E5AA8", // lapis-600
          textual: "#216568", // reed-600
          traditional: "#855A1C", // gold-700
          scholarly: "#563E74", // plum-600
          hypothesis: "#8E4325", // terra-600
          unknown: "#656257", // ink-500
        },
      },
      fontFamily: {
        // Populated with next/font CSS variables in app/layout.tsx, with system-font
        // fallbacks so the page is never unstyled while a font loads.
        display: ["var(--font-display)", "Georgia", "serif"],
        body: ["var(--font-body)", "Georgia", "Cambria", "serif"],
        sans: ["var(--font-body)", "ui-sans-serif", "system-ui", "sans-serif"],
        // font-serif is used deliberately (e.g. ClaimCard's quoted source_text
        // blockquote) — pointed at the same Spectral variable as `body` rather than
        // Tailwind's generic serif stack, so a "quote" visually reads as this site's
        // serif, not a system default.
        serif: ["var(--font-body)", "Georgia", "Cambria", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
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
