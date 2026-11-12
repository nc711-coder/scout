import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Scout: AI lead research",
  description: "Researches businesses on the web, checks every fact against its source, scores fit and writes a first line.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
