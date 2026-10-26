import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Keep trailing slashes intact — Django's APPEND_SLASH + Next normalization
  // would otherwise create a /api/.../ redirect loop through the proxy.
  skipTrailingSlashRedirect: true,
  experimental: {
    // The dev proxy clones request bodies through a 10MB-capped stream by
    // default; larger PDF uploads arrived truncated at Django (multipart
    // parse 400s) and the cut stream also caused socket hang ups (plain
    // 500s). Match Django's DATA_UPLOAD_MAX_MEMORY_SIZE (512MB).
    middlewareClientMaxBodySize: "512mb",
    // Large uploads need more than the 30s default proxy timeout.
    proxyTimeout: 10 * 60 * 1000,
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/media/:path*", destination: `${BACKEND}/media/:path*` },
    ];
  },
};

export default nextConfig;
