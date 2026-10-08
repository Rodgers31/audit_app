# PR #516 public build and server API configuration verification

Date: 2026-10-08. Reviewed baseline: `2014b826d8efb2490eb124bb9233a2f8f73c25ab`.

## Review conclusions and contract

Inline comments 4221380956 and 4221381056 are valid. Both Dockerfiles supplied a silent localhost public API default, and the Docker deployment workflow supplied only the two Supabase build arguments. Next embeds public API configuration into browser JavaScript, as documented in its [version 15 environment variable guide](https://nextjs.org/docs/15/app/guides/environment-variables). A Compose runtime API variable cannot repair that JavaScript.

The additional SSR finding is also valid. County list, county detail and debt Server Components prefetch through the same API functions and Axios client used by the browser. Container loopback is not the backend service address. The shared API base selector now uses optional runtime `INTERNAL_API_URL` on the server, while browser requests keep the public API address. Without an internal override, server requests retain the public fallback used by non-container deployments.

Production Docker builds require three explicit public values:

- `NEXT_PUBLIC_API_URL`: absolute HTTP(S) base URL, matching the deployment's public backend hostname and scheme.
- `NEXT_PUBLIC_SUPABASE_URL`: absolute HTTP(S) URL.
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: nonblank public anonymous key.

URLs reject blank values, whitespace, malformed authority, embedded credentials, query strings and fragments. Trailing slashes normalize consistently. General production Next configuration requires the explicit API URL; the additional required auth checks are limited to Docker's public configuration guard.

Each production image records these three normalized public values in `.next/public-build-config.json`. Its default startup command validates that the runtime values still match before `next start`. Disagreement requires rebuilding the image. Errors identify the variable without printing the supplied value. The marker contains no internal address. `INTERNAL_API_URL` is validated separately and can vary at runtime.

Production rewrites remain built with the public URL in `routes-manifest.json`. Setting runtime `INTERNAL_API_URL` changes server Axios requests, not those built rewrites. The development Next server can use the internal URL for rewrites when it loads configuration. No startup route-manifest mutation or browser proxy migration was introduced.

## Deployment wiring

The manually dispatched Docker workflow requires `public_api_url`. Structured step environment values supply it to the Next build and the configuration preflight. Structured Docker action build arguments supply it to the frontend image. The input is not interpolated into shell commands and is not a global environment value for unrelated jobs. Preflight validates all three public values before registry login or either image push. The workflow also runs the new focused Node regression tests.

All four Compose frontend definitions supply server-only `INTERNAL_API_URL=http://backend:8000`. Root `docker-compose.yml` retains its source-mounted development target and browser `http://localhost:8000`. Hosted dev uses HTTP; QA and production use HTTPS. Hosted definitions require `BACKEND_HOST`, which must match the URL used to build the selected image. Their runtime public override is checked by the image entrypoint.

Hosted `docker-compose.dev.yml` runs a compiled production image with `next start`, so its `NODE_ENV` is now production. This differs from root Compose's `npm run dev` target. No backend, ETL, data, dependency manifest or lockfile changes were needed for these configuration fixes.

## Reproduction before the fix

Evidence directory:
`/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170/REVIEW_516_2026-10-08/config`

| Receipt | Observed baseline behavior |
| --- | --- |
| `baseline-missing-api-red.log` | Production Next configuration accepted a missing API URL and selected localhost. |
| `baseline-api-selection-red.log` | Actual baseline Axios/endpoints source selected the public URL on the server despite an internal override. |
| `public-config-red.tap` | Permanent configuration assertions failed against the baseline. |
| `baseline-runtime-mismatch-red.json` | Prior native production image started despite conflicting runtime and baked public API values. |
| `baseline-browser-red.log`, `baseline-browser-targets.json` | Real fresh Chromium API requests targeted baked `http://127.0.0.1:8000`, although the runtime public override was `http://127.0.0.1:65395`. |
| `baseline-real-SSR-red.log` | Actual `/counties/516` returned its bounded fallback shell, but the separately instrumented internal fixture received no SSR API request. |

The baseline browser intercepted API requests with an inert 503 response so that the incorrect localhost destination could not contact another local application. This checks the real compiled request target without claiming real backend data availability.

## Verification after the fix

### Focused source and wiring tests

```sh
cd frontend
node --test scripts/container-config.test.cjs scripts/api-base.test.cjs
```

24/24 passed after the final workflow input-scoping change (`configuration-tests-green.tap`). Tests cover missing/invalid public configuration, all three runtime public mismatches, marker validation, optional internal validation, actual Axios/endpoints selector behavior, and workflow input/preflight/build wiring. The selector tests transpile the actual source with Axios/Supabase side effects stubbed; they are source execution evidence, not a substitute for packaged runtime checks.

### Actual Docker builds and runtime

All builds used only these inert public arguments: API `http://127.0.0.1:65395`, Supabase URL `http://127.0.0.1:54321`, and anonymous key `local-container-verification-placeholder`. No `.env` or real credentials were loaded. The runtime-only internal override was `http://backend516:8000`; it was not a build argument.

| Dockerfile | Platform | Local image | Build seconds | Runtime |
| --- | --- | --- | ---: | --- |
| `frontend/Dockerfile` | linux/arm64 | `audit-frontend516-config-default-arm64` | 65.72 | Passed |
| `frontend/Dockerfile` | linux/amd64 | `audit-frontend516-config-default-amd64` | 120.27 | Passed |
| `frontend/Dockerfile.prod` | linux/arm64 | `audit-frontend516-config-prod-arm64` | 60.97 | Passed |
| `frontend/Dockerfile.prod` | linux/amd64 | `audit-frontend516-config-prod-amd64` | 114.88 | Passed |

The `*-build.json` receipts record exact subprocess argument arrays, exit status, hashes of the manifest/lockfile/peer policy/Dockerfile, image inspection metadata, and timings. The `*-build.log` files record actual Docker output. Equivalent build command, repeated with both Dockerfiles and platforms:

```sh
docker buildx build --platform linux/arm64 --load \
  --file frontend/Dockerfile.prod --tag audit-frontend516-config-prod-arm64 \
  --build-arg NEXT_PUBLIC_API_URL=http://127.0.0.1:65395 \
  --build-arg NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 \
  --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY=local-container-verification-placeholder \
  frontend
```

Each actual packaged image ran as UID 1000, served `/api/health` with HTTP 200, and served `/counties/516?fy=runtime-config` with HTTP 200. For every image, the independently recorded internal fixture saw the real server request `/api/v1/counties/516/comprehensive?fiscal_year=runtime-config`. This proves the packaged SSR transport uses runtime container DNS.

For every image, the built production rewrite still contained the baked public URL and an actual `/api/v1/config-probe` request returned HTTP 200 from the separate public fixture. Because the inert test public URL is host loopback, a temporary container-local HTTP relay forwarded that loopback port to the public fixture. The relay was a test fixture; it did not change application code or Next's built route manifest.

All 113 client JavaScript files per image were inspected: the public build URL was present and the actual internal runtime URL value was absent. Native Chromium separately exercised the built application with a fresh context. It sent genuine uncached Axios requests for fiscal years, comprehensive county data, and accountability to `http://127.0.0.1:65395`, matching the public build value (`candidate-browser-targets.json`, `candidate-browser.log`). This is request-observation evidence, not only a chunk-string assertion.

`runtime-results.json` and individual `*-runtime.json`/`*-server.log` receipts contain these observations. The private and public fixture APIs intentionally returned 503 for ordinary data endpoints, with a successful dedicated transport probe. These checks establish selected addresses and successful fixture connectivity; they do not establish financial payload accuracy or successful-data hydration semantics.

### Executed rejection paths

`negative-results.json` and `build-negative-*.log` record actual Docker builder execution for both Dockerfiles with missing API argument and invalid `ftp://` API argument. All four builds exited 1 at the configuration guard before Next's optimized build began.

The native production image's actual default command also exited 1 before Next startup for an explicitly blank public API override and for malformed `INTERNAL_API_URL`. Neither error echoed the supplied URL. The coordinator separately executed the actual default entrypoint with conflicting public API values and observed the same early rejection. Focused Node tests exercise malformed and mismatched cases for all three public values.

## Boundaries

An independent reviewer executed 346 guard challenges. Invalid effective public
values, missing/malformed JSON markers, wrong versions/types, runtime mismatches
and invalid internal addresses were rejected. Four unusual direct-call
representations (named array properties and inherited properties) contained all
the same valid required values and were accepted. The coordinator reproduced
these and confirmed changed-URL controls were rejected; those representations
cannot survive marker JSON serialization and do not demonstrate an invalid
configuration accepted by the startup guard. Raw results and that disposition
remain preserved under `map-focus/independent-config/` beside `config/` in the
review evidence root.

Coordinator verification separately passes 33 actual-helper transport checks,
the full isolated frontend suite (126 suites, 1,605 tests and one existing
skip), the final 24 configuration tests, TypeScript, lint and dependency tooling.
The final API helper's affected Axios, endpoint, server retry and county SSR
suites pass 41 tests. Coordinator logs are in the evidence directory's parent.

Linux arm64 ran natively; Linux amd64 built and ran through Docker Desktop emulation on the arm64 Mac. Browser request observation used the native image; the other three images received actual server/rewrite/client-output probes. Dedicated local fixture containers and an isolated Docker network were used, with ephemeral host ports. No full Compose stack, ETL, cloud provider, production traffic, real auth session, image push or GitHub Actions run was used. Existing packaging/image-cache receipts remain in the earlier container-build report; this review verification focuses on the changed configuration paths.
