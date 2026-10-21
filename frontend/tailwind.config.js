/**
 * Tailwind v3 configuration.
 *
 * The palette is driven by CSS custom properties declared in app/globals.css so
 * the whole product can flip between the institutional dark theme and the light
 * "reading" theme by setting `data-theme` on <html> — no component needs to know
 * which theme is active.
 *
 * @type {import('tailwindcss').Config}
 */
module.exports = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./store/**/*.{ts,tsx}",
    "./stores/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "rgb(var(--ink-950) / <alpha-value>)",
          900: "rgb(var(--ink-900) / <alpha-value>)",
          850: "rgb(var(--ink-850) / <alpha-value>)",
          800: "rgb(var(--ink-800) / <alpha-value>)",
          700: "rgb(var(--ink-700) / <alpha-value>)",
          600: "rgb(var(--ink-600) / <alpha-value>)",
        },
        edge: "rgb(var(--edge) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        faint: "rgb(var(--faint) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        accent2: "rgb(var(--accent-2) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        good: "rgb(var(--good) / <alpha-value>)",
        bad: "rgb(var(--bad) / <alpha-value>)",
        /* Evidence-first answerability statuses (see docs/architecture/adr/0001). */
        status: {
          verified: "rgb(var(--good) / <alpha-value>)",
          supported: "rgb(var(--accent) / <alpha-value>)",
          review: "rgb(var(--warn) / <alpha-value>)",
          insufficient: "rgb(var(--bad) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "SF Pro Text",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        panel: "0 1px 2px rgb(0 0 0 / 0.25), 0 12px 32px -12px rgb(0 0 0 / 0.45)",
        lift: "0 18px 48px -16px rgb(0 0 0 / 0.55)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "0.25" },
          "50%": { opacity: "1" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 220ms ease-out both",
        "pulse-dot": "pulse-dot 1.4s ease-in-out infinite",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
