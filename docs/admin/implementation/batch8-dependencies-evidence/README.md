# Batch 8 tooling dependency evidence

This compact packet binds the four product files, complete 313-record lock review, actual baseline/final audit JSON, commands/observed exits, selected raw outputs and three independent reviews. Large model caches, coverage/build outputs and complete candidate installations remain at the `raw_root` in source-identities.json. The primary financial checkout was not edited. There is no hosted CI result: Actions remains disabled.

`command-receipts.json` preserves failing experiments alongside final observations. Its legacy `source` field means the frozen baseline; consult source-identities.json for final tested file hashes. An audit exit 1 reports remaining vulnerabilities. The original malformed-report gate returning 0 was a demonstrated defect, not a successful security check. The bounded package exception probe is not proof of a crash through the public Jest CLI. Uninterpretable supervising timeouts are not Jest passes.

Reproduce the product gates from an owned full frontend installation with the tested Node 22 runtime, using an owned npm cache: `npm ci --include=optional`; `npm ls --all --json`; `npm audit --json`; `npm audit --omit=dev --json`; `npm run test:dependency-boundaries`; `npm test -- --runInBand`; `npm run verify:dependency-tooling`; `npm run lint`; `node node_modules/typescript/bin/tsc --noEmit`; `npm run build`. Lint/build need explicit inert NEXT_PUBLIC_API_URL/NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:58175 and NEXT_PUBLIC_SUPABASE_ANON_KEY=batch8-inert-public-key. Use ONNXRUNTIME_NODE_INSTALL=skip for the retained CPU-only installation policy. Full audit currently exits 1 by design, so inspect its JSON rather than interpreting that exit as a test failure.

Native: `npm run verify:native` uses the accepted script, a separately owned cache of public Xenova/all-MiniLM-L6-v2 revision 751bff37182d3f1213fa05d7196b954e230abad9 and an explicit inert environment (exact command/env files retained in raw). The unchanged real build-embeddings.mjs was executed in owned macOS/Linux fixture roots with pinned local model bytes, producing 264x384 normalized finite vectors. Production embeddings were not rewritten.

Runtime: build first, finish full native checks, then in an owned copy `npm prune --omit=dev --include=optional`; `node scripts/verify-runtime-dependencies.cjs`; `npm audit --omit=dev --json`. Never prune the full installation or follow a shared node_modules link during a live verification. The existing boundary command retains the #577 real linked-source-preservation regression and image decode, plus invalid transport controls. Browser verification uses the existing exact allowlist harness; actual fallback/WASM outputs are retained.

The portable watcher harness at raw/review-adversarial/probe-parcel-watch-portable.cjs executes real --watchAll --watchman=false, edits an inert test, observes pass then failure, traces the platform native binding and stops its group. Its hash is 2adebfcb98a45a57cf129d6a0ee09be32a655ff25701a37af9019967d206105f. Both platform receipts are committed. Linux was executed via owned Docker amd64 emulation, not a native host or deployed service. No Windows/musl/GPU/macOS-x64/arm-Linux/watchman-backed claim follows.

See ../BATCH_8_DEPENDENCIES_HANDOFF.md for the decision and residual chains. #494 remains open. Review reports state their exact inspected snapshots; final delivery identity is recorded after the normal push.

Selected raw outputs use [lossless JSON envelopes](LOG_FORMAT.md); decoding `text` as UTF-8 reproduces the exact original SHA256, including carriage returns and spaces. Full publisher notes remain in raw evidence; the committed release note is a compact review summary.

## Coordinator filename corrections — 2026-10-09

The historical review snapshots keep their original text and inspected hashes. Three filename references in those snapshots use the original raw names rather than the committed packet names. Use these exact committed files:

| Historical reference | Committed evidence |
| --- | --- |
| `final-evidence-validation.json` in `spec-final-followup.md` | [spec-final-evidence-validation.json](spec-final-evidence-validation.json) |
| `format-checks.json` in `standards-format-followup.md` | [standards-format-checks.json](standards-format-checks.json) |
| `documentation-checks.json` in `standards-documentation-followup.md` | [standards-documentation-checks.json](standards-documentation-checks.json) |

The coordinator also narrows the manifest and lock root's Node contract to `^20.9.0 || ^22.0.0 || >=24.0.0`, consistent with the installed Jest tooling. Node 22 is locally exercised and already configured in workflow definitions; Actions remains disabled. Semantic-version validation now rejects nonempty but malformed versions in measured npm graph rows. The author reports above describe the earlier inspected snapshot; current coordinator receipts supersede their runtime-range and graph-validation claims.
