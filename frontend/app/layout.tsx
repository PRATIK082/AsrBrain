import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AsrBrain — Institutional AUTOSAR Knowledge Assistant",
  description:
    "Citation-grounded RAG assistant for AUTOSAR Classic/Adaptive engineering: concept flow, issue triage and specification lookup.",
};

/**
 * Applies the persisted theme before first paint so the UI never flashes the
 * wrong palette. Kept inline and tiny on purpose.
 */
const THEME_BOOTSTRAP = `(function(){try{var t=localStorage.getItem("asrbrain-theme")||"dark";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","dark");}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body className="min-h-screen bg-ink-900 text-fg antialiased">{children}</body>
    </html>
  );
}
