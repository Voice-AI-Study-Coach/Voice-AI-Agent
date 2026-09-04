import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The floating dev badge sits bottom-left, exactly where the sidebar's
  // profile row is.
  devIndicators: false,

  // Uploads are proxied through Next (see rewrites below), and the proxy
  // truncates request bodies past this limit - the backend then waits for
  // bytes that never arrive and the socket hangs up mid-upload, with no
  // request ever reaching FastAPI to log or reject it. Scanned and
  // handwritten PDFs are page images, so a set of notes that is 1MB printed
  // is 20MB scanned, and multipart encoding adds more on top of the raw file
  // size.
  //
  // Effectively uncapped so the proxy never truncates: MAX_UPLOAD_BYTES in
  // backend/config.py is the real limit, and rejecting there gives a clean
  // 413 instead of a hung socket. Note the backend reads the whole upload
  // into memory to hash it, so that limit is what keeps a large file from
  // exhausting the process - this setting must not become the only guard.
  experimental: {
    proxyClientMaxBodySize: Number.MAX_SAFE_INTEGER,
  },

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
