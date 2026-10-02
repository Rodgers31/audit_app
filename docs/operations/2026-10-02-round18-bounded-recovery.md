# Round18 bounded local acquisition and recovery controls

This implements a local rehearsal of the missing controls in the
[Round17 operation plan](2026-10-02-round17-release-plan.md). **Production
acquisition and recovery remain pending. A hard 256 MiB transport ceiling is
not established.** No production connection/configuration/seed/cache operation
or application startup is part of this tool.

`tools/bounded_pg_backup.py` uses the already installed pinned PostgreSQL image
and Python standard library. No arguments means usage refusal; its acquisition
entry point accepts only `round18_s1_*` containers exclusively attached to an
owned internal Docker network. It creates its own fresh client namespace,
without inherited libpq configuration, and removes that container and anonymous
volumes afterward. This local synthetic source uses trust inside the internal
network; it is not a production TLS recipe. The production TLS/service-file
requirements in the original plan still apply to a future reviewed transport.

## Executed controls and their limits

The acquisition subprocess runs under GNU `timeout --signal=KILL`, with a
separate host timeout and container removal on failure. Its dump deadline is at
most 300 seconds; archive inspection, setup and cleanup are additional bounded
steps, not part of that dump deadline. The host timeout is dump deadline plus
2 seconds, and Docker control calls have their own deadlines. This is an actual
wall watchdog, unlike statement timeout. It cannot guarantee elapsed time if the
Docker daemon/host is unresponsive; failure to remove a container is an error,
not a successful cleanup receipt.

A watcher reads the fresh client's `eth0` RX+TX counters, sleeping 20 ms between
reads, and kills the dump after observing a byte breach. A final counter read
also refuses publication when a fast dump completed between samples. The counter
covers namespace traffic, including DNS and visible retransmissions; it is not
compressed output size or a provider billing meter. Read/scheduling overhead adds
to the sampling interval. In the final local author run, a 128 KiB abort threshold
was exceeded by **84,516 bytes**; an earlier author run overshot by
4,661,194 bytes. These are observed overshoots, **not a maximum**;
there is no proven rate bound. No reserve chosen from this measurement can prove
256 MiB maximum provider consumption. The available images had `timeout` but no
`nft`, `iptables` or `tc`; no proxy, TLS bypass or new image/toolchain was installed.
The local acquisition CLI deliberately has no production service/DSN option.
Root must resolve enforceable transport/accounting semantics before using a
production acquisition path. Lowering the sampled threshold alone does not
resolve this requirement.

The original Round17 command was run against the owned source, retaining its
statement/lock timeouts and changing only connection/path inputs. It remained
alive after 0.35 seconds at a scaled 0.25-second wall requirement, while the new
watchdog refused that same held-lock dump. The original successful compressed
archive was 42,738 bytes but consumed 4,902,498 namespace RX+TX bytes. These
controls demonstrate the original gaps; they do not extrapolate local timing or
transfer rate to Supabase. The fixed 0.25-second stall control returned after
0.556 seconds including setup/counter read/removal. The 300-second maximum is
validated directly; no 300-second live or local stall was run.

All failures refuse to publish the requested archive. Partial bytes and private
stderr are confined to a 0700 temporary directory with 0600 files and deleted
when the local rehearsal ends. No raw stderr is placed in public results; a
synthetic credential-bearing child failure tested this. An acquired archive is
`acquired_unverified`, and `pg_restore --list` success is only
`archive_readable_not_recovery_proof`, both with `backup_verified=false`.
Missing/expired snapshots, child failures/warnings, malformed bounds, public or
symlink archives, bad hashes and missing owners refuse. A half-truncated custom
archive had readable TOC but refused actual restore. Removing only 2,000 trailing
bytes did not reliably make an archive unrestorable; that exploratory assumption
failed and is not treated as a defect or proof.

## Same-snapshot local restore comparison

`inventory_local` imports the exported snapshot before its first query in a
READ ONLY REPEATABLE READ transaction and rolls back. The exporter remains open
until inventory and dump finish. It inventories all non-system schemas/tables,
including synthetic `auth` and `storage`, with SHA256 of sorted, length-prefixed
complete JSON row representations and counts. It includes columns/defaults,
constraints/validation, indexes, RLS policies, triggers, routines, views,
ownership/ACLs, role attributes without password hashes and memberships,
extensions, tablespaces, large-object page bytes/ACLs and sequence state.

This is a small local comparison tool, not a new application provenance system
or a general production-completeness certificate. Its SQL aggregates each table
in memory; large production tables need separately reviewed streamed inventory
and memory/transport bounds. It does not cover every PostgreSQL global/config,
custom type/domain/collation/default-privilege/security-label/publication or
subscription recovery requirement. Raw extension config OIDs may change on
restore and require reviewed logical identity resolution. It excludes system
schemas as normal database dumps do; explicit provider changes to their owners
or privileges remain additional recovery input. Sequences and role/catalog
observations are not all MVCC: the approved freeze must cover these writers too.
A previous arbitrary projected capture cannot replace this manifest.

`restore-local` requires the archive, trusted executable roles SQL and inventory
with their SHA256 values, all private regular files. It starts a fresh owned
`--network none` database with no published port, mounts only those reviewed
inputs, preserves owners/ACLs, and uses `pg_restore --exit-on-error
--single-transaction`. No app, scheduler or inherited production credentials are
mounted or started. The target and anonymous volume are removed even on refusal.
Source-superuser SQL is executable during restore, so archive/roles trust review
remains essential; network isolation is not an archive trust verdict.
[PostgreSQL17 dump scope](https://www.postgresql.org/docs/17/app-pgdump.html),
[restore semantics](https://www.postgresql.org/docs/17/app-pgrestore.html),
[Docker network-none scope](https://docs.docker.com/engine/network/drivers/none/).

The author control restored four complete synthetic tables, preserved distinct
null/zero/boolean JSON, a large object's bytes/owner/ACL, `pgcrypto`, forced RLS,
FK/check constraints and an identity sequence. Only one row was visible to the
read role; invalid amount/FK writes refused. Failed inserts consumed sequence
values, and `nextval` survived rollback. Allocation controls therefore use a
throwaway target that is destroyed, never a supposedly harmless rollback on
production. No production sequence is reset. Catalog shape, duplicate/missing
identities, coverage and sequence-type mutations refuse before an equality
verdict. Two initial fail-open cases and inspector child-cleanup were actually red, fixed
and green; the
independent reviewer replayed them and a separate real archive/restore.

## Operator invocation and exact remaining input

Run from the assigned checkout with the existing interpreter, in an explicit
allowlisted environment. The complete author rehearsal is:

```sh
/usr/bin/env -i PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin \
  PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
  /Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python -I -B \
  backend/tests/test_bounded_pg_backup.py
```

The operator CLI exposes `inspect --archive --expected-sha256`,
`acquire-local --source --network --snapshot --output [--wall-seconds]
[--transport-bytes]`, and `restore-local --archive --expected-sha256 --roles-file
--roles-sha256 --inventory --inventory-sha256`. Paths/hashes are concrete operator
inputs; it never reads the application's environment or connects by default.
A successful restore CLI says `local_inventory_equal_production_unverified`.
This does not approve or certify production recovery.

S02's single fresh read-only receipt, captured 21:37:17–21:37:53 UTC on
2 October 2026, is `ROUND18_SESSION_2_DATABASE_READONLY.json`, SHA256
`4d6da7c1a48a6b1fc95d5a19ebe21698ed6c7ddac3e28af52d27b27fcf4f83f5`.
It reports PostgreSQL17.6, five extensions (`pg_stat_statements`1.11,
`pgcrypto`1.3, `plpgsql`1.0, `supabase_vault`0.3.1, `uuid-ossp`1.1),
30 roles,21 memberships and11 schemas, including managed auth/storage/vault.
It is a projected observation, not the full archive or its same-snapshot manifest.
The pinned vanilla test image actually reports17.11. Its synthetic success does
not establish that it restores this managed database. The existing Supabase image
was checked only for available tools, not restored/configured or certified.

The exact next owner action is to provide an authorized complete archive with
provenance plus same-snapshot full inventory and compatible role/extension/key
recovery inputs, or approve one acquisition after the transport ceiling and
writer window are resolved. Vault encryption/key restoration, inaccessible
provider-managed data, managed role/system-privilege differences and actual
extension/preload compatibility need explicit owner treatment. Stored object
metadata is not storage object bytes; a separately protected object backup is
needed when objects must be recovered.
[Supabase backup scope](https://supabase.com/docs/guides/platform/backups).
No archive filename was found in the bounded assigned repository/shared-bank
search; no whole-machine or live full dump discovery was performed. Root's
concrete final production approval, reviewed outage/writer window and actual
full restore/recovery acceptance remain unchanged requirements of231/319.
