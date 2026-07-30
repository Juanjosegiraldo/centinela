import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export: the console is a client-side SPA, so it ships as static HTML
  // and can be hosted on Azure Storage static website / Static Web Apps.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
