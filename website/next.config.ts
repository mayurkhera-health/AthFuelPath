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
