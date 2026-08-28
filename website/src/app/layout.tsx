import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { SITE_URL, IS_PRODUCTION_SITE } from "@/lib/site-url";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { StickyBar } from "@/components/StickyBar";

// next/font emits a size-adjusted fallback, which holds CLS at 0 through the swap.
const hanken = localFont({
  src: "../../public/fonts/hanken-grotesk-latin-wght-normal.woff2",
  weight: "100 900",
  // "optional": the fallback is size-adjusted but glyph widths still differ, so a
  // swap re-wraps the hero h1 and shifts everything under it (measured CLS 0.203
  // on throttled mobile). "optional" gives the font a 100ms block window, then
  // keeps the fallback for that paint and caches the font for every later view —
  // CLS 0 at the cost of one uncached slow-connection visit rendering in fallback.
  display: "optional",
  variable: "--font-hanken",
  preload: true,
});

const defaultDescription =
  "AthFuelPath turns your player's practices, games and tournaments into personalised fueling guidance — so they know what to eat, when to eat, and why it matters. For soccer players 13–17.";
const defaultImage = `${SITE_URL}/og/home.jpg`;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "AthFuelPath — sports nutrition built around your soccer player's schedule",
    template: "%s · AthFuelPath",
  },
  description: defaultDescription,
  alternates: { canonical: SITE_URL },
  openGraph: {
    title: "AthFuelPath — fuel smarter, play stronger",
    description: "Sports nutrition built around your soccer player's schedule.",
    url: SITE_URL,
    type: "website",
    siteName: "AthFuelPath",
    images: [{ url: defaultImage, width: 1200, height: 630, alt: "AthFuelPath — fuel smarter, play stronger" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "AthFuelPath — fuel smarter, play stronger",
    description: "Sports nutrition built around your soccer player's schedule.",
    images: [defaultImage],
  },
  robots: IS_PRODUCTION_SITE ? { index: true, follow: true } : { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#0B1F17", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={hanken.variable}>
      <body>
        <a href="#main" className="skip-link">Skip to content</a>
        <Header />
        <main id="main" className="page">{children}</main>
        <Footer />
        <StickyBar />
      </body>
    </html>
  );
}
