# OAG county catch-up and signed refresh: coordinator runbook

Scope: issues [#234](https://github.com/Rodgers31/audit_app/issues/234),
[#231](https://github.com/Rodgers31/audit_app/issues/231) and
[#378](https://github.com/Rodgers31/audit_app/issues/378). This is a reviewed
procedure, not a record of a production catch-up or a successful nightly.
The coordinator owns the serial production operations and secret configuration.

## Starting evidence, 29 September 2026

Scheduled [run 36512696196](https://github.com/Rodgers31/audit_app/actions/runs/36512696196)
used `1d5fa9f`, before the current `b54d50e` deployment. Its audit job
registered all eight county volumes, completed the first three with 47/47
chapters each, created 2,898 findings and deferred five at the 240-second
start budget. It reported zero failed or partial **new** volumes. This is
budgeted progress, not evidence of starvation. `test_eight_volume_backlog_advances_across_bounded_runs`
models eight volumes and a 240-second window with synthetic 100-second parses:
the successive outcomes are 3/5, 3/2, 2/0 and 0/0 processed/deferred,
with earlier volumes marked current and no duplicate extractions. Actual
production durations can differ.

The [accepted source manifest](../verification/2026-09-27-oag-coverage/accepted-source-manifest.json)
contains all eight exact OAG URLs, SHA256/MD5 digests, local extraction counts
and page counts. The five awaiting production extraction are:

| Fiscal year | Institution | MD5 in local accepted manifest | Local findings (comparison only) |
|---|---|---|---:|
| 2023/2024 | assemblies | `15cd6108a0f08498a9e9f699430b365b` | 541 |
| 2022/2023 | executives | `f49345102b734ddc4825110e44ef9113` | 1,041 |
| 2022/2023 | assemblies | `1e757ebf2480ab1959dd7e86e8fffddf` | 513 |
| 2021/2022 | executives | `cda52424386d5ab6afae21a4dc9dcde7` | 1,082 |
| 2021/2022 | assemblies | `6ac0f20f7a8bfe535775bccb1e81bdcc` | 532 |

The public API currently answers 0 findings for `year=2022`, 0 for 2023,
1,047 for 2024, and 2,664 for 2025. The 2025 total includes the separate
813 national findings; it is not a county count. A bounded
`year=2025&county_id=3&limit=100` response has 40 Nairobi Executive and 10
Nairobi City Assembly findings, with distinct institution labels and PDF page
URLs. These API observations are publication samples, not a 376-cell receipt.

Validation also failed on the 15-to-11 inflation census (#347), and named
older FY2020/21 documents 2395/2396 whose latest extraction attempts were
partial. No successful refresh ran. The national document 2392 reconciliation
proposal (335 retirements, two revisions) is separate; no county catch-up
authorizes it.

## Before dispatch

1. Confirm merged backend/frontend SHAs and current CI. Take a fresh encrypted,
   read-only production baseline of **every existing audit row**, keyed by ID,
   including source document/extraction IDs, publication verdict, amount,
   institution and page. Compare exact prior-row hashes after every pass;
   count alone cannot prove preservation. Capture all eight source-document
   URLs, current MD5, status, extracted MD5 and latest-attempt status. Stop if
   a source's current bytes differ from the accepted manifest until that
   edition is reviewed.
2. Configure one dedicated `REVALIDATE_SECRET` value in repository Actions
   secrets for `Rodgers31/audit_app`, Render service
   `srv-d6hr3t5m5p6s73bomqu0`, and Vercel project
   `rodgers31s-projects/audit_app` **Production**, as a server-only variable.
   Enter the same value in all three places, without printing or copying it
   into logs, issues or this document. Apply Render's environment change and
   make a Vercel production deployment that includes its new variable. Record
   the resulting SHAs. At this check, Actions listed no such secret, Vercel
   listed five project variables and no linked shared variables, and Render
   listed 15 service variables and no linked environment group; neither
   service listed `REVALIDATE_SECRET`. With no secret, both signed endpoints
   fail closed. An unsigned probe should change from 503 to 401 after the
   running services receive the variable; it must not invalidate anything.
3. Keep the workflow's constant `seed-production-database` concurrency group.
   Ensure no other seed or database-writing release operation overlaps the
   catch-up. Confirm source hashes, backup/recovery and available runtime
   headroom; stop if any of these are missing.

## Serial catch-up

Dispatch `seed.yml` on reviewed `main` with `domain=audits`,
`dry_run=false`, `run_bootstrap=false`, `run_validation=true`, **one run at a
time**. The equivalent coordinator command is:

```sh
gh workflow run seed.yml --repo Rodgers31/audit_app --ref main \
  -f domain=audits -f dry_run=false -f run_bootstrap=false \
  -f run_validation=true
```

After each run, record the audits `ingestion_jobs` ID/status and
`metadata.county_volumes`: `discovered`, `processed`, `already_current`,
`deferred`, `failed`, `partial`; also `documents`, discovery errors, source
hashes, committed finding IDs and exact prior-row comparison. A completed
volume must move from `processed` to `already_current` on a later run; the
remaining list must shrink. Deliberate deferrals are explicit and may leave
validation red. Do not turn validation off to get a green refresh, increase
the budget blindly, rerun concurrently, or continue past a failed/partial
new volume. A stalled sequence with the same deferred labels and no new
committed findings is a new scheduling diagnosis, with logs and timings.

When all eight are current, the older-document queue becomes eligible again.
Document 2392 may propose historical retirements and documents 2395/2396 may
remain partial. Review their exact source and row-level proposals separately;
do not apply a blanket acceptance or bypass the publication/reconciliation
guards. The coordinator must also resolve #347's inflation identity question
before a successful full validation can certify the night.

## Completion and no-deploy proof

1. Run the existing `county_audit_coverage_receipt` against production in a
   bounded read-only session. Require all **47 counties × four fiscal years ×
   two institutions = 376** cells to carry attributable published evidence,
   the correct Executive/Assembly names, source document and page, and no
   unexplained run gap. Reconcile the five actual production finding counts
   against their source PDFs and the local manifest; do not assume the local
   counts must match a changed publisher edition. Inspect representative
   pages in each year and institution. Compare all pre-catch-up row hashes.
2. Require the whole workflow's seed and validation jobs to pass, including
   the economic census and any older audit-source refusal. Only then may the
   `revalidate` job run. Its receipt must show HTTP 200 with
   `invalidated: true` from the API **before** the frontend call; the frontend
   must return exactly the manifest's requested paths, with `rejected: []`.
   The [single path manifest](../../frontend/lib/revalidation/paths.json)
   includes `/audits` and the `/counties/[id]` pattern for all county pages.
3. Choose a newly accepted, source/page-backed finding visible on a rendered
   page. Record its API value and server-rendered page content before and
   after the successful seed and refresh, with backend and Vercel deployment
   SHAs unchanged during that data transition. A restart, TTL expiry or a
   deploy is not the requested no-deploy freshness proof. Record the first
   public page read after the refresh and its matching source citation.

Keep #234/#231/#378 open until these production observations exist. Code tests
and a local replay establish the mechanism, not the completed publication.
