/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "/api",
    NEXT_PUBLIC_ADMIN_API_BASE_URL: process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL || "/api",
  },
};

export default nextConfig;
