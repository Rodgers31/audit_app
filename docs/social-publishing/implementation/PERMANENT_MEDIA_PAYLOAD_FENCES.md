# Permanent media payload fences — Batch15 candidate

This candidate implements default-off payload retirement under #490/#488/#476. It does not assert deployment, live R2 acceptance, legal approval, write quiescence, full privacy-request completion, or legacy-grant revocation.

## Storage and admission contract

R2 presigned PUT expiry, quiet HEAD and matching listings cannot establish that an admitted write stopped. The generic `UnsupportedWriteQuiescenceVerifier` remains unsupported. Existing uploads whose `write_protocol` is NULL, including historical retained pairs, remain refused by payload retirement. Never backfill this field from time, listings, a positive HEAD or operator assertion.

With `SOCIAL_MEDIA_FENCED_RETIREMENT_ENABLED=false` (default), current intake behavior is retained. Explicit enablement records `conditional_create_v1` when allocating **new** uploads. Browser grants and finalization must always use `If-None-Match:*`; runtime construction checks SDK support for both conditional-create and conditional-replace parameters without network I/O. Lifetime admission is serialized by the global budget row and capped at 1,000 assets/uploader and 10,000 total by default, with strict configurable in-process ceilings. Admissions are never refunded: historical asset/upload records and up to two permanent marker objects remain bounded even after payload bytes shrink.

Only an independently approved policy whose exact digest is separately allowlisted in `SOCIAL_MEDIA_RETIREMENT_POLICY_HASHES` may authorize storage effects. That reviewed policy must establish: exact private unversioned R2 bucket/provider; exclusive application writers using this conditional protocol; no bucket lifecycle, out-of-band DELETE, overwrite, replication/versioning or alternate credentials that can remove/replace fence keys; retention of minimal markers and audit/checksum/provenance records; and restoration/custody of both external signed intent and database effect history. Configuring a digest is not evidence these external conditions were verified. No bucket settings, grants or credentials are changed by this candidate.

Eligible payloads are atomically replaced with a permanent one-byte object via `If-Match:<observed ETag>`. A missing key is occupied using `If-None-Match:*`. If a late admitted create wins first, a bounded subsequent CAS can replace it. Once the marker exists, conditional creates cannot replace it. There is no DELETE/absence window. All newly admitted browser/server writes may remain unknown; this implementation never declares they drained. Cloudflare documents the conditional PUT headers at https://developers.cloudflare.com/r2/api/s3/extensions/ . This is a local implementation against that documented contract; live provider semantics remain a separate gate.

Each invocation uses at most three bounded CAS/create iterations per key, single-attempt SDK writes, exact marker identity/metadata/bytes and strict successful HEAD/GET/PUT acknowledgements. Versioned responses, malformed acknowledgements, altered bytes, another operation's marker and ambiguous responses retain uncertainty. No raw key enters the admin/operator command: allocated `quarantine/{actor}/{asset}/source` and `ready/{asset}/original` identities are rechecked under locks.

## Durable authority, concurrency and accounting

`social_media_deletions` records immutable command, authority/receipt, scope, policy and execution binding before external effects. Admission and completion force deferred constraints and compare actual persisted asset/upload/budgets/ledger/audit rows with intended values. Suppressed/altered writes cannot authorize storage or return completed deletion. Unknown database commit outcomes propagate; no rollback promise or completed receipt is fabricated.

The common lock order is global budget, uploader budget, asset, upload, deletion ledger. Original retirement takes the same asset row lock used by domain revision insertion, checks **every historical revision reference**, and archives before I/O so later domain references are rejected. Any historical reference blocks original retirement. Quarantine-only retirement keeps a ready original available, including its checksum/provenance and publication references. No force-clear/delete-history path is added.

Two-copy reservation is held until every selected marker is positively verified and the exact owned completion transaction commits. A lost response leaves all previous capacity held; an explicit retry uses the same operation/marker and verifies it. Completed replay does no storage writes and credits no bytes twice. One byte remains charged per fenced copy. Retained fence text is immutable history; its constraint now permits the recorded fenced-copy count to replace a payload charge with a one-byte marker charge. `reservation_released`/write settlement are never invented. Lifetime admission is still consumed.

## API, operator and privacy composition

Authenticated admin media routes expose:

- `GET /maintenance`: bounded database-only inventory, raw unknown-write counts, completed/uncertain retirement counts, marker bytes and lifetime admissions. This never authorizes deletion or proves quiescence.
- `GET /assets/{id}/retirement-scope`: bounded hash of the exact upload/object/version/epoch/retention identity, for independent approval.
- `POST /assets/{id}/retire`: strict `PrivacyMediaDeletionCommand` containing original operation/authority/receipt/asset UUIDs, mode/purpose, plan/policy and expected scope hashes. A browser cannot supply an approval Boolean or raw storage key. Disabled/blocked/uncertain are explicit results.

`python -m social.media.maintenance --database-url <explicit DSN> --retire-command <original.json>` reads at most 4 KiB, validates before DB I/O, and performs one explicit command. Non-complete retirement exits nonzero. Report-only remains the runner default. The command file is metadata, not authority. A bare production CLI runtime installs no trusted authority and remains blocked; use the composed operator runtime or authenticated media API. No scheduler or hosted resource is introduced.

`PrivacyWorkflowMediaAdapter(factory, exact_app_media_runtime, signed_ledger)` implements the privacy lane's `inspect_scope`, `execute`, and **database-only** `reconcile`. Proposal must freeze `media_assets:[{id,scope_hash}]`. The bridge verifies canonical immutable `PrivacyPlan`, independent approved `PrivacyDecision`, executing `PrivacyExecution`, exact receipt/asset/hash attribution and matching signed ledger intent, plus the separately allowlisted storage policy. The parent privacy execution UUID maps deterministically to an internal per-asset UUID5, avoiding multi-asset operation collisions. It preserves the parent identity in privacy results.

The privacy route composition owns `app.state.social_privacy_media_port`; media routes borrow its authority only when it is the concrete adapter for the exact same app-owned runtime. Privacy owns keys, signed intent custody, policy/independent approval and request completion. Media owns storage effects and its effect ledger. A complete media result covers allocated payloads only: marker bytes, audit/delivery/ownership/provenance, backups, provider/CDN/recipient copies remain outside its coverage.

Privacy never repeats writes during reconciliation. If a marker response is lost, an operator may explicitly retry the **original internal media command** through the media entry point, then privacy reconciliation observes the durable completed receipt. With no completed media receipt, read-only reconciliation stays unknown. Preserve the original command and signed intent; never regenerate identities or silently rerun privacy execution.

## Migration and rollback

Candidate revision `a701b15a0001` descends accepted `a545b14a0001`. Coordinator must serialize it after recovery `a700b15a0001`, review exact resulting diff and replay the chain before integration. Do not rewrite any applied revision or privileged role grants. The new ledger enables RLS and revokes PUBLIC/anon/authenticated access; no browser grant is added. Dedicated current-ORM migration fixtures advance to this additive schema; historical DDL tests remain historical.

Downgrade takes bounded exclusive locks and refuses any recorded protocol or deletion history. Rollback means disabling flags and retaining additive schema, immutable ledger, every marker and all unresolved capacity. **Never delete a permanent fence key**, including during cleanup, recovery, rollback or bucket lifecycle maintenance. Legacy cleanup excludes recorded protocol rows and retains its existing trusted-quiescence prerequisites.

After a backup restore keep uploads, retirement and publishing OFF. Reconcile signed external deletion intent and media effect ledger, protocol/admission records and permanent marker identities. An earlier DB snapshot cannot authorize replacing unknown objects or releasing missing reservations. Recovery lane owns broader restoration acceptance; absence of a ledger entry is not proof no storage effect occurred.

## Evidence and remaining gates

See checkout `HANDOFF.md` and shared `FULL_PLAN_COMPLETION_B15/lane/media-status.md` for exact source identity, commands, retained red/green review records and cleanup. New full-chain tests execute actual PostgreSQL migrations, lost-response/concurrent retry/reference fencing, raw SQL/history/downgrade refusal and hostile/deferred trigger effects. Controlled storage tests execute the real R2 port; SQL-backed adapter fixtures are distinct from actual predecessor signed-ledger/workflow integration.

Remaining acceptance includes actual private R2/CORS/SDK/host receipts; approved policy and bucket writer/lifecycle custody; effective production roles/migration; independent external ledger/backup restoration; live retention measurements/egress; and separately authorized enablement. Historical protocol-unknown uploads require genuine upstream fencing/revocation evidence or continued permanent full reservation; this candidate offers no manufactured proof or forced reclassification. Uploads and publishing remain OFF throughout this session.
