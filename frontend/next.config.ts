import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The floating dev badge sits bottom-left, exactly where the sidebar's
  // profile row is.
  devIndicators: false,

  // The backend sets an HttpOnly cookie, so requests must be same-origin for
  // the browser to send it. Proxying /api through Next avoids third-party
  // cookie rules entirely.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
