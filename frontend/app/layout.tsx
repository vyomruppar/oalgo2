import type { Metadata } from "next";
import "@fontsource-variable/hanken-grotesk";
import "@fontsource/unbounded/400.css";
import "@fontsource/unbounded/500.css";
import "@fontsource/unbounded/600.css";
import "./globals.css";
import Shell from "@/components/Shell";
import { authEnabled } from "@/lib/auth";

export const metadata: Metadata = {
  title: "oalgo2 Observatory",
  description: "Quantitative stock research and paper trading for NYSE and NASDAQ listings. Research only; no real orders.",
};

// read login settings at request time, not at build time
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans">
        <Shell signOut={authEnabled()}>{children}</Shell>
      </body>
    </html>
  );
}
