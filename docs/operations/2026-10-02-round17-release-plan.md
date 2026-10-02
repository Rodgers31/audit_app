# Round17 release and recovery operation plan — 2 October 2026

**Preparation only; production execution is not authorized.** This plan resolves
#231/#319's concrete target, coordination and recovery inputs. S07 owns refreshed
correction manifests/SQL; S08 owns OAG adoption; root owns final approval and
external changes. Do not run a broad seed to repair three rows or infer a data
transition from deployment. Actions remains OFF.

## Current targets and evidence

The immutable external index is `ROUND17_SHARED_READONLY_READY.json` in the shared
Round17 evidence bank. Its five captures total **2,051,788 bytes**, below 2 MiB.
Primary database capture SHA256
`8d4adbc94934cb4ef36d68777b568490a640c87f3cf790a861dcb100d280f39a`
ran **18:55:12–18:55:23 UTC**. It contains complete source rows1707/1718/1836/1840/
2383/2541/1715/1823, all47 complete county rows, CPI67/86/87, audits5545/5679/5716,
extractions6023/6158/6196 and audits870–894. Both SQL captures verified READ ONLY,
REPEATABLE READ and rolled back; no application import or warmer ran.

The **18:56:52–18:56:57 UTC** supplement SHA256
`e407db5a9a88972b85814cb903c81e2a1c92d5d9542e6e299b28059b60ca7a06`
contains compact source-FK identities,189 county/period/institution-volume cells
and preservation counts. These are **two distinct transactions**, not one
consistent snapshot or backup. Full dependent audits on shared2541 exceeded the
segment budget (1,569,776 bytes) and were omitted whole; compact identities582
are retained. The primary includes full582 extraction rows; their existence is
not permission to change those unrelated rows. Do not certify unrelated audit
recovery from a projection. Preparation of exact three-row correction may use
complete target images; full recovery needs the separate complete backup.

| Target | Fresh observation and required action |
|---|---|
| Render | `srv-d6hr3t5m5p6s73bomqu0`, live `dep-davu1pgjo6nc73928d00`, commit `fc69f13c04c9cc27fa2e6514b47b6bd569a5b772`; one Starter instance; root/build context backend, backend/Dockerfile, no Docker command or predeploy override. |
| Vercel | `rodgers31s-projects/audit_app`, Ready production deployment `8YH2QXrxV7tyjMAmZJnP5ZREjCd3`, hostname `audit-d1opuegqe-rodgers31s-projects.vercel.app`, same fc69f13 commit. Public target `https://www.auditgava.com`. |
| Database | Supabase project `xznjxwrkbkahwtnbstbj`, PostgreSQL17.6, public Alembic revision `ea1645a4c0b5`; endpoint identity fingerprint is in each capture. No new migration is part of this plan; optional county-debt schema is separately owned. |
| Signing | Names-only Render/Vercel/GitHub observations still lack `REVALIDATE_SECRET`; no linked groups/shared variables. Configuration-name hashes are in PROVIDER_READONLY, not secret-value fingerprints. Dedicated secret equality is unverified. |
| Workers/cache | Public detailed health18:59:14 UTC reports production, namespace fc69f13c04c9, memory fallback/no Redis. One instance + Dockerfile's single Uvicorn command is configuration evidence, not process census. WEB_CONCURRENCY's name does not establish worker count. Actual marker adoption is unverified. |
| Writers | Correct pipeline-health GET19:00:58 UTC reports running web reference refresher; next county reference refresh9October16:51:22 UTC. Dedicated domain health is `not_checked_here`; `etl_jobs=[]` does not prove no provider/db scheduler. SQL observes pg_cron/pg_net workers, without certifying their configured jobs. |
| Quota/backup | Provider UI18:58 UTC:4.12/5GB egress82%,72.1MB database; prior-cycle grace ends8October. Usage may lag1hour. Free Plan does not include project backups. No current full archive+restore receipt was established. |

1840/2383 still have wrong publishers;1840 has no observed source FKs and2383
has loan426. Zero refs is not deletion authority. Nairobi3 retains001 and
Mombasa4 retains047 in both nested FY2024/25 and FY2025/26 cells. CPI67/86
remain143.08 and87 remains142.47 with no extraction. Fresh public CPI200/[]
proves withholding. Population79 remains51,202,827 and is excluded from writes.
Projects47, missing-funds3, audit-summary8, economic-profile47 are presence
counts, not fixture eligibility. All sourced project arrays must survive.

Fresh grouped coverage is FY2020/21:47counties/1498findings with null explicit
volume kind; FY2021/22:onecounty/onepreamble with null kind; FY2023/24:
47executives/1047findings; FY2024/25:47executives/1269 and47assemblies/582.
Missing deferred periods/institution cells are unobserved, never filled from
older receipts or represented as verified zero/complete coverage.

## Writer window and exact approval boundary

Root must name one database operator and one reviewer. Keep Actions OFF and no
native/manual domain writer active. The currently running web refresher means
Actions concurrency alone cannot provide a freeze. Before backup or exact
correction, the approved operational choice is to **suspend this exact Render
service**, with a declared temporary API outage, rather than treating a flag or
maintenance page as proof its processes stopped. Owner must separately inventory
and pause any database/provider/other runner jobs that can write these tables,
then verify no such active transactions remain. Do not indiscriminately terminate
provider sessions. pg_cron/pg_net existence alone does not establish a writer.

`AUTO_SEEDER_ENABLED=false` alone is insufficient: startup unconditionally calls
`initialize_reference_data` (backend/main.py:1703), and separately sets up the
scheduler. Environment changes/redeploys can run that startup path. Suspend/role
quiescence/restore/resume is an owner operation, not an action performed here.
Recheck exact before-images after the freeze. If a concurrent writer or changed
identity/source/metadata is found, stop and regenerate/review affected plans.

Root's final correction authorization must bind: exact reviewed deployment/code
SHA and tool hashes; selected source artifact hashes/editions/pages; fresh plan
and forward/inverse hashes; full backup/restore receipt hashes; exact ID/count
scope; named writer window; rollback owner; public acceptance and outage budget.
No missing hash is replaced by a old packet hash or a simulated post-code image.

## Full consistent acquisition and isolated restore — proposed commands

No full dump was run as discovery. No retained archive bytes were found by the
bounded shared-bank filename search. August30's8.9MB clone/zero-error comment is
inherited evidence, not current backup provenance. Owner must supply an existing
complete retained archive with provenance, or approve exactly one acquisition.

Use the already installed PostgreSQL17 image
`postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`
for both clients and restore. Host clients report18.3 and are not the selected
parity runtime. Owner supplies private0600 libpq service/pgpass files under
`R17_PRIVATE`, outside repository/shared evidence, with service
`round17_prod_readonly` pinned to the authorized TLS database and connect_timeout8.
Do not print their contents or put credentials in argv. Below are **unexecuted**
commands; variables identify owner-provided paths and budget, not credentials.
Run from the assigned checkout; capture exit codes/times and private stderr.
Keep an owner-operated READ ONLY REPEATABLE READ transaction open, obtain
pg_export_snapshot(), and supply its opaque ID as R17_SNAPSHOT_ID. Use that
same snapshot in the separately reviewed complete inventory/content-checksum
export transaction (SET TRANSACTION SNAPSHOT before its first query); keep
the exporter open until both consumers finish. An expired ID stops acquisition.

```sh
# AFTER approved writer freeze and acquisition authorization.
# R17_PRIVATE and R17_BACKUP are approved absolute private directories.
umask 077
docker run --rm --name round17_s6_dump \
  --mount "type=bind,src=$R17_PRIVATE,dst=/run/private,readonly" \
  --mount "type=bind,src=$R17_BACKUP,dst=/backup" \
  -e PGSERVICEFILE=/run/private/pg_service.conf \
  -e PGPASSFILE=/run/private/pgpass \
  -e PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=300000' \
  postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675 \
  pg_dump --dbname=service=round17_prod_readonly --format=custom \
  --snapshot="$R17_SNAPSHOT_ID" --lock-wait-timeout=5s --file=/backup/production.dump
shasum -a 256 "$R17_BACKUP/production.dump"
docker run --rm --network none \
  --mount "type=bind,src=$R17_BACKUP,dst=/backup,readonly" \
  postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675 \
  pg_restore --list /backup/production.dump
```

Select the complete database: no schema/table/data/large-object exclusions.
One nonparallel custom archive has one consistent database snapshot. Check all
warnings, permission errors and archive coverage; zero exit alone is insufficient.
Record extensions, schemas, RLS/privileges, triggers, owner/role requirements and
sequence state. pg_dump omits cluster globals: obtain a separately protected
role/tablespace definition export/provider recovery manifest, without exposing
password hashes. Supabase auth/storage/provider-managed roles/extensions and
actual storage object bytes need explicit restore treatment. Database backups
do not restore object bytes. Any inaccessible objects or unsupported extensions
are **missing recovery input**, not exclusions silently accepted as complete.
[PostgreSQL17 pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html),
[Supabase backup scope](https://supabase.com/docs/guides/platform/backups).

Before approval select the concrete restore image with every required extension
and role definition; the vanilla17 image is available, but its sufficiency has
not been verified. Dump ownership/ACLs must be preserved, or exact differences
reviewed explicitly. Do not use --no-owner/--no-acl to manufacture success.
With compatible image/roles/extensions ready, proposed local target is:

```sh
docker network create --internal round17_s6_restore_net
docker volume create round17_s6_restore_data
docker run -d --name round17_s6_restore --network round17_s6_restore_net \
  -p 127.0.0.1:5576:5432 \
  --mount type=volume,src=round17_s6_restore_data,dst=/var/lib/postgresql/data \
  --mount "type=bind,src=$R17_BACKUP,dst=/backup,readonly" \
  -e POSTGRES_USER=round17_s6 -e POSTGRES_DB=round17_s6_restore \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  postgres@sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675
# Owner-reviewed roles/extensions are provisioned locally first.
docker exec round17_s6_restore pg_restore --exit-on-error --single-transaction \
  --username=round17_s6 --dbname=round17_s6_restore /backup/production.dump
```

The trust setting is disposable loopback/internal-only isolation, never a
production recommendation. Use an encrypted owner-approved volume when the full
backup contains private data. No production service file/DSN is mounted into the
restore. Do not start the application or restored schedulers; block provider
outbound access, including extension background workers. A local result must
record actual endpoint/database/schema/version readback. Network isolation alone
does not certify privilege/RLS parity.

Restore reviewer must verify complete archive/table inventories and deterministic
per-table contents against a same-snapshot manifest (not this projected bank),
large objects, constraints/FKs validated, sequence/identity allocation, triggers,
privileges, accepted population79, all47 identities/full metadata, source1823/
2541 and every shared reference. Demonstrate next allocation in a rollback-only
owned transaction. Run approved exact forward/inverse/drift-refusal controls on
the restored database, compare full state after recovery, and retain measured
restore time. Missing same-snapshot manifest/role/extension input stops proof.
[PostgreSQL17 pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).

Budget proposal for owner decision: one dump connection, no parallel source
reads;300seconds wall limit and256MiB transport allowance for acquisition;
1GiB secured local space and10minutes isolated restore/review window. These are
proposed ceilings, not measured backup size/duration. Before execution the
operator must supply a concrete300second process watchdog and acquisition-client
network-byte counter with a256MiB stop threshold; statement_timeout alone is not
a wall-clock watchdog, and compressed archive size is not transport consumption.
Those controls are an explicit missing execution input, not established here.
The72.1MB database size
does not predict exported bytes. Egress headroom0.88GB is delayed provider usage,
not reserved capacity. Abort/review a ceiling breach; retain incomplete bytes as
failed evidence privately, never label them a backup or repeatedly re-export.

## Serialized correction, recovery and release path

1. S07 supplies source-authority reviewed fresh manifests. Keep1707/1718/1836
   retained unless a separate exact source-proven retirement is approved;
   1718's unresolved CRA source is not repaired by changing a title. Publisher
   correction1840→CBK and2383→Treasury changes only publisher columns and guards
   complete rows/current FK sets. Preserve2541/1823 and their unrelated records.
2. Exact CPI67/86/87 and OAG5545/5679/5716 corrections use existing tools below;
   no generic seed. Prepare from fresh actual state, review digest, dry-run, then
   only final exact-plan approval permits --commit. S07 owns the artifacts and
   source PDFs; this document does not invent their future approved hashes.
3. Correct exactly four nested county code cells, preserving legacy routes
   Nairobi001/Mombasa047 and all financial identities. Recapture **actual**
   post-code metadata. Coordinate any approved S08 OAG catch-up first. Regenerate
   cleanup from actual post-code/post-ingestion state, never projected after-code
   metadata. Cleanup only exact retired fixtures/keys; preserve all sourced
   projects, unknown/newer observations and unrelated metadata.
4. Recovery is operation-specific and reverse dependency order: cleanup to
   approved post-code state, code cells, publisher columns; independently reverse
   OAG/CPI only against their exact guarded after-images. Newly introduced1836
   coverage refuses recovery. Never restore stale whole JSON over newer evidence,
   reset sequences, or globally retire2541/1823. An intent receipt does not prove
   commit; after lost acknowledgment read current full state against before and
   resolved after-images. Mixed/unknown state requires investigation. Full restore
   is disaster recovery with separate owner approval, not default selective undo.

Existing CLI bindings, executed only in a separately approved secure environment:

```sh
PYTHON_DOTENV_DISABLED=1 python scripts/verification/cpi_source_correction.py \
  --manifest docs/operations/2026-09-30-economic-evidence/cpi-correction-proposal.json \
  --january-pdf "$R17_JAN_PDF" --december-pdf "$R17_DEC_PDF" \
  --output "$R17_RELEASE/cpi-plan.json"
PYTHON_DOTENV_DISABLED=1 python scripts/verification/oag_boundary_correction.py \
  --pdf "$R17_OAG_PDF" \
  --manifest backend/tests/fixtures/oag_boundary_reviewed_manifest.json \
  --output "$R17_RELEASE/oag-plan.json"
python tools/prepare_legacy_evidence_cleanup.py \
  "$R17_RELEASE/actual-post-code-cleanup-manifest.json" "$R17_RELEASE/cleanup"
```

The dedicated connection variables are CPI_CORRECTION_DATABASE_URL and
OAG_BOUNDARY_DATABASE_URL, supplied privately with explicit TLS. For reviewed
forward CPI add --plan, --expected-sha256, fresh --output, --commit; CPI inverse
uses --recovery with resolved receipt digest. OAG forward uses --plan,
--expected-plan-sha256; inverse additionally --recover. Preparation/dry-run must
retain rollback. The cleanup renderer has no commit flag: its reviewed SQL ends
ROLLBACK. Any exact terminal-COMMIT variant needs its own file hash/review and
final authorization; do not indiscriminately replace ROLLBACK tokens.

After corrections, owner resumes the exact service and establishes stable
revisions/healthy read-only API. Configure one dedicated server-only signing
secret in GitHub Actions, Render service and Vercel production; owner enters
credential values. Compare equality via HMAC-SHA256 of one fresh release nonce
computed privately at each destination; retain only equality verdict/nonce ID
and destination/revision identifiers, never values or raw value hashes. A later
approved signed endpoint acceptance establishes serving-runtime configuration.

For marker topology, obtain actual process PID/command census and resolved marker
path without dumping environment. Code default is tempfile.gettempdir()/auditgava-cache-generation
(backend/cache/invalidation.py:41); the deployed resolved directory remains an
operator readback input. Capture the signed response generation/PID
and marker inode/mtime/size readback from every actual serving worker/container,
then verify next requests clear old responses. No Redis/single container means
that container's worker files must be shared; scaling across containers requires
separately reviewed topology. Do not claim every worker from repeated hits to
one PID. If only one actual worker exists, document that census instead of
inventing a multiworker proof. No process shell or signed request ran here.

Finally root separately approves the exact source-scoped seed and final Actions
batch after #234/#347 requirements are ready. Warm selected published values,
run accepted seed→**full validation**→signed backend invalidation→exact frontend
acknowledgment using frontend/lib/revalidation/paths.json. Targets are
`https://audit-app-4pwa.onrender.com/api/v1/system/cache/invalidate` and
`https://www.auditgava.com/api/revalidate`; use the existing workflow's exact JSON
checks/order (.github/workflows/seed.yml:976–1028). Capture changed stored/API/
rendered source-bound values at unchanged deployment SHAs **and without restart
between the measured before/after**. Recheck source2541 findings, CPI evidence,
publishers, both legacy county routes, official-code labels, preservation/null/
zero/source identity and full validation warnings. A restart during the earlier
correction outage does not satisfy this later without-deployment transition.

#231 stays open for actual configuration/worker/seed/full-validation/render
acceptance. #319 stays open for authorized stored changes and full recovery/
public/source acceptance; population79 is already satisfied. #137's five-table
retirement is already adopted; optional county debt and historical P1step5 are
separate decisions. #291/#343 require actual final hostedCI only when owner
changes the Actions policy. Optional Codecov failure honestly reported is
acceptable under original scope; a hosted Codecov report is not mandatory.

No new release-path defect was demonstrated, so no application guard or redundant
freshness regression was added. Local test counts remain inherited, explicitly
not rerun here. The exact missing decisions are current full archive/acquisition
approval and secure paths; compatible full restore role/extension manifest;
writer suspension/resumption window; S07/S08 exact source/action hashes;
independent recovery acceptance; signing entry/runtime topology evidence; and
root's final concrete production/Actions approval. This preparation is reviewable
while those execution prerequisites remain pending.
