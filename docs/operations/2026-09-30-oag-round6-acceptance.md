# OAG Round 6 correction and coverage acceptance packet

Prepared 30 September 2026 (America/Chicago) from merged base
`31e4735720bd385bea90616f953649f937decf6f`. This records development
acceptance and proposed release commands. It grants no production write,
seed, cache refresh, Actions enablement or issue closure.

## Fresh observations

The bounded production READ ONLY observation at
`2026-10-01T03:15:02.595642+00:00` (30 September, 22:15 Chicago) confirms
three complete county volumes, 2,898 published findings, and 141 present / 235
missing cells in the required 47 counties × four fiscal years × two institutions.
All 47 counties have FY2024/25 Executive findings. The five other editions
are registered and deliberately deferred, with no fetched MD5 or extraction
attempt. Their `FAILED` registration status does not establish a failed download.

| FY | Institution | Production document | State | Published findings | Local exact-source findings |
| --- | --- | ---: | --- | ---: | ---: |
| 2024/25 | Executives | 2542 | complete, 47 chapters/counties | 1,269 | 1,269 |
| 2024/25 | Assemblies | 2541 | complete, 47 chapters/counties | 582 | 582 |
| 2023/24 | Executives | 2539 | complete, 47 chapters/counties | 1,047 | 1,047 |
| 2023/24 | Assemblies | 2540 | deferred, not fetched | 0 | 541 |
| 2022/23 | Executives | 2537 | deferred, not fetched | 0 | 1,041 |
| 2022/23 | Assemblies | 2536 | deferred, not fetched | 0 | 513 |
| 2021/22 | Executives | 2535 | deferred, not fetched | 0 | 1,082 |
| 2021/22 | Assemblies | 2534 | deferred, not fetched | 0 | 532 |

[Source/refusal matrix](../verification/2026-09-30-round6-oag/source-coverage-matrix.csv)
retains URLs, cached SHA256/MD5, observed database MD5, source/attempt status
and exact refusal reasons. [376-cell production matrix](../verification/2026-09-30-round6-oag/county-coverage-matrix.csv)
records published source presence; it is not an exhaustive text audit.
The existing [accepted source manifest](../verification/2026-09-27-oag-coverage/accepted-source-manifest.json)
remains the source-edition authority. A fresh fetch of OAG's
[county listing](https://www.oagkenya.go.ke/county-executives-assemblies-reports/)
and four year pages still lists all eight exact URLs and no FY2025/26 edition
on that listing. PDF bytes were replayed from the hash-verified cache rather
than re-downloaded. Listing absence is not a finding count of zero.

Latest executed audits job **3176**, started `2026-09-29T02:29:13.234557`,
reports three processed, five deferred, zero failed/partial new volumes,
and the unchanged 240-second start budget. National document 2392 remains
separate: 813 published findings, with the existing reconciliation refusal
requiring review of 335 retirements and two revisions. Older county documents
2395/2396 retain 986/512 findings and partial unreadable-source attempts.
Neither national coverage nor retained older findings fills a missing
FY2021/22–FY2024/25 county cell. No refusal was overridden.

## Three-record stored-text correction

Fresh database and bounded public API reads match all three before-images.
The existing correction tool freshly replayed both pinned and current parsers:
47 chapters, 582 identical identities/metadata, 579 unchanged texts and exactly
three changed texts. Visual page review confirms each current conclusion ends
before the separate historical table. The source edition is:

- URL: [FY2024/25 Assemblies PDF](https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-ASSEMBLIES-2024-2025-1.pdf)
- SHA256: `aa72b0a512fe01ce8f40b9ed8597bd78657a9f441a8daf4963b07e661104d896`
- MD5: `f495cb595c81583af7d8bbd46e2279d6`
- Reviewed manifest SHA256: `8504dd3243d56a5de8b98eea717faf0c8de484be3e3b28a00b2c8342c0228961`
- Fresh production plan SHA256: `57a73173edaa838a589c3e5e5a091042da801db3a23c6d8050ab6b0ced36338a`

| Audit / extraction | Reference | PDF / printed page | Text characters before → after |
| --- | --- | --- | --- |
| 5545 / 6023 | `OAG-CV-2024/2025-A33-P453` | 168 / 155 | 1,251 → 500 |
| 5679 / 6158 | `OAG-CV-2024/2025-A44-P603` | 221 / 208 | 1,640 → 713 |
| 5716 / 6196 | `OAG-CV-2024/2025-A47-P645` | 239 / 226 | 5,548 → 586 |

Use the existing [guarded correction runbook](2026-09-30-oag-boundary-correction.md),
tool and manifest. Parser deployment or an unchanged-MD5 seed cannot repair
these stored texts. Source 2541 and FY2024/25 identities stay fixed. Only each
audit/extraction text pair and its canonical audit source hash change. Amounts
remain absent, and all other fields/publication verdicts are preserved.

## Executed development evidence

Session-specific external receipt root:
`/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170/ROUND6_SESSION_2_EVIDENCE_2026-09-30/`.

- `production-readonly-plan.json`, `production-readonly-metadata.json`,
  `production-readonly.log`, `production-recovery-review-packet.json`: two connections with startup READ ONLY enforced,
  `transaction_read_only=on`, refused INSERT SQLSTATE `25006`, narrow bounded
  source/census/job reads and rollback. No successful production DML.
- `fresh-public-before.json`: exact public text hashes for 5545/5679/5716,
  references, institutions and PDF page URLs. Public text remains uncorrected.
- `fresh-official-listing.json` and captured HTML: fresh listing receipts.
  `fresh-source-page-{168,221,239}.png/.txt`: fresh renders/text from the
  exact cached correction PDF, visually checked against the three boundaries.
- `cli/cli-receipt.json`: actual CLI prepare/dry-run/commit/recovery,
  wrong-digest/existing-receipt/repeat-commit/wrong-state recovery refusal on a
  disposable PostgreSQL schema; full inventory restored. Synthetic clone
  plan digest `2f147b386f807b5fe1903e9206966b036700373402da1c3cf4e1e3772a64c132`
  is not the production plan or a release authorization.
- `final-tests.log`: **230 passed**, four warnings, no skips; the existing
  correction tests use real PostgreSQL and the exact cached PDF. Includes
  atomic DML failure rollback, absent/malformed evidence, duplicate/payload/
  source/period drift, numeric JSON type drift, zero-vs-absence, loader
  preservation and recovery. General parser/domain fixtures use synthetic
  inputs; the eight-volume 3→3→2→0 scheduling test uses synthetic 100-second
  parse costs, not a production-duration forecast.
- `offline/serial-replay-summary.json`: existing runner against a fresh
  PostgreSQL 16 database, cached exact PDFs, HTTP sends blocked, OCR off;
  newest pair yields exit 2 with six explicit deferrals; all-listed completes
  the other six; repeat skips eight. 6,607 real-source findings plus one
  synthetic unrelated control; coverage becomes 376/376. Worker bounds stay
  900 seconds / 6 GiB; downloads retain 120 seconds / 40 MiB bounds.
- `offline-inventory-proof.json` and before/after hashes: every audit and
  extraction column/ID and source-document identity preserved on another
  bounded no-op; every finding has coherent source, PDF page, text, payload
  hash, institution/year and loader provenance; 47 chapters/counties in each
  of eight volumes. Three FY2023/24 Executive findings retain absent printed
  page values rather than invented offsets; PDF page citations remain present.
- `local-engine-red.log` → `local-engine-green.log`: a real libpq reproduction
  found that inherited `PGHOSTADDR` redirected the local writer despite URL
  validation. The runner now pins `hostaddr`, the psycopg2 driver, local
  TLS/GSS settings and an 8-second connect timeout. Real PostgreSQL positive,
  separate environment override and combined override controls pass. Remote/
  wrong-database/query-override/unsupported-driver/missing-target refusals
  continue to run before engine creation. `independent-connection-probe.json`
  executes the merged-base and fixed functions separately: baseline connection
  succeeds; each address/TLS/GSS override fails on the base and succeeds on
  the fixed function. No new extractor defect was proved.

Earlier harness failures remain in receipts. Missing period/severity on a
synthetic control were setup errors. The first source replay correctly refused
preservation when publication backfill normalized that control's null label
to `no_page_reference`; the final baseline uses that observed label. A public
comparison was corrected to include the manifest's `#page=` fragment; an ORM
enum serialization and an assumption that every printed page exists were
corrected in the verification harness. None is represented as an app defect.
Ruff was unavailable in the existing runtime; AST syntax checks and
`git diff --check` were used, with the executed behavioral tests above.

## Future release commands — separate owner authorization required

1. Freeze the reviewed backend/frontend SHAs, reserve the serial ingestion
   window, and take an encrypted baseline/recovery backup of all audit and
   extraction rows, source metadata, IDs/sequences and publication fields.
   Keep the pinned baseline Git object
   `c76ad74877dcd29a284b548c928f59538553fa0f` available. Set a secure unique
   release directory and the hash-verified PDF path. Supply
   `OAG_BOUNDARY_DATABASE_URL` using the owner's secret mechanism, with an
   explicit supported remote TLS mode. Set `PYTHON_DOTENV_DISABLED=1` and
   ensure general import/test tools retain a synthetic `DATABASE_URL`.
   Do not load a live default database into general tools.
2. Prepare a new correction plan using the existing CLI, with startup READ
   ONLY enforced and the bounded INSERT-refusal connection proof described
   above. Do not reuse a digest without checking the current full snapshots.

```sh
PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=8000 -c lock_timeout=2000' \
python scripts/verification/oag_boundary_correction.py \
  --pdf "$OAG_RELEASE_PDF" \
  --manifest backend/tests/fixtures/oag_boundary_reviewed_manifest.json \
  --output "$OAG_RELEASE_DIR/boundary-plan.json"

PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=8000 -c lock_timeout=2000' \
python scripts/verification/oag_boundary_correction.py \
  --pdf "$OAG_RELEASE_PDF" \
  --manifest backend/tests/fixtures/oag_boundary_reviewed_manifest.json \
  --plan "$OAG_RELEASE_DIR/boundary-plan.json" \
  --expected-plan-sha256 "$OAG_REVIEWED_PLAN_SHA256" \
  --output "$OAG_RELEASE_DIR/boundary-dry-run.json"
```

3. Only after exact-plan authorization, use the same reviewed arguments with
   `--commit` and a fresh exclusive recovery-intent path:

```sh
python scripts/verification/oag_boundary_correction.py \
  --pdf "$OAG_RELEASE_PDF" \
  --manifest backend/tests/fixtures/oag_boundary_reviewed_manifest.json \
  --plan "$OAG_RELEASE_DIR/boundary-plan.json" \
  --expected-plan-sha256 "$OAG_REVIEWED_PLAN_SHA256" \
  --output "$OAG_RELEASE_DIR/boundary-recovery-intent.json" --commit
```

The receipt records intent before DML. Inspect the database against both full
snapshots after any interruption; receipt existence does not prove commit.
Verify three stored text/payload/hash pairs, all preserved columns, and public
after-text hashes after the authorized normal refresh. For recovery, run the
same plan/digest with `--recover` first without commit, then with `--recover
--commit` and a new receipt path after authorization. Recovery refuses any
intervening evidence drift; obtain a new reviewed plan rather than forcing it.

4. Before any live county seed, confirm every source MD5/SHA256 matches the
   accepted edition, pre-existing row hashes are banked, and the current three
   volumes are skipped. After explicit authorization for Actions enablement
   and the final data batch, account access restored, and repository/workflow
   states rechecked, dispatch one bounded run at a time:

```sh
gh workflow run seed.yml --repo Rodgers31/audit_app --ref main \
  -f domain=audits -f dry_run=false -f run_bootstrap=false \
  -f run_validation=true
```

Record the run ID and reviewed main SHA. Use read-only `gh run view RUN_ID
--repo Rodgers31/audit_app --json jobs,status,conclusion,headSha,url` to retain
outcomes; do not dispatch the next pass until seed and validation outputs are
reviewed. Require explicit progress in the deferred set, unchanged prior row
hashes/IDs, and exact source/chapter/page receipts. Stop on a failed/partial
new source or drift. Production timing can differ from synthetic scheduling.
Do not raise the start budget, disable validation or bypass refusals to obtain
success. The general audits workflow may attempt national/legacy documents
once current volumes finish; their refusals must remain visible and their
stored changes require separately reviewed plans. No catch-up authorizes
national retirements, source1823 changes, #319 cleanup or source retirement.

5. Resolve the preserved historical inflation acceptance (#347, 15→11) and
   the older-source refusals before certifying full validation. Configure the
   same server-only `REVALIDATE_SECRET` in Actions, Render and Vercel through
   the authorized release process. Fresh Actions names still omit it; current
   Render/Vercel state was not re-inventoried here. Billing/access and refresh
   credentials are prerequisites, not reasons to lower the gates.
6. Require seed and full validation success before the existing `revalidate`
   job runs. Retain HTTP 200 and `invalidated: true` from the API cache call,
   then exact frontend acknowledgement of
   `frontend/lib/revalidation/paths.json` with `rejected: []`, including
   `/audits` and `/counties/[id]`. Capture a newly source/page-backed finding
   and the three corrected texts through API and rendered pages before/after
   that refresh, with backend/frontend SHAs unchanged during the transition.
   A deploy, restart or TTL expiry is not the no-deploy refresh receipt.

County catch-up recovery requires the owner's full backup and a separately
reviewed reversal of precisely banked new audit/extraction/source/job changes;
this packet supplies no live catch-up rollback mutation. The three-row CLI
recovery applies only to the stored-text correction. Preserve any newer
intervening evidence and refuse a blanket restore or deletion.

Keep #379 open until corrected public text is observed. Keep #234/#378/#231
open until live coverage, full validation and seed→refresh→page acceptance
are recorded. Actions remains OFF during this development delivery.
