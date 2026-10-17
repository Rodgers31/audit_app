# Batch15 recovery/privacy handoff

## Candidate identity and disposition

- Worktree: `/Users/roger/.codex/worktrees/b15-recovery-privacy/audit_app`
- Branch: `codex/b15-recovery-privacy`
- Accepted base: `06896185005d822c4b29888138b984510dd1fdbd`
- Frozen implementation/test head: `3f2bc34372a27cce7458eb0218e9afb0d001a004`
- Draft PR: https://github.com/Rodgers31/audit_app/pull/705
- Documentation-only delivery commit follows that implementation. Its exact head, current remote review snapshot and final evidence index are recorded in the shared lane status; `git rev-parse HEAD` resolves the checkout delivery commit without a self-referential document hash.
- CODE IMPLEMENTED: bounded selected-schema recovery, retained-envelope rotation, independent privacy authority/execution/reconciliation, external-ledger restore suppression and authenticated admin UI.
- TESTED: owned local PostgreSQL/SQLite, synthetic cryptographic backups, controlled media SDK, Chrome desktop fixture. Details below.
- DEPLOYED: no. LIVE ACCEPTED: no. EXTERNALLY BLOCKED: off-host custody, legal/provider/retention and production integration gates below. The full original recovery/privacy operational lane remains open.

Primary dirty checkout and peer worktrees were not edited. Existing Python and frontend dependency trees were reused read-only; no dependencies, lockfiles or paid resources were added. Features default OFF. Global/account publishing and media uploads were not enabled.

## Implemented behavior

`social.recovery_operator` provides explicit `export`, `verify`, `rotate` and `reapply-ledger` operations. It accepts only a named PostgreSQL URL environment variable, does not discover credentials or read dotenv, creates exclusive private output paths, bounds input/output/SQL/child lifetime and returns sanitized refusals. Export launches real pg_dump against the same exported repeatable-read snapshot used by two independent DB connections, inventories all physical tables in the selected schema (including empty/zero-column relations and selected-schema partition leaves), reconciles counts and full-row digests, and signs the dump commitment plus schema inventory. Inventory covers columns/defaults, constraints/indexes/triggers/RLS, functions/views/sequences/enums. Arbitrary definitions stay exact; only the observed equivalent unbounded-varchar membership CHECK deparser rewrite is normalized.

Verification uses a separately supplied trusted Ed25519 public key. It needs no source database, refuses malformed signed identities, and conservatively refuses the same database name/OID pair across endpoint aliases. Independently supplied envelope/digest backup bytes and complete manifest-bound subject proofs enable the separate cryptographic-continuity verdict. Missing optional crypto inputs never become a crypto pass. Coverage is the bounded selected schema, not an entire cluster, all external schemas, role grants or off-host custody. Low-level `capture_database` accepts a supplied digest and explicitly does not certify extraction binding; the actual exporter does.

Backup writes reopen and compare persisted bytes before acknowledgement. Rotation requires paused publication, a new active label and retained decryptability; it reencrypts all retained credentials/pending flows in one transaction, preserves logical generations/owners, refuses active work and verifies freshly persisted ciphertext/version/decryption before success. Immutable privacy confirmation envelopes and historical backups still require old keys. Retirement is never authorized.

Privacy plans freeze mapped callback scope, operator-installed policy hash, evidence and exact credential generations/flow identity+content hashes/media scope hashes. Receipt identity alone is insufficient authority. An eligible configured human different from the proposer approves the immutable plan. Execution rechecks actor/policy/version/current owners under locks; durable signed external intent is fsynced/read back before effects. Credential tombstones and pending-flow clearing preserve immutable provenance, receipts, ownership, delivery and financial history. Sticky owners and newer generations refuse erasure. Persisted readback catches triggers retaining old bytes and stale Sessions cannot overwrite newer generations.

Unknown outcomes remain durable and restart-safe. Privacy reconciliation reads the existing intent and media observation port without resending media effects. Scope completion deliberately leaves the overall request pending retention/provider/backup review. Restoring an earlier DB requires separately retained signed intents: validation is read-only by default; explicit apply suppresses eligible old generations in one paused transaction and appends audit history. Newer generations and malformed batches refuse; media still requires explicit reconciliation. Restored publication remains unauthorized.

Admin routes under `/api/v1/admin/social/privacy` use existing admin authentication, no-store boundary, bounded pagination, strict commands and idempotent plan identity. `/admin/social/privacy` shows exact scope/hashes, independent approval/rejection reasons and explicit execution/reconciliation acknowledgement. It uses current social styles and distinguishes completed scope from an unresolved overall request.

## Operator entry and configuration

Run from `backend` with the existing Python environment: `python -m social.recovery_operator --help`. Every operation requires `--database-url-env NAME`; select the owned target explicitly. Never point tests at production. Key files must be private regular files; trusted witness keys, encryption/digest backups and subject proofs must come from independently retained custody. No custody key is generated by this implementation.

- Export requires `--backup`, `--manifest`, `--signing-key` and an absolute `--pg-dump`; optional `--current-keyring` plus `--digest-backup` bind those exact backup bytes in the manifest.
- Restore the dump into an explicitly owned distinct DB using the operator's approved PostgreSQL procedure. `verify` requires backup, manifest and `--trusted-public-key`. Complete crypto verification additionally requires `--current-keyring`, `--digest-backup`, `--subject-proofs`; proof snapshot_id is `recovery_snapshot_id(manifest_bytes)`.
- `rotate` requires explicit `--apply`, `--current-keyring`, `--candidate-keyring`, paused publication and no active owners. Keep old key material; success is not retirement authority.
- `reapply-ledger` requires current keyring, trusted public key and one or more `--ledger-entry` files. Without `--apply` it validates only. Apply requires paused publication and does not enable it afterward.

Application defaults are `SOCIAL_PRIVACY_WORKFLOW_ENABLED=false` and `SOCIAL_PRIVACY_EXECUTION_ENABLED=false`. Review enablement requires existing Meta privacy registration, `SOCIAL_PRIVACY_POLICIES` JSON mapping approved policy keys to lowercase SHA256 and `SOCIAL_PRIVACY_APPROVERS` JSON UUID list. Execution additionally requires absolute preprovisioned private `SOCIAL_PRIVACY_LEDGER_DIRECTORY` and canonical URL-safe base64 32-byte `SOCIAL_PRIVACY_LEDGER_SIGNING_KEY`. Invalid configuration fails startup. These are operator qualification inputs, not permission to activate them now. Local fsync proves only local persistence.

## Media dependency and migration integration

Media lane owns all storage effects. The typed port exposes inspect_scope/execute/reconcile; selected media items are exactly `{id,scope_hash}`. A parent execution UUID maps to media's internal `uuid5(execution.id,str(asset_id))`; result reports the parent UUID. Runtime lazily composes the peer `PrivacyWorkflowMediaAdapter` only with privacy execution and media fenced-retirement gates enabled, borrowing the exact app-owned runtime and signed ledger. Media has its own approved policy hashes and default-off gates. The peer module is not present on this isolated branch and is needed for media execution; credential/flow paths do not import it with gates OFF.

After a lost media response, privacy reconcile remains read-only. Only an explicit media-owned retry using the exact original admitted internal command can reconcile storage fences; then privacy reconcile observes completion. Never automatically retry privacy execute or clear owner/history to manufacture completion. Controlled SDK tests demonstrate protocol behavior, not real object-store writer/version/lifecycle custody.

Reserved migration `a700b15a0001` follows `a545b14a0001`; adds plan/decision/execution/event tables, constraints, immutable authority/history and RLS with PUBLIC/browser privileges revoked. No runtime role grants were changed. Populated downgrade refuses; empty downgrade exists. Isolated tests run the full real upgrade chain. Coordinator owns serial predecessor links: recovery → media → generation → platforms → rendering; independently review and replay the combined chain before any release. Multiple candidate heads are not production-ready.

Shared edits: `backend/main.py` calls configure_privacy_workflow immediately after configure_meta_privacy; `backend/social/__init__.py` registers workflow models; `connections/recovery.py` adds persisted backup readback; `SocialWorkspace.tsx` adds the privacy navigation link. No edits to shared api/models/contracts/service, provider adapters, role contract, generated types or dependency manifests.

## Validation and review evidence

Evidence directory: `/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/recovery-privacy-evidence`.

- `backend-normal-final.json` and `backend-optimized-final.json`: 51 passed in each mode, zero skips; exact commands, commit/input hashes, raw log and unique JUnit testcase identities. Python3.13.9; PostgreSQL17.11; pg_dump/pg_restore18.3. Real DB cases use the owned port55392 and full Alembic chain, actual dump/restore, deliberate source DB removal, separate synthetic keyring recovery, complete crypto proofs and signed-ledger replay.
- `compatibility-final.json`: 293 passed, seven explicit prerequisite skips in the historic separate-target PostgreSQL cases. No all-suite or live acceptance claim; overlapping selections are not added into an invented unique total.
- `combined-final-normal.json` / `combined-final-optimized.json`: two passed each with actual privacy authority/FileDeletionLedger and peer media adapter, binding both worktree inventories plus external harness. Normal and lost-response/read-only observation/explicit admitted retry paths use a controlled conditional SDK. Peer changes after these hashes require coordinator replay.
- `frontend-final.json`, `ui-final-jest.json`: five UI cases and scoped lint passed. `ts-final-candidate.log` equals `ts-final-accepted-baseline.log`: sole full-TypeScript failure is inherited `components/map/StyledGeography.tsx:36` CSSProperties incompatibility. Exact base source was extracted and verified. Full application build and hosted checks were not run.
- `chrome-privacy-completed.jpg` and `chrome-privacy-completed-state.txt`: actual Chrome desktop synthetic proposal → independent approval → explicit execution; completed selected credential generation and unresolved overall request visibly verified. Local harness proxies the actual FastAPI router; fixture identities/keys/ledger are disposable. Mobile viewport and live deployment were not validated.
- Independent Spec: `spec-review-final.md` and source-bound directories; final ten normal + ten optimized cases, no remaining confirmed reviewed finding. Independent Standards: `standards-review-final-v2.md` and provenance; final eight normal + eight optimized cases over the final identity guard, no remaining finding. Earlier source-specific reviewed suites (including 64+64 and 53+53 hostile controls plus Jest5) remain historical receipts, not relabeled current runs. Neither reviewer certifies production/off-host custody; parent combined-media receipts support that separate seam.
- Original observed-red backup readback, schema coverage/rotation, stale generation, child cleanup and malformed/aliased identity reproductions and frozen sources remain intact. Setup failures are labeled separately; a Python3.9 setup failure is not a product regression.
- Remote inline comments, review bodies and requested reviewers were checked after draft creation: all empty at that snapshot; REVIEW_REQUIRED remains, no review requested, no hosted check run, parent closing references empty. Final snapshot is in shared status.

Source SHA256 at frozen implementation head:

- `backend/social/recovery_database.py`: `c283ec195cb7cb3a2dbb77b4cca7740a13b9e29e21b8083cfe5f3437daea612b`
- `backend/social/recovery_operator.py`: `9246b9f22a6b0b4f1554cbfea8841c9e0accd7e5d7f2b0e60f2381f187e9a7ef`
- `backend/social/connections/rotation.py`: `86d739f69ce6d83181656f318871ff8b208c087cd940b9a7200b717f4dfc4337`
- `backend/social/privacy/workflow.py`: `9e329deb7a3a989d6ee7157af8b20c3992eb918a9369050160b3e996c5a63a8d`
- `backend/social/privacy/deletion_ledger.py`: `06033e88654c184f7fcb46c88ed5eaed52dae3027c16fd8324ec3f24911326d6`
- `backend/social/privacy/workflow_api.py`: `01b30da24514d6390e88ccf297de84c3e6b09a677cc51663c901fe3fba6b35a9`
- `backend/social/privacy/workflow_startup.py`: `d0465e977119f5bc59e60692257c6ddbd69dafc4994470d35d4cfe82a78761f2`
- `frontend/components/admin/social/PrivacyReview.tsx`: `c92f8b151abf48f4c2b1da04903bde19c92edd7a06786603e7bb92ddb523fae5`
- `frontend/lib/api/socialPrivacy.ts`: `4d863c7236504f988445d83708deb54d311fcc4b5363c6566625ed921e31a459`
- `backend/alembic/versions/a700b15a0001_privacy_authority.py`: `3ef16b1e3378009a7c69bf64474e7bc4b6770d41941485cc0741c2d818968495`

## Remaining original requirements and external gates

The local code increment does not finish the original operational recovery/privacy lane. Coordinator must obtain independently held signer/public-witness, envelope/digest backup and subject-proof custody; perform an actually off-host source-unavailable recovery drill; cover all retained snapshots/WAL/key copies and external schemas; validate intended DB roles/grants/privilege restoration; and replay the exact merged migration/runtime/media composition. Same-host distinct-DB source removal is not off-host custody. Bounds refuse larger inventories instead of silently truncating.

Human legal/editorial policy must decide the approved retention scope, valid approvers, audit/financial provenance and provider/backups obligations. No retention duration or legal approval was invented. Provider copies, immutable confirmation/history, held backups and media writer/versioning/lifecycle contracts remain outside local completion. No full-deletion public status, backup retirement, old-key destruction, publishing/upload activation or production acceptance is authorized. Parent #488/#476/#545 remain open.

## Resource cleanup

Owned `b15-recovery-privacy-pg` container removed. Fixture API PID6672, Next PID96090 and its child7381 exited; loopback ports33502/52043/55392 verified closed. Agent-created Chrome tab760055466 closed. `cleanup-final.json` records verification. Reviewers removed their owned fixture databases; synthetic files/receipts and source worktree remain for review. No peer processes, primary files, production accounts, storage or credentials were changed. No merge/deployment occurred.
