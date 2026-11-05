/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    if (process.env.VERCEL) {
      return [];
    }
    const apiBase = (
      process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000"
    ).replace(/\/$/, "");
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
