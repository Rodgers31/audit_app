# Full backup and isolated restore prerequisite

Status: **NOT PERFORMED in Session4. Required before any production write.** The banked synthetic PostgreSQL JSON/FK rehearsals are useful transaction controls and cannot certify a complete production restore.

The release/database owner must produce an external full consistent database backup at the approved writer freeze. Record provider/export backup ID, UTC capture time, database identity, actual deployed release/schema revision, PostgreSQL version/extensions, byte size/SHA256, secured storage/access/retention, and the exact restore procedure. Keep credentials and private data outside committed packets. Record encrypted storage transport and a safe separate hash of the immutable backup bytes; do not pretend this packet's JSON rows are a backup.

Restore into an owned, isolated environment with application schedules/lifespans/seeding/warmup disabled and all outbound production/provider destinations removed. Read back actual database/libpq target, schema/search_path and resolved settings before trusting it. No production endpoint/secret may be inherited. Use an approved PostgreSQL version and required extensions/collations compatible with the actual backup; document differences. Network/source effects remain stubbed or blocked. Name the owned resources and cleanup.

The restore receipt must show successful restore completion and independently verify:

1. Complete schema/table inventory and migration revision; columns absent from ORM, indexes, enum/types, extensions, ownership/privileges and enabled triggers/constraints as appropriate to the captured database. Record any unavailable provider-managed objects and their recovery implications; do not silently exclude them.
2. Full data coverage against the backup/export manifest, not selected row counts only. Compare complete deterministic per-table contents/checksums or an independently supported equivalent; verify target full before-images and every dependency/FK catalogue/reference set. Run FK/orphan/integrity checks and verify constraints are validated.
3. Sequences/identities restored consistently, including audited870–894 and future source/extraction allocation. Demonstrate safe next allocation on the isolated copy with an owned control transaction, retain legitimate gaps, and never reset a production sequence merely to reuse IDs.
4. Population79 accepted WorldBank2019 state, all 47 current project arrays and companion metadata, full source 1823/2541 and their references, current2430 loans and2383 loan 426, exact CPI/OAG target images, county names/slugs/route identities and financial controls match the captured state.
5. Existing tool preparation/refusal and authorized synthetic/local correction/recovery against the restored snapshot where owner permits. A fresh mismatch requires source/plan review. Test atomic failure and intervening-evidence refusal; compare complete unchanged state, not just affected counts.
6. Restore startup/read-only application smoke controls using synthetic network destinations; verify predecessor/new county schema compatibility as actually selected. Optional c415a10d2026 adoption requires separate migration/source approval.
7. Restoration duration, rollback/recovery feasibility, independently reviewed receipt/hash and disposal of only owned resources. Leave the recoverable full backup under owner retention.

Retain a separate target/dependency export immediately before each authorized action and actual post-code recapture before cleanup. If earlier CPI/OAG/source writes changed dependencies, the September30 reference bank is superseded and must be refreshed. A backup before earlier corrections remains a disaster-recovery artifact, while action-specific guarded inverses preserve subsequent accepted changes.

The exact owner approval binds backup and restore receipt hashes to each fresh plan. Neither the old318 migration approval,406 merge,review packet hash,nor successful default-ROLLBACK script grants319 data authority. Recovery after a newer unrelated value requires new reviewed current images and approval; never replay a stale whole-document export.
