# Batch15 media retention handoff — 16 October 2026

## Checkout and review identity

- Worktree: `/Users/roger/.codex/worktrees/b15-media/audit_app`
- Branch: `codex/b15-media`
- Accepted base: `06896185005d822c4b29888138b984510dd1fdbd`
- Implementation head: `91f5872e5296ddf4c0b41b624154a9a22bf8099c`. Later delivery commits contain handoff text only; the exact final delivery head is recorded in the shared lane status and PR.
- Attached draft PR: https://github.com/Rodgers31/audit_app/pull/702 . No merge/deployment/activation is authorized here.
- Primary checkout was never edited, reset, stashed or installed into. Cached runtimes were borrowed read-only.

CODE IMPLEMENTED and locally TESTED are distinct from DEPLOYED/LIVE ACCEPTED. No deployed or live acceptance claim is made. New behavior, media uploads and publishing remain OFF.

## Implemented behavior

New uploads can explicitly record a conditional-create-only protocol and obey serialized byte, pending and lifetime admission bounds. A policy-authorized retirement atomically replaces each selected payload with a permanent one-byte conditional marker, including bounded recovery when a late PUT wins first. A marker is never deleted. This prevents recreation under the recorded protocol without falsely claiming requests drained. Legacy protocol-unknown uploads and retained pairs remain refused and charged; time, HEAD/listing and lease expiry never supply missing proof.

The effect ledger binds command/authority/receipt/policy/scope, preserves uncertainty and exact per-asset identity, and cannot be removed or retargeted after completion. Protocol/retained history cannot be deleted to refund admission. Actual stored rows, budgets and audit events are checked before effects and before success, including deferred-trigger effects. Lost responses retain full capacity until explicit same-operation retry; completed replay never credits twice. One byte per fenced copy remains charged, with immutable retained history preserved.

Original retirement shares the domain's asset lock, checks all historical references and archives before external I/O. Referenced originals remain ready/available; quarantine-only retirement is supported. No raw storage key or Boolean approval is accepted. Admin inventory/scope/retirement routes, a bounded regular-file operator command, and the typed privacy bridge are executable. Privacy owns independent approval, signed external intent and keys; its reconciliation stays database-only. Actual peer Workflow + FileDeletionLedger + HTTP execution has been exercised, including response loss, explicit media retry and later scoped privacy reconciliation.

See `docs/social-publishing/implementation/PERMANENT_MEDIA_PAYLOAD_FENCES.md` for policy assumptions, commands, replay, limits and rollback.

## Changes, shared edits and migration

Owned implementation: `backend/social/media/{api,config,deletion,fencing,maintenance,models,operator,privacy_adapter,retention,runtime,service,storage}.py`; new tests `test_media_payload_retirement.py`, `test_media_privacy_adapter.py`, `test_media_retirement_postgres.py`; default-off `.env.example`; implementation note.

Migration: `a701b15a0001_media_payload_retirement.py`, candidate parent `a545b14a0001`. Adds write protocol/fenced-copy accounting and private immutable `social_media_deletions`; retains RLS, revokes PUBLIC/anon/authenticated access and adds no browser grants. Bounded downgrade refuses recorded protocol/effect history. Coordinator must relink after recovery `a700b15a0001`, review and replay combined chain before any landing. Never rewrite applied history. Candidate full chain was actually executed in PostgreSQL.

Shared test fixture edits: `test_admin_social_runtime_postgres.py`, `test_connections_migration_postgres.py`, `test_connections_readiness_roles.py`, `test_privacy_postgres.py`, plus media migration/retained/settlement/operator fixtures. Current-ORM fixtures include the additive migration; historical DDL cases explicitly retain historical schema. Operator report now makes four SELECTs, including compact retirement aggregates. These narrow edits may conflict with privacy/platform integration and must be preserved/serialized. No changes to `main.py`, common social models/contracts/service, package/lock files or production role contracts.

Privacy predecessor composition: `PrivacyWorkflowMediaAdapter(factory, exact_app_media_runtime, signed_ledger)`. Proposal freezes `media_assets:[{id,scope_hash}]` obtained from `inspect_scope`. The predecessor's route dependency stores the concrete adapter in `app.state.social_privacy_media_port`; media API borrows only the exact same app runtime. It verifies canonical Plan/independent approved Decision/current Execution/signed intent plus separate media policy digest allowlisting. Parent execution UUID maps to UUID5 per asset. Preserve `social_media_deletions`, upload protocol/fenced counts, immutable references and signed intent during restoration. Missing restored history never authorizes reclassification/release. No raw delete belongs in privacy.

## Executed verification and source binding

External packet root:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/lane/`

Each accepted receipt has generator hash, complete measured-source inventory, before/after stability, child exits, retained raw output/JUnit where applicable and disk readback. Counts overlap and are not additive.

- `media-evidence/record.py broad`: **863 passed, 34 historical guarded PostgreSQL skips**; `broad-8823c96979034892a61b11a70607f7fc/receipt.json`. All seven new full-chain PostgreSQL cases execute. Broader count includes actual media API/inspection/recovery fixtures.
- `media-evidence/record.py optimized`: **111 passed, zero skips**; `optimized-7d6000c94f9e48fdaebfda7037aa5724/receipt.json`. Actual `python -O` over retirement, privacy bridge, full-chain PostgreSQL, config, CLI/privacy and retained-recovery controls; normal pytest optimization warning disclosed.
- `media-evidence/record_namespace.py`: **112 passed, zero skips**; `namespace-58062724db2043e7ae4cc3e0cfe1ed3b/receipt.json`. Cached Linux Python3.12 / SQLAlchemy2.0.23 and original hardcoded test guards inside an owned container namespace. Local ports62124/62249 are internal only, forwarding to owned PostgreSQL; host DB assignment remains55394. `--confcutdir=backend/tests/social` isolates this focused cohort from absent full-main dependencies; no minimum-runtime full-main startup claim.
- Critical flake8 `--select=E9,F63,F7,F82`, compilation and `git diff --check`: passed. Actual current boto3 PutObject model includes IfMatch. No live storage call.
- Independent Spec: `media-review-spec/report-final-v3.md` and `bound-run-e369509c18ea406695f26f7f9bf55abe/receipt.json`: **63 normal + 63 optimized**, zero skips/source drift; genuine signed-ledger and actual HTTP privacy workflow pass; no open confirmed findings.
- Independent Standards: `media-review-standards/REPORT_FINAL.md`, `FINAL_VALIDATION.json`, `frozen-normal-20261016T200051679594Z/receipt.json`, `frozen-optimized-20261016T200113169422Z/receipt.json`: **206 normal + 206 optimized**, five exact historical maintenance-PG skips separately covered by the namespace cohort; all seven mandatory new full-chain PG cases execute, seven independent child probes pass; no open confirmed findings.

Observed-red evidence remains preserved: altered/suppressed/deferred authority and accounting; retention timestamp mutation; failed GET acknowledgement; malformed wrong-asset completion; FIFO command-file blocking. See Standards original logs/probes and supersession declarations. The final admission-history DELETE regression was observed red before the migration guard; `media-evidence/admission-delete-red.log`, context and exact pre-migration byte artifact/hash are retained. Initial fixture setup, stale-source and recorder expectation failures are diagnostic/historical, never relabeled as accepted.

Core SHA256 at implementation head:

- `deletion.py`: `f2807d94d50260925f269431337451f2a5626f11876485d7b82f717c0609c1d6`
- `fencing.py`: `a97b339087b7d0a771b32232691bfe13e463061082c068995b17a25b147db31d`
- `privacy_adapter.py`: `78db142d29a1f52a4dec23b16c19831407e02d5eb5ff7b6c3046e283007aece8`
- migration: `5c0833e994770fdf40adac3fba92348f03dd9c62b8e89fedc74e5fdffd45cc8d`

Full source hashes are in accepted receipt inventories. All three author receipts were read back against current committed bytes with zero mismatches. Final published replay and exact delivery head/resource cleanup are appended in shared lane status.

## Original requirements and remaining gates

No original requirement is silently dropped. Local implementation covers bounded safe new admission, ambiguous browser/finalizer fencing recovery, accounting, policy/authority ports, maintenance execution, deletion ledger, exact keys and reference concurrency. Remaining original acceptance requirements are:

1. Genuine storage/provider custody and conditional-write/CORS/SDK/host receipts; private unversioned bucket, exclusive conditional writers, no lifecycle/out-of-band marker deletion and least-privilege effective roles. These are policy/external facts, not inferred from configuration.
2. Approved explicit retention/privacy policy, independent approver, signed off-host intent/ledger custody and independent backup restoration. Broader privacy/key/recovery ownership remains with recovery/privacy lane. Marker/history/backups/provider/CDN copies are never represented as fully erased by media results.
3. Historical protocol-unknown grants: no generic R2 revocation or write-quiescence proof exists here. Continue durable uncertainty/full reservation unless genuine upstream proof is separately established. Do not force-fill protocol, force-clear pending capacity or erase retained ownership/history.
4. Coordinator serial migration integration and actual production role/deployment qualification. Candidate chain is not the final ordered multi-lane chain.
5. Separately authorized live retention/storage/egress measurements and enablement. No scheduler, paid resource, provider upload/deletion, Actions, bot-review request, policy override, merge or deploy was performed.

Rollback: disable new flags, retain additive schema/history, preserve every permanent marker and all unresolved reservations. Never DELETE a marker key. Publishing/uploads stay OFF.

## Resources and remote readback

Owned resources: `b15-media-postgres` host55394, `b15-media-forward` internal namespace only; all ephemeral test containers use b15-media names. Final cleanup occurs after final verification and is recorded in lane status, including exact anonymous volume removal and port absence. No peer resources are touched. Managed worktree retained for PR review, not archived.

PR702 initial readback: draft true, exact implementation head, no reviews/inline comments/issue comments/review requests/check rollup, no closing-issue references. Parent operational issues stay open. Every later remote review body and inline surface must be read before claiming review closure; no paid review is requested.
