import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'AsrBrain — AUTOSAR Knowledge Copilot',
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
        {children}
      </body>
    </html>
  );
}
