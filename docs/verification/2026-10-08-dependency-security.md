# Dependency security maintenance — 8 October 2026

Scope: partial remediation of [#494](https://github.com/Rodgers31/audit_app/issues/494), based on main `e9da7c7e7149bddb54eb917cd391f4b67ccd827d`. The remaining upstream advisories keep the issue open. No production deployment, data changes or GitHub Actions runs are part of this verification.

## Changes and rationale

| Package/caller | Before | Selected | Reason |
| --- | --- | --- | --- |
| Transformers | 4.1.0 | 4.3.1 | Supported upstream native dependency refresh; retain existing pipeline/model |
| ONNX Runtime Node | 1.24.3 | 1.30.0 | Transformers' declared dependency, without a native override |
| AdmZip | 0.5.17 | 0.6.1 | Resolves naturally inside ORT's new ^0.6.0 range |
| Transformers / Next Sharp | 0.34.5 / 0.35.4 | 0.35.5 | Patch both image-decoding paths, including the new librsvg advisory |
| Next / eslint-config-next | 15.5.24 | 15.5.27 | Matched framework security patches |
| PostCSS selector parser | 6.0.10 / 6.1.4 | 7.1.6 | Deliberate, tested cross-major override for the three inventoried callers |
| Vercel toolbar | 0.2.2 | Removed | No code/config import or required peer; avoid an unnecessary dependency path |

Keep Jest 29.7.0 and Tailwind 3.4.19. The proposed forced Jest upgrade retains the vulnerable sprintf chain; a Tailwind 4 migration would change the styling contract without patching braces itself.

Transformers 4.3.1 declares Sharp ^0.35.4, so its selected Sharp version requires no native override. Next retains its existing caller-specific Sharp override, updated to 0.35.5. The upstream Transformers combination includes ONNX Web 1.31.0-dev.20260914-8d85527a0; browser compatibility was tested separately. Sharp requires Node >=20.9.0, matching this application's engine.

The uniform selector-parser override is restricted in effect by the current complete caller inventory: Tailwind, postcss-nested and Tailwind typography. Their original ranges require 6.x, so this is a deliberate compatibility exception, not a supported parent-range update. Version 7 changes insertion behavior while iterating selectors; actual complete application CSS and behavior fixtures are unchanged. Review any new parser caller before adding it. Initial scoped overrides retained stale vulnerable nested copies; removing those entries, resolving the lockfile again and using the uniform override eliminated every installed 6.x copy. The verification script checks actual caller resolution.

Natural transitive changes also include HuggingFace tokenizers 0.1.3→0.2.0, jinja 0.5.7→0.5.10, global-agent 3.0.0→4.1.3, matcher 3→4, serialize-error 7→8 and protobuf UTF8 1.1.1→1.1.2. The lockfile retains the full delta. No forced framework/native upgrade or YAML schema override was used.

## Actual callers and boundaries

- `data/constitution/semantic-search.ts` dynamically imports Transformers behind a browser guard. It embeds user queries with Xenova/all-MiniLM-L6-v2, q8, mean pooling and normalization, then ranks the existing 384-dimensional article vectors. Browser inference uses ONNX Web/WASM.
- `scripts/build-embeddings.mjs` is the actual native CPU caller. It is an explicitly run offline builder, outside the normal Next build script. Its model, inputs and generated assets are unchanged.
- Transformers' Node RawImage adapter and Next image optimization resolve Sharp. The text-search path does not decode user images. Next permits localhost and the configured API image host.
- ORT's installer uses AdmZip to look up/extract optional execution-provider archive entries. No application import accepts uploaded ZIPs.
- Next output tracing continues to exclude HuggingFace/ONNX native trees. The fresh Learn server trace contains none. This limits deployed server bundles; it does not remove install-time exposure.
- The removed toolbar has no importer in application source, scripts, Next/Vercel configuration or layouts, and no dependency requires it as a peer. Vercel's hosted preview toolbar is configured independently.

## Verification

All commands ran against isolated checkout/installations with local inert API/auth configuration. Public model files were cached locally; verification made no Supabase database queries.

| Gate | Result |
| --- | --- |
| Fresh macOS npm ci, final lock | Pass |
| Production Next build, including lint/type validation | Pass |
| Full Jest suite | 125 suites; 1,600 tests passed; one existing skip |
| Actual three-caller tooling fixture | Pass: theme, dark/responsive/group/peer/arbitrary selectors, typography, nesting |
| Complete minified app CSS before/after | Byte-identical, 143,142 bytes |
| Native fixed-model inference, ZIP lookup/extraction, SVG/PNG/WebP decode and RawImage | Pass on macOS arm64 and emulated Linux x64 |
| Actual browser WASM semanticSearch, metadata lookup, blank query and SSR guards | Pass |
| Production Next start /learn and actual /_next/image conversion | HTTP 200; image returns WebP |
| Independent adverse-input checks of verifier guards | 13 negatives fail; two positive controls pass |

CSS SHA256: `502d213b6024c30d95c1712a0d6dcfb2f00d521078843e32d532e74684663351`.

Copilot's review summary correctly identified that the tooling verifier initially imported transitive postcss-nested from application scope. It now resolves that dependency through declared Tailwind, including the parser check. The native verifier similarly resolves ORT through declared Transformers. An isolated resolver probe rejecting those undeclared application-scope imports fails both original scripts and passes both corrected scripts, including actual CSS generation and native model/image/ZIP checks. No extra direct dependencies or lockfile changes were needed for this review correction.

macOS used Node 22.19.0. Linux used Node 22.23.3 in node:22-bookworm-slim, image digest `sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392`, under Docker amd64 emulation. Both installations used the repository's existing .npmrc. Linux CPU verification set the upstream-supported `ONNXRUNTIME_NODE_INSTALL=skip` to skip optional unbundled GPU downloads, while retaining bundled CPU binaries. Actual GPU execution/full NuGet CUDA downloads, native Linux hardware, other browser engines and hosted model CDN delivery were not verified.

### Numerical compatibility

The public verification model revision is `751bff37182d3f1213fa05d7196b954e230abad9`. Verification does not rewrite the production embeddings.

The first Linux run failed an overly strict 0.999 comparison with the shipped vector. Same-platform baseline measurement showed the old dependencies already produced article/index cosines of 0.99454–0.99679. Article 142's old/new Linux vectors have cosine 0.9999999999998591 and maximum component delta about 1e-7; the original failure does not identify an upgrade regression.

Other long inputs do change numerically: old/new Linux Article 1 and 174 cosines are about 0.99757 and 0.99719; the public-finance query cosine is 0.99808. All five sampled native queries preserve their top five and expected-article positions. Actual browser before/after comparisons also preserve the five queries' rankings; four queries have score changes below 8e-8, while the public-finance query changes by up to 0.00361. These are compatibility samples, not a proof of identical results for every input.

The persistent native smoke uses a documented 0.99 shipped-index cosine floor, finite normalized Float32Array[1,384] checks, and requires Article 142 to rank first for the presidential-term query. This tests model/index compatibility across the observed platforms; it makes no bit-exact or whole-index guarantee. Quantized CPU kernel/platform variation is a supported hypothesis, not a confirmed explanation of every numerical change.

Independent adverse-input testing stubs inference to exercise the verifier's failure guards. Actual native and browser inference were tested by the separate real-model runs; the guard tests are not additional native inference evidence.

## Audits and remaining work

Exact npm audit JSON snapshots are in [dependency-security-2026-10-08](dependency-security-2026-10-08/). Counts below are affected package entries, including inherited parent entries; they are not independent demonstrated application exploits.

| Audit | Baseline | Final |
| --- | --- | --- |
| Production | 17: 12 high, 5 moderate | 5 high |
| Full | 50: 39 high, 11 moderate | 38: 33 high, 5 moderate |
| Critical | 0 | 0 |

The final production entries all derive from unpatched braces 3.0.3. The full audit additionally retains dev-only sprintf-js 1.0.3. No remaining sharp, AdmZip, Next or selector-parser advisory is reported.

- **braces:** Tailwind/Chokidar, ESLint and Jest consume repository glob/config/source/test inputs. No reviewed application request handler accepts user brace patterns. A bounded 4,000-depth compile probe still reproduces RangeError; the character guard alone is insufficient. Keep build/watch/test pattern inputs authored in the repository, and re-evaluate before any online build/parse feature or untrusted patterns. This is a residual vulnerability with no published patch, not a blanket safety finding.
- **sprintf-js:** the remaining path is Jest instrumentation→load-nyc-config→js-yaml 3→argparse→sprintf. Its former native-install production path is gone. The reviewed loader uses YAML's library API; argparse is imported by the YAML CLI. No application format-string caller was found. A bounded precision probe still reproduces RangeError. No published patch exists.

Neither residual is marked remediated or silently accepted. #494 remains open until supported fixes or an explicit, scoped owner exception satisfy closure.

The baseline and final npm ls checks also report the same pre-existing peer problems: React/ReactDOM 19 versus react-simple-maps' <=18 range, and fdir's optional picomatch peer requiring ^3 || ^4 while resolving 2.3.2. Legacy-peer-deps installation and passing tests do not establish supported peer compatibility. A separately reproduced baseline Docker installation failure and its build prerequisite work are tracked in [#511](https://github.com/Rodgers31/audit_app/issues/511).

## Primary sources

- [Transformers 4.2.0](https://github.com/huggingface/transformers.js/releases/tag/4.2.0), [4.3.0](https://github.com/huggingface/transformers.js/releases/tag/4.3.0), [4.3.1](https://github.com/huggingface/transformers.js/releases/tag/4.3.1)
- [ORT 1.30](https://github.com/microsoft/onnxruntime/releases/tag/v1.30.0), [installer control](https://github.com/microsoft/onnxruntime/blob/v1.30.0/js/node/script/install.js), [quantization/platform limits](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html#when-and-why-do-i-need-to-try-u8u8)
- [Sharp 0.35.5](https://sharp.pixelplumbing.com/changelog/v0.35.5/), [librsvg advisory](https://github.com/advisories/GHSA-wq5f-xc86-pv6w), [AdmZip 0.6.1](https://github.com/cthackers/adm-zip/releases/tag/v0.6.1)
- [Next 15.5.27](https://github.com/vercel/next.js/releases/tag/v15.5.27)
- [Selector-parser release](https://github.com/postcss/postcss-selector-parser/releases/tag/7.1.6), [changelog](https://github.com/postcss/postcss-selector-parser/blob/main/CHANGELOG.md), [advisory](https://github.com/advisories/GHSA-rj75-hqrm-r3gf)
- [Braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), [sprintf advisory](https://github.com/advisories/GHSA-hp3w-g68c-fv3c)
- [Jest 30 migration](https://jestjs.io/docs/upgrading-to-jest30), [Vercel hosted toolbar configuration](https://vercel.com/docs/vercel-toolbar/in-production-and-localhost)

Full native version-note enumeration, caller probes, before/after model vectors, CSS comparison, peer trees, platform logs and independent guard checks are retained in the coordinator's October 8 DEPENDENCY_494_2026-10-08 artifacts. Actions remained disabled throughout.
