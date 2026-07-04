import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,

  // 用這個方式強制設定 @/* alias（不依賴 tsconfig 的 baseUrl）
  turbopack: {
    resolveAlias: {
      "@/*": "./src/*",
    },
  },
};

export default nextConfig;