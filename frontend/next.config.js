/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow the backend to be called from a relative /api proxy in dev.
  async rewrites() {
    return [
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
