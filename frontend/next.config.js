/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // The rewrite proxy aborts with a 500 after 30 s by default; Gemini answers that fall back
    // across models/keys, and long Sarvam read-alouds, can take longer than that.
    proxyTimeout: 120_000,
  },
  // Allow the backend to be called from a relative /api proxy in dev.
  async rewrites() {
    return [
      {
        // Backend mounts this router under /api itself, so keep the prefix (must precede /api/:path*).
        source: "/api/audit-report",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/audit-report`,
      },
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/:path*`,
      },
      {
        source: "/simulator/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/simulator/:path*`,
      },
      {
        source: "/sarvam/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/sarvam/:path*`,
      },
      {
        source: "/heatmap-api/:path*",
        destination: `${process.env.HEATMAP_API_URL ?? "http://localhost:8001"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
