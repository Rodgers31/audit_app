# Build and runtime use the same glibc base for native optional dependencies.
FROM node:22-bookworm-slim AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

FROM base AS dependencies
# npm ci needs the lockfile's peer policy and the local ESLint package.
COPY package.json package-lock.json .npmrc ./
COPY eslint-rules ./eslint-rules
# Keep build tools and native optional packages. Only skip ONNX's extra GPU
# download; its bundled CPU binaries and other dependency scripts remain intact.
RUN ONNXRUNTIME_NODE_INSTALL=skip npm ci --include=dev --include=optional --no-audit --no-fund

# Docker Compose selects this target for its source bind mount.
FROM dependencies AS development
ENV NODE_ENV=development
ENV PORT=3000
COPY --chown=node:node . .
RUN chown node:node /app
USER node
EXPOSE 3000
CMD ["npm", "run", "dev"]

FROM dependencies AS builder
COPY . .
# Next.js inlines NEXT_PUBLIC_* values at build time. Pass public values only.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN node scripts/container-config.cjs validate && npm run build && node scripts/container-config.cjs record
# Prune after Tailwind, TypeScript and ESLint have finished the build. Optional
# production dependencies (including Next's Sharp image decoder) are retained.
RUN npm prune --omit=dev --include=optional --ignore-scripts --no-audit --no-fund
# Build caches are disposable; the nonroot runtime can recreate its own cache.
RUN rm -rf .next/cache

FROM base AS runner
# next.config.js is evaluated again by next start. Keep its public API/image
# host config aligned with the values embedded during the build.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/package.json /app/package-lock.json ./
COPY --from=builder --chown=node:node /app/next.config.js ./
COPY --from=builder --chown=node:node /app/lib/config ./lib/config
COPY --from=builder --chown=node:node /app/scripts/container-config.cjs ./scripts/container-config.cjs
COPY --from=builder --chown=node:node /app/node_modules ./node_modules
USER node
EXPOSE 3000
# Public readiness endpoint: no auth cookies or backend connection required.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "const req=require('http').get('http://127.0.0.1:'+process.env.PORT+'/api/health',res=>{res.resume();process.exit(res.statusCode===200?0:1)});req.on('error',()=>process.exit(1));req.setTimeout(3000,()=>{req.destroy();process.exit(1)});"
CMD ["sh", "-c", "node scripts/container-config.cjs runtime && exec npm start"]
