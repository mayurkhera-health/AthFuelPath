import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Fly runs this as a container: standalone emits a self-contained server.js
  // plus only the node_modules actually imported, so the image stays small.
  output: "standalone",
  // Without this Next infers a workspace root above the project and nests the
  // standalone build under .next/standalone/<project>/, which silently breaks
  // the COPY paths in the Dockerfile. Pin the root to this directory.
  outputFileTracingRoot: path.join(__dirname),
  /**
   * WebP only, deliberately. AVIF was first in this list and Safari rendered
   * some of the app captures as a blank frame with a broken-image glyph — the
   * bytes arrived and the decoder gave up. The sources were valid WebP, byte
   * identical in format to captures that rendered fine, so the failure was in
   * the AVIF the optimizer produced, not in the input.
   *
   * WebP is universally supported and gives most of the saving. A slightly
   * larger image beats a hero that does not render for Safari users. Do not add
   * AVIF back without testing every capture in Safari first.
   */
  images: { formats: ["image/webp"] },
  // /how-it-works and /for-parents were duplicates of homepage sections.
  // Permanent redirects so old links and any indexed URLs land on the content.
  /**
   * Security headers. The site had none before 2026-08-29.
   *
   * CSP is the important one and it is NOT strict: Next's App Router injects
   * inline scripts to stream the RSC payload, so 'unsafe-inline' is required
   * for script-src without a nonce middleware. What it still buys is the thing
   * that matters most for a marketing site — no script from any other origin
   * can execute, no frame can embed us, and no form can post anywhere else.
   * Tightening to a nonce needs middleware and is a separate change.
   *
   * HSTS deliberately omits `preload`. Preload is a one-way door enforced by
   * browser vendors and this site is not on its final domain yet.
   */
  async headers() {
    const csp = [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self'",
      "connect-src 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "object-src 'none'",
      "upgrade-insecure-requests",
    ].join("; ");
    return [{
      source: "/:path*",
      headers: [
        { key: "Content-Security-Policy", value: csp },
        { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
        { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
      ],
    }];
  },
  async redirects() {
    return [
      { source: "/how-it-works", destination: "/#how-it-works", permanent: true },
      /* Straight to /parents, not to /#for-parents.
         This used to 308 to the homepage anchor, and since /parents exists that
         became a CHAIN: 308 -> /#for-parents -> a client-side hop to /parents.
         A permanent redirect is cached by browsers and search engines, so the
         chain would have outlived the decision that created it. */
      { source: "/for-parents", destination: "/parents", permanent: true },
      /* Pricing is hidden while the product is pre-launch and the price is not
         committed. TEMPORARY (permanent: false) on purpose — a 308 would be
         cached by browsers and search engines and would outlive the decision. */
      { source: "/pricing", destination: "/", permanent: false },
      /* Login is hidden until the app is open to families. Temporary for the
         same reason as /pricing: this comes back, and a cached 308 would not. */
      { source: "/login", destination: "/", permanent: false },
    ];
  },
};

export default nextConfig;
