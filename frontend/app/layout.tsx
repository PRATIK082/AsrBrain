import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'AsrBrain — Automotive Intelligence',
  description: 'Citation-grounded AUTOSAR Classic/Adaptive engineering assistant',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          background: '#070A0F',
          color: '#F1F5F9',
          fontFamily: "Inter, SF Pro Text, system-ui, sans-serif",
        }}
      >
        <style>{`
          :focus-visible { outline: 2px solid #00F5FF; outline-offset: 2px; }
          @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }
          }
        `}</style>
        {children}
      </body>
    </html>
  );
}
