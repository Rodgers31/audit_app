# Round16 inflation investigation and preservation (#347)

The current economic sweep could commit deletion of a source-linked alternative
solely because its date differs from the incoming annual calendar. Its identity
receipt also omitted the full observation before-image. Both defects were
reproduced through the registered domain and real CLI transaction on owned
PostgreSQL 16, then fixed locally. This does not restore any historical row.

The investigation also recovered full local archived row/source images, including
the four candidate IDs. Earlier statements that only their tuples were available
must now be qualified by this new evidence. The exact production dump/import
chain, state at deletion, database actor, commit time and authorization remain
unverified. No production read/write, count reset or monthly substitution ran.

## New local archive evidence

The retained `pg-test` container is stopped (finished September28 06:20:20 UTC).
Its original PostgreSQL17 volume was mounted read-only and copied into an owned,
network-disconnected volume. Only the copy was started, with no TCP listener and
no application/bootstrap. Crash recovery occurred on the copy. The original
container remained stopped. Its `pg_control` hash before/after was
`646e70067520238fab9f615c52f9d995456fe6d05785fff5c00ce1d05d04d01f`;
the frozen source-volume tar-stream hash is
`ee88f514446be1e74c3da4cd0831e3c5d92c80b35b1126129d183686fce34897`.
This hash identifies the retained cluster corpus, not a September26 export.

Bounded queries used `BEGIN READ ONLY`, `SET LOCAL statement_timeout='5s'`,
`SHOW transaction_read_only` (returned `on`) and `ROLLBACK`. The database
catalogue was limited to30 relevant names;21 databases were returned. Their
inflation counts identified19 fifteen-row candidates and two empty databases.
Selected full reads recovered:

- `audit_prodclone`:15 full18-column inflation rows; selected economic jobs
  stopAugust30. Do not present this database as a September snapshot.
- `audit_oag_pristine`: the same15 row images; retained economic job3128 from
  September24, census3139 from September24 with count15, and bootstrap3141
  from September26 09:08:28 UTC. All three referenced source-document images
  and the reflected columns were captured. All15 extraction IDs are NULL;
  there are no referenced extraction images to invent.
- `audit_fs237_pristine` and `audit_headline`: identical15 row images, September
  jobs and additional September26 local jobs. Identical rows do not establish
  an untouched clone or an independently captured production snapshot.

The recovered candidate identities are actual stored rows, not reconstructed
from the count:

| Archived ID | Date | Exact stored value | Source ID | Stored metadata |
| --- | --- | --- | --- | --- |
|65|2025-01-31|3.30|1823|KNBS CPI January2025; notes describe year-on-year CPI change; `data_quality=official`|
|66|2024-01-31|6.30|1715|KNBS CPI January2024; `data_quality=official`|
|84|2024-06-30|4.60|1823|KNBS CPI June2024; `bootstrap=true`|
|85|2023-06-30|7.90|1823|KNBS CPI June2023; `bootstrap=true`|

Each is national, unit`percent`, with NULL extraction/page/hash/basis fields.
IDs65/66 were created March26;84/85 April20. These are stored creation timestamps,
not a proven insertion actor or authorization. Source1715 points only to a KNBS
CPI listing. Source1823 is an unrelated combined debt/economic-survey document
with NULL URL, MD5 and file path. Source1856 has the World Bank inflation URL but
the archive's publisher field still says KNBS. None supplies original publisher
bytes or row-specific extraction. Metadata labels do not validate the figures.

Relative to the inherited September29 eleven-row diagnostic (IDs26–35 and98),
the archived-only IDs are65/66/84/85. Two January tuples exactly match job3160's
old-format removal list; that job still has no row IDs. The September24 census
has no identity array. This narrows the production candidates substantially but
does not certify that every field remained identical up to deletion. Surviving
IDs26/27 also changed values/source IDs between this archive and the dated later
diagnostic; the older6.6 values must not replace accepted newer World Bank data.

Raw, exact-numeric-string receipt:
`ROUND16_SESSION_9_SEPTEMBER_CLONE_LINEAGE.json`, SHA256
`262f132dd5affd65121aca6fc80d2381ef3a7140a99fe0e9d2c8eedb428b734f`.
Other query/copy/chronology receipts and an independent bounded readback are in
the coordinator's September27 artifact bank under`ROUND16_SESSION_9_*`.

## Invocation, persistence and authorization timeline

| Evidence time (UTC) | Invocation/observed output | Transaction/actor/authorization limits |
| --- | --- | --- |
|Sep24 02:36:04|Run35947298790 executes inflation census15; local archived census3139 agrees.|Count-only census cannot identify rows. Retained local rows require owner export/import/mutation provenance.|
|Sep25–27|Previously inspected validations fail importing psycopg before census; scheduled seed/bootstrap jobs are skipped.|No executed count or deletion inferred from those failed validations. Already tracked driver incidents are not reopened.|
|Sep26|PR248 describes a production-derived clone sweep of the same four tuples. Local September-bearing copies now provide candidate IDs/full fields.|PR prose and local job timestamps do not authenticate the original export/import chain or prove a live deletion.|
|Sep27 08:33:57|PR326 merges startup deletion code; current bootstrap later changed to preservation.|Merge time is not deployment/startup execution. June84/85 deletion by startup remains a hypothesis.|
|Sep28 02:53:41|Run36370404355 logs January2025=3.30 and January2024=6.30 removal intents; job3160 is recorded completed/non-dry/errors[].|Invocation and persisted job receipt corroborated; no original row IDs, DB principal, independently observed commit timestamp or authorization. GitHub scheduled actorRodgers31 is not DB actor proof.|
|Sep28 02:59:51|Validation reports11 against15 and fails.|The integrity failure remains evidence of unexplained historical loss, not authorization to lower the baseline.|
|Sep29|Dated read-only diagnostic: job3180 removes nothing;11 year-end World Bank rows survive.|Not a fresh production observation. Monthly CPI and annual World Bank inflation remain distinct.|
|Oct2 15:24:50|New PR248 CI log query: run36277625249/job108503304035 fails conftest import on missing psycopg; its artifact list is empty.|A genuinely new archive query, beyond the seven previously absent seed-run artifacts. No census/before-images produced. Does not exclude other backups.|
|Oct2|Owned PG16 CLI red/green and PG17 read-only archive-copy inspection.|Synthetic tests establish prevention/transaction behavior; archived local evidence establishes stored candidates. Neither certifies deployment or historical authority.|

The new CI response has999 lines/111,295 bytes; SHA256
`e4e2a7c2f0f3be7451865555c05ed199b2a9e34bbe81b788c52feec3f956bc44`.
Only safe topical excerpts were retained. No repeat of the seven empty seed-run
artifact queries occurred. S03's dated provider UI says the Free Plan backup page
does not include project backups; this does not exclude owner/local archives.

## Verified current caller and repair

The sole non-test sweep caller is the registered
`economic_indicators.run` at`backend/seeding/domains/economic_indicators/__init__.py:49`.
It supplies a receipt collector, includes refusals in its domain errors and
returns receipts in metadata. CLI copies that result to the job and commits the
job with the observations (`backend/seeding/cli.py:319`,`:398`); dry-run rolls back
observations and retains an explicitly dry job. No separate receipt write or
production logging service was introduced.

The sweep now preserves any off-cycle row carrying a source ID, extraction,
locator/hash, non-bootstrap metadata or malformed metadata for source review.
A bootstrap flag cannot override that protection. Unknown metadata is a reason
to preserve, not certification of provenance. Annual year-end and monthly
month-end gaps retain the existing protection. Only unsourced legacy candidates
without additional evidence retain automatic retirement; their receipt includes
every mapped row column, with exact decimal strings and a deep-copied metadata
image. The log explicitly describes retirement as pending commit.

Bootstrap still preserves indicators (`backend/bootstrap.py:625`); production
startup calls `initialize_reference_data` at`backend/main.py:1703`, and weekly
bootstrap calls the same initializer. Retry/scheduled CLI runs use the same
registered sweep. Repository-wide caller search found no other production sweep
caller. Existing generic economic upserts at the same type/date key are outside
this off-cycle repair; no general chart-table provenance rollout was performed.
The direct helper's existing optional no-collector API has no other production
caller. Concurrency behavior and deployed parity were not established here.

## Executed verification and disposition

- Exact base writer rebound from280353055:13 failed/4 passed (exit1), including
  alternative/source-linked retirement and missing before-images. Failures were
  observed committed state/receipt assertions. Two rollback controls already
  passed on the base and guard against future atomicity regressions.
- Final targeted suites:89 passed, zero skips (exit0);14 new lineage tests also
  pass under their default durable SQLite fallback. PG16/SQLite results overlap.
- Independent adversarial review:98 final controls passed, including52 external
  PG controls and46 overlapping repository tests. Three first-patch bypasses
  were reproduced and repaired; after-deletion and final-commit failures retain
  exact originals and fail the job without a committed retirement receipt.
- Independent archived PG17 readback plus current-writer controls:2 passed;
  source-bearing archived candidates all preserved, unsourced contrast retired.
- All application-engine connection attempts were zero; unstubbed HTTP was
  blocked. Dotenv/Pydantic env files, seeder/warmup and provider access were
  disabled. These are local synthetic controls, not production parity or final CI.

Initial harness failures are retained: missing Country timezone (4 setup errors),
WB disabled against fake-source positives (3 failures/72 passes), and an archive
decoder treating SQL NULL extraction aggregation as JSON. None is hidden as a
successful product check. No dependency changed. Actions remained OFF.

The incident's original log/job investigation is complete as far as these
receipts permit, and the reachable prevention defect has a local repair. Do not
claim the15→11 production history reconciled. Root may close the executed failure
after merging if the remaining history obligation is explicitly transferred to
a separately tracked item and linked public acceptance remains under#378/#234.
Until root verifies that disposition, keep#347 open for source/history evidence.
#137 remains open for its broader source/schema/public acceptance; its historical
P1 step5 is still unauthorized. No new duplicate ticket is needed for this repair.

The exact remaining owner/provider request is now narrower: bind the retained
September-bearing clone to its original export bytes/hash/time/method, imported
DB identity and mutation history (especially bootstrap/seed/migration activity);
establish the four candidates' source/measure at the loss boundary and original
publisher bytes; correlate live deployment/startup/jobs with DB deletion/WAL/audit
records for June84/85 and January candidates65/66; supply the DB principal, commit
boundary and original reviewed authorization. A production-at-loss before-image
or proof of unchanged rows after export is still needed. No new questionnaire,
publisher contact, rollback plan or guessed restoration was produced.
