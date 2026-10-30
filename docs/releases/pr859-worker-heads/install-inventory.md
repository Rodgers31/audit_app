# Native authority view deployment contract — initial inventory

Read-only inventory of accepted `ee23da4404fb8ced0fd4303ba08eb534a212399b`; executable repaired-candidate review is pending. No production connection or mutation was made.

| Registry / entry point | Effect of changing the audit view predicate |
|---|---|
| `backend/social/worker/native_authority_schema.py::_branch`, `definition`, `create_views` | Builds both optional native views, including seven report/financial branches. Both actual PostgreSQL-deparsed definitions change. Preserve five digest-only columns, source locks, security barrier and private ACLs. |
| `backend/social/worker/role_contract.py:36` `NATIVE_VIEW_SHA256` | **Only product registry of the two native view definition pins.** Replace both with fresh actual PostgreSQL `pg_get_viewdef(...,true)` hashes using the verifier's narrow FROM/JOIN schema-prefix handling. Do not accept the old pair in the ordinary runtime verifier. |
| `role_contract.py::_views`, `_verify`, `verify_worker_role`, `install_worker_role` | Strict shape, types, owner, rule, security barrier, ACL and exact definition checks. New source + old installed views must refuse. Ordinary role install must not become a native-view upgrade. |
| `native_authority_schema.py::install_native_authority` | Existing installer verifies first and creates only when absent. It **does not upgrade old installed definitions**. Its idempotent grant restoration must retain this fail-closed behavior. |
| `backend/social/worker/role_admin.py` / `worker/__main__.py` | Explicit named-DSN install/verify entry; worker role verification runs before worker authority acquisition or provider composition. `role_admin --verify` starts no worker. |
| `backend/social/generation/worker_authority.py` | Captures the owner-only snapshot witness; checks the locked digest at delivery. `VERSION=1` is the saved witness format, not a DDL migration number. A changed audit digest can correctly leave older revisions held; do not rewrite their evidence or fingerprints. |
| `REPORT_VIEW_SHA256`, `REPORT_LOCKED_VIEW_HISTORICAL_SHA256`, Alembic head | Separate legacy county report contract / historical schema variant. No change justified by this repair. Native views are optional explicit installed objects, not a new model migration. |
| `docs/social-publishing/implementation/NATIVE_WORKER_AUTHORITY.md`, worker README, new release packet | Existing guidance describes first install, not an upgrade. Add the exact versioned release operation, source/operator pins and fresh installed-view readback. Historical source manifests and production-status receipts stay unchanged. |

Accepted old pins:

- `social_native_source_authority`: `921b807c9637ae9541cf63e74313a4816875afef3de92d42cf6fc25226b09f4a`
- `social_native_source_authority_snapshot`: `f219c56c5f21622cfae0fe875e2020770859c90f2d1978625d21a40781aa6ba6`

The new predicate must use the selected **own-job** audit series head, not only newer-job supersession. Canonical 32-character lowercase-hex scope, JSON-number head type and exact selected receipt membership matter: `native_report_series` was absent from the old digest inputs, so a coercible head mutation must not leave the old witness current. Audit-only digest changes should leave unrelated native domains' digest semantics intact.

## Narrow explicit replacement operation

Use a separately reviewed, hash-pinned release artifact, not an automatic installer expansion. In one bounded owner transaction: establish the off-state precondition; lock both existing view identities before authoritative preflight; accept only exact **old/old** or **new/new** pairs; refuse absent, partial, mixed or unknown definitions. New/new verifies without DDL. Old/old uses `CREATE OR REPLACE VIEW` for both, then proves captured OIDs, owners and ACLs unchanged and runs the full new role contract before commit. Unknown ACL/grant drift must refuse and roll back, never be repaired by revocation. Keep the existing 5-second statement and 2-second lock bounds, explicit search path and no new role/grant/function/migration/activation.

Local executable review should force failure after the first replacement, contention on the second view, unknown/mixed/partial definitions, ACL drift and enabled controls. Each refusal must preserve both original definitions and all ACL/OID/owner state. A metadata-only preflight without a held view lock can race another owner DDL operation; authoritative checks belong after locking.

## Deployment receipt requirements while workers stay off

1. Bind release source hashes for DDL + role contract, the exact release-operator bytes, old/new deparsed hash pairs, actual PostgreSQL version and sanitized target identity. Never record a DSN/password.
2. Retain fresh flags/controls/account holds, absence of worker/consumer and active delivery effects, and the existing repository-variable baseline. No generation, publishing, upload or worker activation belongs to this operation.
3. Before DDL record both view definitions/hashes, OIDs, owners, columns/types, security options, return rules and relation/column ACLs. Check an exact pair; no best-effort reconstruction or partial repair.
4. Record one transaction's zero child exit, unchanged OIDs/owners/ACLs, new definitions/hashes and full contract success. On failure record rollback with both original hashes intact. No success claim from command exit alone.
5. After commit, use a fresh connection for installed hash/metadata readback and the existing actual worker login's `--verify` contract check; this starts no worker. Keep all operational holds and data totals unchanged. If replacement is intentionally deferred, deployment must explicitly retain a pending-install hold and must not claim the new SQL contract is installed.

The production receipt and execution are coordinator-owned. This inventory authorizes no production write and gives no production acceptance verdict.

## Final reviewed pins / executable result

Final app candidate1 mapping `d6a204b8f7982d91756c7624afcfee99daf317f1c438e79882d55fd29901d1dd` uses native locked hash `95c130e2106639dcaa3519951bfa9baa49b52c7fdd677b0dbfe1f0e744b3975a` and snapshot hash `7549c1de87fb44bf1f00b1a9b0ca39b2859d8b1e9a3d898f9203ab4a496faf1e`. Final standalone operator `e243b2b358a95fb232c0e612e2aba5191a67459a2af47aa47caaac118c0435f5` supplies fixed forward and reverse wrappers. Committed rollback requires the actual old runtime contract; wrong-runtime directions refuse. `REPORT.md`/`RECEIPT.json` carry final executed scope; historical initial inventory and old pins above remain provenance.

Final operator2 supersedes the earlier standalone artifact: SHA256 `4c401a7d403ce4ebaccd6a85ad5d8990b45cafbb100d11f5fe0a278511916253`. It additionally requires explicit `AUTO_SEEDER_ENABLED=false`; absence is unsafe because the production app defaults it on. The actual earlier-artifact desired-red and final 55-case/rollback receipts are retained. App/SQL/view pins remain unchanged.
