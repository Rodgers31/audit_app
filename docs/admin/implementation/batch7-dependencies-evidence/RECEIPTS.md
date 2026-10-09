# Executed receipts — 9 October 2026

Source: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`; baseline lock SHA256 `dac3afaab71df334fc5e7d1c1a918c307f8a71fd750b91b1672546b044a0de5c`; final lock SHA256 `b3b3289f728d8a338815e8457d2fc509030dcc44e457eed733610ebe56ddd51a`.

Working directory for npm commands: `/Users/roger/.codex/worktrees/batch7-dependencies/audit_app/frontend`.
Every author npm/Node invocation uses `env -i PATH=/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/bin:/bin:/usr/sbin:/sbin`; registry/install commands additionally pass `--cache /Users/roger/.codex/worktrees/batch7-dependencies/npm-cache --userconfig /dev/null`. The project `.npmrc` retains `legacy-peer-deps=false`. No primary dotenv files are copied or loaded. Node reports `v22.19.0`, macOS arm64.

| Exact command / selected configuration | Result and artifact |
| --- | --- |
| `git rev-parse HEAD`; `git status --short` before branch creation | Exact pinned SHA; owned clean checkout. |
| `npm ci --no-audit --no-fund` (old lock) | exit 0, 961 packages; `baseline-install.log`. |
| `npm audit --omit=dev --json`; `npm audit --json` before edits | exit 1, five high production entries / 38 total full entries; `baseline-*-audit.json`. |
| `npm why braces sprintf-js --json` | Actual old/final installed caller chains, `baseline-callers.json`, `final-callers.json`. |
| `gh api /advisories/GHSA-vfj7-8cjw-p6xm`; `gh api /advisories/GHSA-hp3w-g68c-fv3c` | Authoritative bodies; both patched versions null. Registry HTTP GET metadata for 12 inventoried packages captured in `registry-metadata.json`. |
| `npm ci --omit=dev --include=optional --no-audit --no-fund` in copied baseline/final manifest roots | Both exit 0; old 280 installed packages. Copies contain owned manifest/lock/.npmrc/local ESLint files only. |
| `node scripts/verify-runtime-dependencies.cjs /Users/roger/.codex/worktrees/batch7-dependencies/runtime-baseline` | exit 1: `tailwindcss must be absent`; `runtime-red.log`. |
| Same command targeting `runtime-final` | exit 0 after retaining production Sharp; real PNG→WebP and all package inventory (142 packages), `runtime-green.log` / independent replay. Initial omission of shared native binaries failed actual Sharp loading and was repaired. |
| `RUNTIME_VERIFY_ROOT=/Users/roger/.codex/worktrees/batch7-dependencies/runtime-final node --test scripts/runtime-dependencies.test.cjs` | Four controls plus parent: real decoder positive; nested actual braces, malformed dependency maps and absent decoder negatives. `runtime-regressions-green.log`. |
| `npm ci --include=dev --include=optional --no-audit --no-fund` (final lock) | exit 0, fresh isolated full installation; `final-install.log`. |
| `npm ls --all --json` | exit 0, no peer problems; `final-tree.json`. |
| `npm test -- --ci --coverage --runInBand` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:43194`, Supabase env unset | exit 0, 144 suites, 1,932 pass, one existing skip; `final-jest.log`. Initial unnecessary inert Supabase settings caused two fake-timer failures; clean isolated retry control passes 19/19. |
| `npm run lint -- --max-warnings=0`; `node node_modules/typescript/bin/tsc --noEmit` | Both exit 0; `final-lint.log`, `final-types.log`. |
| `npm run build` old/final | Both exit 0; explicit inert API `http://127.0.0.1:43194`, Supabase `http://127.0.0.1:58173`, anon value `batch7-inert-anon-key`, telemetry disabled. `baseline-build.log`, `final-build.log`. |
| `NATIVE_VERIFY_CACHE_DIR=/Users/roger/.codex/worktrees/batch7-dependencies/model-cache npm run verify:native`; `npm run verify:dependency-tooling` old/final | exit 0; fixed public model, native inference, ZIP lookup/extraction and image controls; parser caller resolution and real CSS behavior. `baseline-native-macos.log`, `final-native-macos.log`, `baseline-tooling.log`, `final-tooling.log`. |
| `node --import ./pinned-cache.mjs scripts/build-embeddings.mjs` in `builder-fixture` | exit 0, actual byte-identical builder encodes all 264 copied chapters/articles using pinned local-only model bytes; fixture outputs only. `final-actual-builder-macos.log`. |
| `node tests/batch7DependencyBrowser.cjs` old/final; `DEPENDENCY_PREVIEW_URL=http://127.0.0.1:43193`, same owned model cache, `PLAYWRIGHT_BROWSERS_PATH=/Users/roger/Library/Caches/ms-playwright` | exit 0, real UI and WASM, fallback control; both queries/rankings/resource receipts exactly equal. `baseline-browser.log`, `final-browser.log`, `compatibility-summary.json`. |
| Pruned `node node_modules/next/dist/bin/next start -H 127.0.0.1 -p 43193`; curl `/api/health`; `/_next/image?url=http%3A%2F%2F127.0.0.1%3A43194%2Fred.png&w=16&q=75` with Accept image/webp | HTTP 200; actual 68-byte WebP returned. Local static image fixture uses read-only Python runtime, `PYTHON_DOTENV_DISABLED=1`, port 43194. `final-pruned-preview.log`, `next-image-headers.txt`, `next-image.webp`. |
| Final `npm audit --omit=dev --json`; `npm audit --json` | exit 0 production / exit 1 full. Zero production entries; same 38 full entries; exact JSON outside git with hashes. |

Linux uses `docker run --rm --platform linux/amd64` and image `node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392`. Source/lock copy is beneath `/Users/roger/.codex/worktrees/batch7-dependencies/linux-amd64/frontend`, never another installation. Node reports `22.23.3` / Linux x64 under emulation. Install uses `ONNXRUNTIME_NODE_INSTALL=skip npm ci --include=dev --include=optional --no-audit --no-fund`. Actual native verifier, tooling and builder pass in the accepted **serial** `final-linux-amd64-native-builder.log`. Builder preload disables remote models and loads owned pinned `/models/` bytes. Native verifier still requests public metadata; the denied-network failure is retained in `final-linux-amd64-native-tooling.log`, not reported as a pass.

Linux `npm run build` → `npm prune --omit=dev --include=optional --ignore-scripts --no-audit --no-fund` → runtime verifier passes; `final-linux-amd64-build-prune.log`. After native/builder verification, restore shipped assets in the fixture, prune again and execute the final all-directory inventory; `final-linux-runtime-inventory.log` reports 145 packages and real decoder success. Network-disabled `batch7-dependencies-preview-amd64` serves `/api/health` and `/learn` HTTP 200 via actual `docker exec -i ... node` fetches; `final-linux-preview-http.log`. It has no published ports.

Compatibility controls compare all lock package versions/URLs/integrities, four CSS byte hashes and real browser output, rather than relying on audit counts. Model/coverage/build/generated artifacts remain external. `artifact-manifest.json` records exact filenames, byte lengths and SHA256 digests for raw evidence.

Independent review findings, repairs, regression state, exclusions and resource cleanup are in `REVIEW.md` and `DELIVERY.md`. Hosted Actions/security/quality jobs, backend/ETL gates, the complete legacy E2E matrix, other platforms/browsers and GPU execution remain unexecuted. This is local packaging and compatibility evidence; #494 stays open.
