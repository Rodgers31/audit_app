# Frontend container packaging verification — 2026-10-08

Scope: issue #511, the frontend Docker build and runtime packaging. Work was performed in the isolated `codex/frontend-container-packaging-511` checkout based on main `3dfc7b9e57311fc38f02683b9ce1985fd4365fe3`.

## Baseline reproduction

A temporary context containing HEAD's unmodified Dockerfile and manifests failed in Docker on Linux arm64 at `npm ci --only=production`, before source copy or compilation. npm reported `ERESOLVE`: react-simple-maps 3.0.0 requires React 16.8/17/18 while the app installs React 19.2.4. The original Dockerfile copies neither `.npmrc` nor the local ESLint package before installation. Evidence: `baseline-default-arm64.log` in the local evidence directory.

## Packaging changes

Both Dockerfiles use Node 22 on Debian Bookworm slim so build and runtime share the same glibc platform for native optional packages. The dependency stage copies `package.json`, `package-lock.json`, the checked-in `.npmrc`, and the `file:./eslint-rules` package before `npm ci --include=dev --include=optional`. Tailwind typography, TypeScript, and ESLint are available during `next build`; production pruning runs after that build and retains optional packages required by Next image optimization. A separate builder instruction removes `.next/cache` after pruning, so webpack build caches are excluded from the runtime image.

Dependency lifecycle scripts remain enabled during installation. `ONNXRUNTIME_NODE_INSTALL=skip` skips ONNX Runtime's extra unbundled GPU downloads and retains the CPU binaries already shipped in its npm package. This behavior is defined by the [ONNX Runtime 1.30 installer](https://github.com/microsoft/onnxruntime/blob/v1.30.0/js/node/script/install.js). The glibc base follows the [official Node image guidance](https://github.com/nodejs/docker-node/blob/main/README.md) and the native platform requirements in the [Sharp installation documentation](https://sharp.pixelplumbing.com/install/).

The default Dockerfile also provides a `development` target with the full build dependency tree, `npm run dev`, and nonroot source/cache ownership. The frontend Compose service selects this target and sets `NODE_ENV=development`, so its source bind mount starts a development server instead of hiding a production build under `npm start`.

The runtime contains `.next`, public assets, production dependencies, and `next.config.js`, starts with `npm start`, and runs as the image's nonroot `node` user. The existing `/api/health` route returns HTTP 200 and `{ "status": "ok" }`; anonymous middleware bypasses Supabase session refresh for this public route. The Docker health command now handles connection errors and times out after three seconds.

`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `NEXT_PUBLIC_API_URL` are explicit build arguments. Public values must be supplied for the intended deployment at build time because Next embeds them in browser output. The runtime repeats the same public build values so reevaluating `next.config.js` preserves the API rewrite destination and image host configuration. The API argument's default remains `http://localhost:8000`, matching `next.config.js`. No public API routing or data semantics were changed.

## Context isolation

A synthetic context was built with Docker's own `COPY` filtering and the frontend `.dockerignore` exclusion rules. It excluded `.env`, `.env.local`, `.env.canary`, `.key`, `.pem`, `node_modules`, and `.next` canaries; it retained `.npmrc`, `eslint-rules`, and the permitted `.env.example`. Real environment files or production credentials were never read or passed into these builds.

Local evidence directory: `/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170/DEPENDENCY_511_2026-10-08/docker`.

## Development bind mount

The Linux arm64 development image was started with a copied tracked-source fixture mounted at `/app`, a fresh named volume at `/app/node_modules`, and no `.next` volume. It ran as UID 1000, retained `@tailwindcss/typography`, served `/api/health` with HTTP 200, created `.next`, and wrote a synthetic file into that cache. Its temporary container and dependency volume were removed. This verifies Docker Desktop on macOS; Linux source mounts whose owner differs from container UID 1000 may require the usual ownership adjustment.

## Health failure handling

The exact production image health command was executed against isolated containers with an absent server, an HTTP 500 fixture, and a listening fixture that never answered. All returned exit 1; the timeout fixture exited after 3.06 seconds. Healthy production readiness returned exit 0. These results come from the Docker command itself. Evidence: `health-negative-results.json`.

## Build and runtime results

| Dockerfile | Platform | Build | Runtime | Local image tag |
| --- | --- | --- | --- | --- |
| `frontend/Dockerfile` | `linux/arm64` | Pass, 71.11 seconds | Pass | `audit-frontend511-default-arm64` |
| `frontend/Dockerfile.prod` | `linux/arm64` | Pass, shared cache | Pass | `audit-frontend511-prod-arm64` |
| `frontend/Dockerfile` | `linux/amd64` | Pass, 121.82 seconds | Pass | `audit-frontend511-default-amd64` |
| `frontend/Dockerfile.prod` | `linux/amd64` | Pass, shared cache | Pass | `audit-frontend511-prod-amd64` |

Before build-cache removal, all four full runtime checks reported Node 22.23.3, UID 1000, Sharp 0.35.5, and libvips 8.18.7. Checks passed for:

- `/api/health`, `/learn`, a generated JavaScript asset, and Next's `/_next/image` endpoint, all HTTP 200.
- Native Sharp PNG encoding and WebP resize/metadata through Next's own dependency resolution.
- Absence of development-only Tailwind typography from the production tree and absence of `.env` files from runtime `/app`.
- Public API/Supabase build values persisted without runtime overrides, configured image hostname matched the nondefault API host, and built rewrite metadata matched reevaluated runtime config.
- An actual `/api/v1/container-packaging-smoke` rewrite reached a synthetic HTTP server on container loopback port 8000 and returned its expected JSON fixture.
- The exact image health command returned exit 0 for readiness.

Runtime containers used `--network none` and no host ports. Temporary verification containers were removed. Linux arm64 ran natively on Docker Desktop; Linux amd64 ran under Docker Desktop emulation. Authenticated service integration and browser WASM inference are separate checks; these container checks use inert configuration and local fixtures.

The two architectures contain comparable production trees. Docker's size before loading an emulated image can reflect only compressed content; post-runtime image metadata records the unpacked size for both. The final image retains the declared production dependency tree, including bundled ONNX CPU binaries, and the Next build output. After build-cache removal, all four tags were rebuilt and rechecked: `.next/cache` was absent before server startup; the real Next image endpoint returned HTTP 200 and created `.next/cache/images`; UID 1000 could write that cache; readiness returned HTTP 200; the actual health command exited 0. These assertions are recorded against the final image metadata in `final-cache-runtime-results.json`.

Removing the 424 MB build cache reduced the shipped `.next` tree from 466 MB to 42 MB on both architectures. Post-runtime Docker image accounting reports 1,888,127,709 bytes for arm64 and 1,888,766,977 bytes for amd64 (about 1.89 GB each), down from about 2.40 GB each. Production `node_modules` remains about 1.1 GB. Evidence: `final-image-sizes.json`; original full build/runtime receipts are preserved under `before-build-cache-removal/`.

## Reproduction commands

Run from the repository root; these public values are deliberately inert:

```sh
for platform in linux/arm64 linux/amd64; do
  arch=${platform#linux/}
  for kind in default prod; do
    dockerfile=frontend/Dockerfile
    if [ "$kind" = prod ]; then dockerfile=frontend/Dockerfile.prod; fi
    docker buildx build --load --platform "$platform" --file "$dockerfile" \
      --tag "audit-frontend511-$kind-$arch" \
      --build-arg NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 \
      --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY=local-container-verification-placeholder \
      --build-arg NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 frontend
  done
done

docker buildx build --load --platform linux/arm64 --target development \
  --file frontend/Dockerfile --tag audit-frontend511-development-arm64 frontend
```

Exact build commands, manifest/Dockerfile SHA-256 hashes, image metadata, and individual logs are saved as `audit-frontend511-*-build.json` and `audit-frontend511-*-build.log`. `runtime-results.json`, `final-cache-runtime-results.json`, `development-runtime.json`, `health-negative-results.json`, and `context-canary.json` hold the individual assertions. The local `verify_runtime.py`, `verify_image_cache.py`, `verify_development.py`, and `verify_health_failures.py` scripts reproduce the fixture checks.

No GitHub Actions, production deployment, real credentials, primary checkout, or primary port-3000 service were used by this verification.

## Independent verification and browser search

A separate reviewer executed the actual native production health command against absent, HTTP 500, HTTP 302, and nonanswering servers; each exited 1, including the bounded timeout. The real Next health endpoint exited 0. Independent checks also confirmed nonroot Sharp encoding, configured public API/image hosts, and the canonical Compose development configuration. Receipts are under `peer-map/independent-packaging/` in the coordinator evidence directory.

Production pruning does not mean every package originally listed under devDependencies disappears: Next's optional peer keeps `@playwright/test` in the resolved runtime tree, and TypeScript is already declared as a production dependency. Jest, ESLint, the local ESLint plugin and Tailwind typography were confirmed absent. This change preserves the declared production dependency contract rather than manually deleting peer packages.

The coordinator also opened `/learn` from the final cache-cleaned arm64 production container in real Chromium on an ephemeral localhost port. All 42 requested built JavaScript chunks returned HTTP 200. The actual page search ran with the real quantized MiniLM model and ONNX WASM runtime; only their remote resource responses were fulfilled from the previously verified local public cache. The model revision was `751bff37182d3f1213fa05d7196b954e230abad9`. Application code, embeddings, search results and computation were not stubbed.

A separate fresh browser context denied model availability as a negative control. It instantiated no WASM runtime and used the app's normal BM25 fallback. With the model available, the real runtime instantiated successfully, the presidential-term query moved Article 142 from rank 2 to rank 1, and the rights query retained Article 43 at rank 1. Both result lists changed compared with the fallback. This prevents a silently empty semantic result from being counted as success. No page errors or missing fixtures occurred, and no production network endpoints were contacted.

These two query checks verify packaged browser search, not exhaustive semantic ranking accuracy or all browser/device combinations. The earlier source-exposing webpack diagnostic was rejected because Next concatenates the semantic module into the page component; it is not a passing receipt. The accepted verification drives the actual page UI and observes real WASM instantiation. Final receipts: `final-container-search-ui.log`, `container-search-ui.json`, `container-search-ui.cjs`, and `container-learn-search.png` in the coordinator evidence directory.
