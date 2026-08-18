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
  images: { formats: ["image/avif", "image/webp"] },
  // /how-it-works and /for-parents were duplicates of homepage sections.
  // Permanent redirects so old links and any indexed URLs land on the content.
  async redirects() {
    return [
      { source: "/how-it-works", destination: "/#how-it-works", permanent: true },
      { source: "/for-parents", destination: "/#for-parents", permanent: true },
    ];
  },
};

export default nextConfig;
