import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "PriceCast — know the price before you leave the farm",
  description:
    "Weekly crop price forecasts for Kenyan smallholder farmers, built on KAMIS market data. Honest confidence, backtested against the last known price, delivered by SMS.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f6f4" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0d0d" },
  ],
};

/* Stamp the theme before first paint so the toggle never flashes. */
const THEME_SCRIPT = `(function(){try{var s=localStorage.getItem('pricecast-theme');var m=window.matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.setAttribute('data-theme',(s==='light'||s==='dark')?s:(m?'dark':'light'));}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col antialiased">{children}</body>
    </html>
  );
}
