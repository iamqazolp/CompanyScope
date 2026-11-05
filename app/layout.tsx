import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CompanyScope — Verified SEC Filing, XBRL & Multi-Agent Equity Research",
  description:
    "Zero-hallucination multi-agent financial research terminal combining SEC 10-K/10-Q/8-K Hybrid RAG, authoritative XBRL statements, earnings commentary, and live market sentiment with 100% verified citations.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} dark`}>
      <body className="min-h-screen bg-[#080c14] text-slate-100 font-sans selection:bg-emerald-500/25 selection:text-emerald-200">
        {children}
      </body>
    </html>
  );
}
