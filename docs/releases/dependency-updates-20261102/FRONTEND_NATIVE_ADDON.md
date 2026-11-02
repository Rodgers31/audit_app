# Final frontend dependency qualification

PR #891 combines four overlapping proposals and captured native weekly group #889 (`6f848539ad1e718648ef8320936f83c2351ebba0`). Both final dependency files exactly match the native head. Against reviewed main, the lock changes 155 entries: 95 existing versions, 34 additions and 26 removals. The original 87 version intents remain represented: 86 exact, with Solid advancing 1.9.17→1.9.18. Two additional manifest ranges cover Node types and Lucide. These are lock-entry counts, not unique packages.

The SSR migration fix retains SDK cache headers/cookie state through repeated writes and both authorization redirects. Its runtime and legacy-cookie regression sources remain unchanged. The initial qualification remains historical in FRONTEND.md/FRONTEND_VALIDATION.json; final source hashes and receipt bindings are in FRONTEND_NATIVE_ADDON.json.

## Exact inventory repair

A fresh scripted install genuinely refused official resolve 2.0.0-next.7's changed nested contents. Qualify the exact locked upstream artifacts and update only 24 React-plugin inventory entries: 11 added, two removed and 11 altered, 112→121 nested files. All 25 existing repair operations, other package metadata, executable modes and guard logic remain unchanged. Missing/altered/symlinked/unexpected files still refuse, including production mode. The original inventory fails on the actual final graph and the qualified inventory passes. No guard or audit suppression was added.

## Final graph verification

Fresh scripted installs/full peers pass on macOS ARM64 and Linux x64. Final checks pass: TypeScript, no-cache lint, 217 dependency boundaries, nine runtime controls, 220 Jest suites/2,960 tests with zero skips, 14 real Chromium admin cases, browser WASM/semantic retrieval and actual model/Sharp/ZIP on both architectures. The fresh Linux Next build passes with networking disabled; expected API/DNS fallbacks establish compilation, not live-data availability. The optional budget reader uses three retained owned PostgreSQL HTTP captures, not a new database qualification.

Two fresh independent executable reviews clear this graph: 17 coordinator inventory/tamper controls; 41 SDK controls, eight caller controls/full 54-rule parity and 17 new resolver/TypeScript-ESLint controls from the second reviewer. The upstream integrity/121-file inventory is independently reconciled. Counts overlap broader author suites; historical 87-entry receipts were not relabelled as final 155-entry proof.

Raw npm audit retains five existing low development-only deepmerge/Jest entries; production audit is zero. Installed repair bytes/behavior are verified while the upstream registry alert remains visible. No patched upstream version was available in the captured scope. Private Linux copy/install harness failures remain recorded separately from product behavior.

## Release boundary and rollback

Merge-only maintenance: publishing, uploads, workers and financial generation remain off. No deployment, ingestion-pin advancement, migration, paid check or new resource is included. Native worker launch gates remain separate. Authorized Vercel Git disconnection prevents Git-triggered Vercel builds while preserving the current deployment and manual prebuilt releases.

Revert the complete replacement merge to restore its parent graph and SSR sources together. The final inverse-tree proof is retained with the coordinator's final commit receipt. Close superseded proposals only after acceptance/merge and current-intent reconciliation.
