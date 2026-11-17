/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  // Live updates are a long-lived event stream; compressing it would buffer the events.
  compress: false,
  // The browser talks only to this server. /api is forwarded to the research backend, so the
  // dashboard works from any address (another device, a preview link) without the backend being exposed.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
export default nextConfig;
