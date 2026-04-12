/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  transpilePackages: ['react-plotly.js', 'plotly.js'],
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
    };

    config.resolve.fallback = {
      ...config.resolve.fallback,
      buffer: require.resolve("buffer/")
    };

    return config;
  },
};

module.exports = nextConfig;