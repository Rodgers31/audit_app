const { validateHttpBaseUrl } = require('./lib/config/public-config.cjs');
const suppliedApi = process.env.NEXT_PUBLIC_API_URL;
const publicApi = validateHttpBaseUrl(
  suppliedApi === undefined && process.env.NODE_ENV !== 'production'
    ? 'http://localhost:8000'
    : suppliedApi,
  'NEXT_PUBLIC_API_URL'
);

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Tree-shake barrel imports from heavy libraries. Next transforms
  //   import { X } from 'lucide-react';
  // into a direct deep-path import so only the symbols you use are bundled.
  experimental: {
    optimizePackageImports: ['lucide-react', 'recharts', 'framer-motion', 'date-fns', 'lodash'],
    // Restore scroll position on browser back/forward. Without this,
    // navigating from /counties?p=2 → /counties/001 → back drops the
    // user at top of /counties instead of where they clicked.
    scrollRestoration: true,
  },
  // @huggingface/transformers + onnxruntime-node are browser-only — the
  // Learn page dynamically imports them inside a `typeof window` guard.
  // Next's file tracer still pulls the 350MB onnxruntime-node binary into
  // every serverless function bundle, blowing Vercel's 250MB limit.
  // Exclude the whole native-binary tree from the deployment trace so
  // server bundles stay lean; browser code still gets transformers.js
  // via its own chunk.
  outputFileTracingExcludes: {
    '*': [
      'node_modules/@huggingface/**',
      'node_modules/onnxruntime-node/**',
      'node_modules/onnxruntime-web/**',
      'node_modules/onnxruntime-common/**',
    ],
  },
  images: {
    remotePatterns: [
      {
        protocol: 'http',
        hostname: 'localhost',
      },
      // Production API domain — add your backend hostname here
      ...(publicApi
        ? [
            {
              protocol: new URL(publicApi).protocol.replace(':', ''),
              hostname: new URL(publicApi).hostname,
            },
          ]
        : []),
    ],
  },
  env: {
    NEXT_PUBLIC_API_URL: publicApi,
    NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME || 'Kenya Audit Transparency',
    NEXT_PUBLIC_APP_VERSION: process.env.NEXT_PUBLIC_APP_VERSION || '1.0.0',
  },
  // Proxy API requests through Next.js to avoid CORS preflight overhead
  // Browser → Next.js (:3000/api/v1/*) → FastAPI (:8000/api/v1/*)
  // The unaccounted-funds page lists findings the Auditor-General's report
  // itself heads "Unaccounted" or "Loss of Funds" (issue #233). "Missing" is
  // not the report's word, so the page left that URL; old links still land.
  async redirects() {
    return [
      {
        source: '/accountability/missing-funds',
        destination: '/accountability/unaccounted-funds',
        permanent: true,
      },
    ];
  },
  async rewrites() {
    // Production rewrites are baked into routes-manifest at build time. Only
    // the development server reevaluates an internal address on config load.
    const apiUrl = process.env.NODE_ENV === 'development' && process.env.INTERNAL_API_URL !== undefined
      ? validateHttpBaseUrl(process.env.INTERNAL_API_URL, 'INTERNAL_API_URL')
      : publicApi;
    // eslint-disable-next-line no-console
    console.log(`[next.config] API rewrite target: ${apiUrl}`);
    return [
      {
        source: '/api/v1/:path*',
        destination: `${apiUrl}/api/v1/:path*`,
      },
    ];
  },
  // Add caching headers for static and API responses
  async headers() {
    // In dev, static chunks are rebuilt in-place with the same URL, so
    // "immutable" traps browsers on stale bundles across HMR cycles.
    // Only pin them in production where filenames are content-hashed.
    if (process.env.NODE_ENV !== 'production') {
      return [
        {
          source: '/_next/static/:path*',
          headers: [{ key: 'Cache-Control', value: 'no-store, must-revalidate' }],
        },
      ];
    }
    return [
      {
        // Cache static assets aggressively in production (content-hashed URLs)
        source: '/_next/static/:path*',
        headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }],
      },
    ];
  },
};

module.exports = nextConfig;
