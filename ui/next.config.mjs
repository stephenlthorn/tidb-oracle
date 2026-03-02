/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: '.next-runtime',
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb'
    }
  }
};

export default nextConfig;
