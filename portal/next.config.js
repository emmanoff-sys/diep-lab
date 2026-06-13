/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Backend-for-frontend proxy is now a server-side route handler
  // (app/api/diep/[...path]/route.ts) so it can inject the Phase 9J auth token.
  // The previous transparent rewrite could not add the Authorization header.
};

module.exports = nextConfig;
