import type { Metadata } from "next";
import "@fontsource-variable/hanken-grotesk";
import "@fontsource/unbounded/400.css";
import "@fontsource/unbounded/500.css";
import "@fontsource/unbounded/600.css";
import "./globals.css";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "oalgo2 Observatory",
  description: "Quantitative stock research and paper trading for NYSE and NASDAQ listings. Research only; no real orders.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
