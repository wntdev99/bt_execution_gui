/** @type {import('next').NextConfig} */
const API_PROXY = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // dev 환경에서 /api/* 와 /ws 를 bt_web_bridge 로 프록시.
    // 운영에서는 nginx 가 같은 origin 으로 라우팅 (CORS 회피).
    return [
      { source: '/api/:path*', destination: `${API_PROXY}/api/:path*` },
    ];
  },
};

export default nextConfig;
