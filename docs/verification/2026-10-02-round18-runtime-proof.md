# Round18 runtime and correction context — 2 October 2026

The new evidence closes the bounded before-image and selected-instance census
work for S02. It does not apply corrections or complete #231/#319/#273/#379/#234.
The immutable shared index is `ROUND18_SHARED_READONLY_READY.json` in the
coordinator evidence bank. Its three captures total **4,746,773 bytes**, below
8 MiB. The index records actual section columns, row counts, hashes and limits;
no complete-backup or post-correction claim is made.

## Actual serving process and signing targets

Authenticated Render shell output at **21:33:46–21:38:56 UTC** observes service
`srv-d6hr3t5m5p6s73bomqu0`, selected instance `mh6v9`, hostname
`srv-d6hr3t5m5p6s73bomqu0-6b9768d6f9-mh6v9`. The visible census contains Gunicorn
master PID1 and child PID7, plus the shell and observation process. Both app
processes have this allowlisted command:

```text
/usr/local/bin/python3.12 /usr/local/bin/gunicorn main:app
--worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:10000
--access-logfile - --error-logfile - --log-level info
--timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100
```

Both hold listener `socket:[3301512303]`, share mount namespace
`mnt:[4026538505]`, and see `/tmp` device66305/inode33628383. The provider UI
configures one instance and shows no one-off jobs for this service. This is an
observed master/worker census in the selected container, not a count inferred
from `WEB_CONCURRENCY`. Permission-denial counts were not emitted; other
services/environments are outside scope.

The serving process startup environments report production, port10000,
WEB_CONCURRENCY1 and commit `4acd7c0270a78a035557575125d77743ac2dbd5d`; no signing
secret was observed. The deployed invalidation module
hash `a3cb325e1d8c1563fedcb9c9c930711c79e2dcb3b38e014fc6693c4c480b893c`
matches this checkout. The path computed from startup environment and that
module's default is `/tmp/auditgava-cache-generation`; no marker file exists in
either process root. **The loaded in-memory `marker_path()` value and generation
adoption were not read.** No marker or signed invalidation request was written.
The first observation used `tempfile.gettempdir()`, whose resolver can create and
delete an incidental temporary probe file; therefore this session does not claim
zero remote filesystem writes. No application data/configuration/marker change
was performed, and subsequent probes only read `/proc` and file metadata.

The actual command differs from the earlier Dockerfile inference. Current UI
still shows backend root/build context, backend/./Dockerfile, and empty command
and predeploy overrides; the checkout's Dockerfile CMD is Uvicorn port8000.
The observed Gunicorn command matches `backend/Dockerfile.prod:93` with
PORT10000 and is the execution target; the image/entrypoint origin of the
provider-setting difference is unresolved. It is not evidence of a missing
invalidation fix because the deployed relevant module hash matches.

Current provider UI binds Render deployment `dep-db018d5ckfvc73cc7cu0` and Ready
Vercel production `GKDmBZRWi3gtrMnDj2adTBvAmN6G`
(`audit-hrzeh6879-rodgers31s-projects.vercel.app`) to the same merged commit.
Render's full names list and Vercel's All Environments list still lack
REVALIDATE_SECRET; no linked groups/shared variables or listed Render secret
files were observed. The names-only GitHub read at21:39:55UTC also lacks it and
confirms Actions disabled. No secret values were revealed or hashed.

Matching-method feasibility is unchanged: after owner configuration, compute
HMAC-SHA256 of one release nonce privately at each exact runtime/destination;
retain only equality, destination/revision and nonce identity. Missing targets
cannot currently be compared. Signing entry and successful endpoint/path
acknowledgments remain owner operations.

## One coordinated database capture

`ROUND18_SESSION_2_DATABASE_READONLY.json`, SHA256
`4d6da7c1a48a6b1fc95d5a19ebe21698ed6c7ddac3e28af52d27b27fcf4f83f5`,
records **21:37:17–21:37:53 UTC**,35.535seconds and4,730,881bytes. A standalone
NullPool connection verified READ ONLY/REPEATABLE READ and recorded endpoint
identity before fact SELECTs, then rolled back. Explicit TLS, connect8seconds,
statement6seconds, lock1second and a100second process alarm bounded the run.
No app import, bootstrap, warmer, DML, nextval or complete dump ran. The
supplementary offline endpoint check confirms database-name and configured
endpoint fingerprints match the authorized inherited target. PostgreSQL is17.6,
rolepostgres, Alembic `ea1645a4c0b5`.

| Captured section | Actual scope |
| --- | --- |
| Publisher/code/cleanup | Full8 source rows, all47 complete county identities/metadata, audits870–894, population79 and33 relevant FK definitions |
| Shared sources | Full607 dependent audits (582 on2541 plus25 on1836),582 extraction rows,4 indicators,2 GDP rows,1 loan and1 population row; remaining declared source/extraction FK queries captured zero rows |
| CPI | Full67/86/87 and country1; each exact case/type/date/national probe returns its sole original ID; reviewed January/December PDF URL candidates and page2 reuse probes return no rows |
| Protected observations | Full73 WorldBank/annual-tagged economic observations under the recorded metadata predicate and all64 population rows; no general source acceptance or full-economic-table claim |
| OAG boundary | Full5545/5679/5716,6023/6158/6196 and period1; each audit reference/extraction collision and source/extractor/chapter/paragraph probe returns its sole target |
| Allocation |8 sequence catalogues plus actual last_value/is_called; no allocation/reservation/reset; sequence observations are not MVCC snapshot guarantees |
| Logical candidates | Whole matching rows in six recorded government JSON fields: sources2121/2392, audits5067/5208/5245/5545/5679/5716, extraction6398; no entity/indicator/population numeric-ID matches |
| Recovery catalogues |5 installed extensions,30 roles without password hashes,21 memberships,11 schema ACL records,102 relation ownership/RLS/trigger-count records and large-object count0 |

No segment exceeded the row/byte ceiling or was omitted by the capture. That
statement concerns the **76 recorded sections**. The numeric-ID JSON probe does
not establish arbitrary logical/external dependency completeness, and catalogue
counts do not replace full ACL/RLS/trigger definitions or a private archive.
All source/county/target audit/extraction/CPI/fixture/population79 images are
equal parsed JSON values to Round17's complete images. Publishers,
four official-code cells, CPI values and OAG texts remain unapplied.

Fresh exact five-source rows are2534/2535/2536/2537/2540, with their retained
plan URLs and institution/year discovery metadata. Each has absent MD5 and
`discovered_not_fetched` registration; the current audit-count query finds no
findings on those five IDs. The three newer adopted cohorts remain2898 findings
and141 explicit county/institution/year cells:2539 FY2023/24 executives1047,
2541 FY2024/25 assemblies582,2542 FY2024/25 executives1269. Legacy2395/2396 retain
1498 findings with null explicit volume kind;2391 has one unlocated unknown-role
row. National2392 has814 stored audits/813 extraction links, not a new claim of
814 published findings. The236 grouped rows are split by source identity; they
must not be counted as236 distinct coverage cells. Stored publishable flags and
linked-locator counts are not the runtime publication predicate or official
publisher verification.

## Writer and recovery limits for the concrete execution target

At21:39:46UTC the public pipeline endpoint reports a running reference refresher,
last county completion20:30:09UTC and next county refresh9October20:30:09UTC.
Dedicated domain job health remains `not_checked_here`. At the database query
instant, seven sessions are visible; the capture is the only visible active
transaction with xact_start. This does not reserve a later writer-free window.
pg_cron and pg_net background workers exist, while their job/run/queue relations
do not resolve in this database. Other-database/cluster/provider/manual jobs are
not inventoried. ActionsOFF, an empty service job list and an instantaneous
transaction sample do not establish exclusive writing.

S01 can consume the complete role/extension catalogue without another provider
scan. Installed extensions are pg_stat_statements1.11,pgcrypto1.3,plpgsql1.0,
supabase_vault0.3.1 and uuid-ossp1.1, with Supabase-owned schema/roles/ACLs.
The17.6 server preloads additional libraries, including pg_cron/pg_net; preload
is not installation in this database. Compatibility of the selected local
restore image with these exact extension/owner/privilege requirements remains
unverified. Vault/auth/storage/private contents and storage object bytes were
not read. No full archive, globals/password export, restore or recovery operation
was performed.

The next production decision needs the compatible complete private archive and
restore proof, named exclusive writer/outage window, exact refreshed forward and
inverse/source hashes after preceding operations, and final concrete approval.
Then owner signing and actual marker/adoption/public transition acceptance can
run. Current catalogue and process receipts narrow those inputs; they authorize
none of the operations. Source298/299/347 decisions remain outside this capture.
Supabase quota/backups UI was deliberately not reread: its Round17 receipt
retains its original18:58UTC date, not a new observation.

## Evidence and validation

The bank contains `ROUND18_SESSION_2_PROVIDER_READONLY.json`,
`ROUND18_SESSION_2_PUBLIC_GITHUB_READONLY.json`,
`ROUND18_SESSION_2_ENDPOINT_CHECK.json` and
`ROUND18_SESSION_2_EXECUTION_TARGET_DELTA.json`, plus frozen generators. Receipt
provenance was read back from disk. Independent offline review accepted the
original bundle, rejected all 44 hostile copies, and passed 44 document value and
arithmetic checks, with zero failures, skips or flaky cases. Its results are
recorded separately under `ROUND18_SESSION_2_ADVERSARIAL_*`; it does not recapture the
provider or certify human/source/full-backup acceptance. No application fix was
demonstrated, so no application test or broad browser suite is counted here.
