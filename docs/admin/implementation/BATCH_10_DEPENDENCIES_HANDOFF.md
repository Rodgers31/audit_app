# Batch 10 dependency lane: #494 remains OPEN

No compatible complete remediation was selected. This branch contains the investigation, executable controls and a portable evidence packet. It changes no application source, frontend manifest, lockfile, workflow, production embedding or shared skill. No draft PR is appropriate for this blocked investigation; there is no new dependency fix to review as a product change. No residual-risk exception is assumed.

The accepted application base is `f6c31e271297eece52f34102dc40a1e2ed7069a8`, tree `69ddfad6deb814dd08fdaee2db2d512d73e14c78`. The managed checkout is `/Users/roger/.codex/worktrees/batch10-dependency-remediation/audit_app`, branch `codex/batch10-dependency-remediation`. The dirty primary checkout was read only. The frozen issue and author coordination contract are included in the evidence archive. Prior hosted run 38014890047 belongs to its original commit; this lane ran local checks and did not activate or dispatch Actions.

## Findings and the decision

| Tested path | Actual result | Consequence |
| --- | --- | --- |
| Pinned base, macOS arm64 | Production audit 0; full audit 26 entries: 7 high, 19 moderate, 0 critical | Two advisory roots remain; affected package entries are propagation counts, not separate demonstrated exploits |
| Pinned base, emulated Linux amd64 | Production audit 0; full audit 27 entries: 8 high, 19 moderate, 0 critical | Same roots; extra Tailwind typography propagation accounts for the platform difference |
| Configuration-only Tailwind 4.3.3/PostCSS candidate | Real application CSS compiler exits 1: `Cannot apply unknown utility class btn` | Package/config replacement alone is incompatible |
| Official `@tailwindcss/upgrade@4.3.3 --force` in disposable copy | Changes 112 tracked paths, including 107 templates; removes JS Tailwind config; CSS compiles | Exceeds this lane's package/config ownership and changes navigation/counties paths reserved for #601 |
| Existing unchanged utility strings in actual Chromium | Baseline self-comparison passes; v4 CSS comparison exits 1, radius 2px → 4px, shadow → none | Keeping the old class strings is not compatible. This probe does **not** establish that the fully migrated templates render incorrectly |
| Official migrated candidate full audit | 24 entries: 5 high, 19 moderate; same two roots | Tailwind migration alone cannot satisfy complete remediation |
| Migrated install, fresh `npm ci`, ordinary `npm update`, and separate regenerated lock | Real `npm ls --all --json` exits 1 for optional WASM `@emnapi/core` / `@emnapi/wasi-threads` ranges | None of these tested install paths yielded a valid complete graph; no broad override was used |

The required optional WASM ranges have published versions: core 1.11.1–1.11.3 and wasi-threads 1.2.2–1.2.3. Their availability rules out describing this graph failure as an unavailable publisher release. Further resolver repair was not selected because the migration still changes reserved templates and retains both advisory roots. The official candidate changes 65 lock records while preserving all 173 baseline production records. The regenerated-lock experiment changes 262 records and changes/removes 40 baseline production records; it is also rejected.

At capture time, the npm registry's latest braces is 3.0.3 and latest sprintf-js is 1.1.3. GitHub's primary advisory responses report no patched release for [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and [GHSA-hp3w-g68c-fv3c](https://github.com/advisories/GHSA-hp3w-g68c-fv3c). Latest Next lint metadata still declares fast-glob 3.3.1; latest NYC configuration loader still declares js-yaml 3. Existing chains remain. The [Tailwind migration guide](https://tailwindcss.com/docs/upgrade-guide) explains utility renames and changed defaults; migration needs actual page review, not just a package installation.

These results block the **tested** compatible upgrade paths. They do not prove every possible replacement or future compatibility shim impossible. Coordinator prerequisites are a scoped ownership agreement for the 107-template styling migration, supported replacement/publisher repairs for the remaining Next lint and NYC/Jest chains, and fresh complete platform/native/model/build/browser acceptance. The styling migration by itself is insufficient. An owner risk exception, if separately granted, would have its own scope; none exists here.

## Actual callers and exposure

| Dependency/caller | Exposure exercised |
| --- | --- |
| Tailwind 3.4.19 → fast-glob 3.3.3 → micromatch/braces 3.0.3 | Build-time CSS content scan; four literal repository patterns. Existing bounded-input verifier passes. Deliberately nested pattern through the real declared caller throws RangeError |
| eslint-config-next 15.5.27 → Next lint plugin → fast-glob 3.3.1 → micromatch/braces | Developer/build lint caller; actual lint passes. The same primitive failure is reproduced through this separate declared caller |
| Jest 30.5.2 → babel/NYC config → js-yaml 3 → argparse 1.0.10 → sprintf-js 1.0.3 | Developer test/coverage tooling. The actual primitive `%.101f` throws RangeError through argparse's declared dependency. This is a bounded precision failure control, not a full resource-exhaustion exploit |
| Transformers 4.3.1 / ONNX Node 1.30.0 / AdmZip 0.6.1 / Sharp 0.35.5 | Offline embedding builder, native smoke, installer ZIP and image decoding. No current audit root in these packages. CPU inference runs despite the optional GPU downloader being skipped |
| `data/constitution/semantic-search.ts` | Browser-only dynamic Transformers import, WASM query inference, server guard and keyword fallback; actual built `/learn` preview exercised on both platforms |
| Next production image runtime | Existing runtime dependency controls, real PNG/WebP decoding and tracing/exclusion controls pass |

Repository search found no application request caller accepting arbitrary braces patterns or sprintf format strings. That is a reviewed-scope observation, not a universal safety conclusion. No sensitive/live endpoint was contacted; public model downloads were cached in this lane and then exact pinned bytes were used offline. All application files equal the accepted base. The lock has 901 `node_modules/` records, one local `eslint-rules` record and one root record; all bytes and all 173 non-dev non-root records remain unchanged.

## Executed baseline acceptance evidence

Both platforms: fresh engine-strict install, valid baseline peer/dependency tree, 45 Node boundary tests plus 9 runtime tests, 147 Jest suites / 2,077 passing cases / one existing skip / zero failures, production build, lint and types. Real native checks decode SVG/PNG/WebP, round-trip an actual ZIP, load the quantized pinned model and infer 384 finite values. Separate ONNX CPU Identity graph returns exactly `[3, -4]`; repeat model inference returns identical output on each platform. The unchanged actual embedding builder starts with absent outputs and encodes all 264 articles; the packet validator checks article identity/order, 384 dimensions, exact byte length, all finite values and L2 norms. These are baseline results, not security-remediation results.

The skipped case is `frontend/__tests__/components/BudgetTab.debtAbsence.test.tsx`: “mounted reader consumes captured PostgreSQL HTTP absence and sourced-zero states.” It requires `FINANCIAL_ABSENCE_HTTP_CAPTURE_DIR`, an existing optional PostgreSQL HTTP receipt not supplied in this dependency lane. No new skip was introduced.

Both actual Chromium production previews serve `/learn` and CSS with HTTP 200. Offline/fallback and actual WASM inference preserve sampled semantic rankings (presidential term query → Article 142; health care → Article 43), with no page errors or unexpected network. The preview process groups terminate and their port 13014 listeners are read back absent.

Model `Xenova/all-MiniLM-L6-v2`, revision `751bff37182d3f1213fa05d7196b954e230abad9`, uses quantized ONNX SHA256 `afdb6f1a0e45b715d0bb9b11772f032c399babd23bfc31fed1c170afc848bdb1`. Config/tokenizer digests are retained in the packet and read back unchanged after execution. Original existing-model smoke cosine: macOS 0.9992964762462274; Linux 0.9959702126804159. These platform values are reported separately; production vectors were not regenerated in the checkout.

macOS: Node 22.19.0, npm 11.6.0, Darwin arm64. Linux: Node 22.23.3, npm 10.9.9, x86_64 under Docker Desktop arm64 emulation. Linux image index `node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392`, amd64 manifest `sha256:efd0ab5780c2d9ab1f0f869571a00d5edb17793bff4cce4a2792e3eb0ffc7562`. Both Playwright 1.58.2, Chromium 145.0.7632.6 / revision 1208. Linux source Git fixture tree equals the pinned tree; its synthetic commit is not the accepted application commit.

## Evidence, corrections and limits

Use [the evidence README](batch10-dependencies-evidence/README.md) for portable verification and rerun instructions. The archive retains every captured stdout/stderr/receipt, earlier failures, old generator bytes, all three candidate overlays/deletions, actual CSS and builder outputs, final Jest JSON, and frozen spec. The verifier checks integrity and expected historical exit/stability values. A passing packet verifier certifies retained bytes; it cannot grant issue acceptance.

Historical failures remain visible: wrong upgrader executable (127), bad caller metadata resolution (1), missing synthetic build Supabase settings (1), and fake Supabase credentials incorrectly applied to unit tests (two retry-budget failures on each platform). Existing CI deliberately supplies fake Supabase settings only for build/preview; the final Jest commands remove those settings. An earlier passing Jest child produced an untracked coverage directory, so its source-stability verification failed; coverage is now external. Failed setup does not count as a candidate compatibility failure. The superseding command names are documented in the README.

Recorder versions 1/2 did not inventory disposable candidate bytes. Later candidate CSS/audit/tree records do. Older inventories did not detect new files within a collapsed untracked directory, and generator identity was read at command completion. An actual disposable self-mutating child reproduced that attribution defect; the committed recorder now records the starting generator and inventories additions/deletions. Optimized-Python controls execute these failures. Historical records retain their original limitations and are never relabeled as generated by the repaired recorder.

Initial candidate install/config setup, Linux git/Playwright system package setup and the source archive preparation were observed in this chat but lack complete command-recorder triples. They are setup provenance limitations, not accepted compatibility results. The first registry metadata lookup accidentally used npm's default metadata cache; subsequent installs/lookups use owned cache. No dependency was installed into a shared runtime. Model files are digest-bound but not bundled (public pinned download required for a cold replay). CPU/Linux emulation does not establish GPU or native Linux hardware acceptance. No hosted jobs, production deployment, reconciliation, migration, restart or dispatch activation occurred.

## Ownership and routing

External resources: `/Users/roger/.codex/visualizations/2026/10/10/01a123ab-8b43-7830-9262-8f05ab1b8a60/batch10-dependencies` owns raw logs, npm/model caches, disposable candidates, source archive, builder fixtures and coverage. Only container `batch10-dependencies-linux-494-01a123ab`, ID `f8dbb60d64beda8c9aa0763614947b681195ca2e6fcf9960ef37e1272a56fd9b`, is owned. Port 13014 was free before each preview; 18014 is inert refused loopback, not an API service. No database or named Docker volume/network was created. Worktree/caches/evidence remain available for coordinator review; final container cleanup and review identities are recorded in FINAL_VERIFICATION.md.

Complete issue census: seven pages / 601 issue-or-PR records / 296 actual issues (13 open, 283 closed) at initial capture. Existing #494 covers both residual roots and migration acceptance; #511/#577/#600 cover already resolved installation/native prerequisites. No duplicate issue or PR was created. No issue was changed or closed. #494 and separate production gate #583 remain OPEN. The coordinator owns shared skills, combined acceptance, readiness and eventual issue/merge decisions. Local lessons are recorded in this lane only.
