import "./globals.css";
import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import type { ReactNode } from "react";

// IBM Plex Mono — an OFL-licensed, warm, typewriter-inspired monospace. Used as
// a freely-licensed stand-in for Cohere's proprietary faux-mono brand typeface.
const brandFont = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-brand",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Medical Billing Extraction",
  description: "Upload medical billing PDFs and review extracted records.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={brandFont.variable}>
      <body>{children}</body>
    </html>
  );
}
