import type { Metadata } from "next";
import "./globals.css";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "oalgo2 Research Command Center",
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
