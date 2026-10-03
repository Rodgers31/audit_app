# Round20 actual production acceptance — 3 October 2026

This is the completed production follow-up to the earlier
[coordinator review](2026-10-03-round20-coordinator-review.md). That earlier
packet records the state before the owner's credential and maintenance approval.

## Recovery and runtime

The owner approved the common server-only cache signing key in Render, Vercel
Production and GitHub secrets, and the maintenance window. The API was suspended
09:34–09:55 UTC and returned readiness HTTP200 at 09:57. Supabase was not paused.

An actual logical archive was acquired at 09:45:43 UTC. The bounded acquisition
took 81.97 seconds and observed 34,024,762 transport bytes. An isolated,
network-disabled Supabase PostgreSQL17.6 restore matched all 68 table inventories
and 30 sequences, with captured roles, settings, ownership and privileges.
Three explicit logical equivalences addressed physical attribute holes and ACL
ordering. The original strict physical comparison failure was retained.

This establishes a logical database fallback and the prerequisites for scoped
fact inverses. It does **not** certify full Supabase infrastructure disaster
recovery: provider credentials, Auth/runtime configuration and external storage
recovery are separate inputs. No whole-database restore was applied to production.

Actual restore acceptance SHA256:
`660a10887580e8f413f87d62462d37b32205f9f7975f34bdadc722b1bbae158f`.

The fixed-runtime experiment used backend and frontend commit
`1b6990d4db8da89003ad68e87f8db9160ce27225`. Automatic seeding and the Parliament
pipeline were disabled. Render served one instance and one worker, with the
generation marker at `/tmp/auditgava-cache-generation`.

## Actual guarded fact corrections

| Operation | Committed result | Preserved scope |
| --- | --- | --- |
| Publisher correction | Source 1840: Central Bank of Kenya; source 2383: National Treasury | Whole source images apart from the declared correction, linked loans and unrelated tables |
| County codes | Nairobi official code047; Mombasa official code001 in their two current financial-year records | Legacy routes `/counties/001` and `/counties/047`, financial values and all other county fields |
| #379 text boundaries | Findings 5545, 5679, 5716 now contain their actual current finding only: 500,713,586 characters | IDs, periods, amounts, source/institution and all unrelated findings; legitimate current narrative retained |
| Five-volume OAG catch-up | Added 3,709 audits and matching extractions across five selected FY2021/22–2023/24 volumes | Original audit/extraction cohorts and three adopted volumes; no relaxed TTL, parser or source gate |
| CPI | Jan 2025 rows 67/86: 142.68; Dec 2024 row 87: 141.66 | 322 other economic rows, population row79, loan426, all counties and original source/extraction cohorts |
| Legacy fixture cleanup | Deleted only audits 870–894; removed exactly 58 reviewed metadata keys | All 47 current `stalled_projects` wrappers, richer metadata, sources 1836/1707/1718, CPI, financial facts, schema/FKs/sequences |

CPI is the KNBS national Overall CPI, February 2019=100, unit
`index_2019_02_100`, sourced to new documents 2551/2552 and their page 2/Table 1.
Corrected CPI rows are source-bound and publishable. Public API acceptance was
observed; no rendered CPI chart is claimed.

Each operation had a fresh exact before-state, a rollback-by-default dry run,
durable execution evidence and independent after-state protection checks.
CPI and fixture cleanup inverses were dry-run against the actual final guards.
The catch-up's current exact inverse is prepared; it was not run in production.
No inverse was committed and no preserved source was silently retired.

## Validator defects found during acceptance

### #468: repeated shared context and query timeout

The original county coverage query exceeded its actual 15-second statement
timeout. It transferred complete county and source objects for every finding.
The fix retains the identical eligibility joins and publication predicate, reads
Audit/Extraction pairs and batches distinct source context once. The existing
county inventory is reused. Controlled transfer size fell from 19,492,044 to
209,412 bytes with identical 376 cells. This is a fixture measurement, not a
claim about the provider's aggregate billing.

All 180 focused tests passed. Seven meaningful regression controls failed on the
old code and passed on the fix. Independent execution covered 50 mutations,
including 45 required refusals. The actual candidate production capture completed
with the unchanged 15-second per-statement limit.

### #469: JSON transport falsely rejected complete evidence

JSONB object order changed the adopted-proof list's iteration order. Plain
Python equality also rejected a durably written image when integer year keys
returned as JSON string keys. Complete typed proof fields are now bound to
unique exact URLs; canonical encoded comparison handles the JSON boundary.
Duplicate identity, changed values/types and malformed evidence remain refused.

All 148 focused transport tests and 33 independent executed cases passed
(27 proof cases, six real CLI seams). Fresh actual seed observation job 3237
completed successfully with no new audits/extractions and all eight editions
current. All 3,709 added audit/extraction hashes and IDs remained exact; selected
sources changed only their observation timestamps. Five publisher HTML requests
returned HTTP200; PDFs were cache hits, without re-download or reparse.

The actual tested candidate was
`9db896dc5c25172d4b7b71140e97c9393f1cfc17`. No acceptance gate or source authority
was weakened to make the operation pass.

## Full validation and remaining coverage warning

The operational FULL validator completed 12:50:19–12:50:42 UTC, exit 0, with
**zero critical errors and four warnings**. It recorded exactly one completed
20-entry row-count checkpoint, job 3238. All 15 protected table digests and the
existing ingestion-job cohort remained exact; only the census sequence advanced.

The warnings were:

1. National discovery was unrecorded on this deliberately scoped county run.
2. The bootstrap fixture was superseded; its modeled financial metadata was removed.
3. Learning Hub remains a fixture by design, without its own extractor.
4. Older FY2020/21 documents 2395/2396 retain genuine partial extraction attempts.

The eight FY2021/22–FY2024/25 executive/assembly proofs contain all 376 positive
county/year/institution cells and 6,607 findings. The **overall coverage receipt
remains WARN and strict coverage acceptance remains false** because of 2395/2396.
Their existing 986/512 supported findings were preserved. These unselected older
PDFs were not reparsed and their failure flags were not cleared. #234 stays open
for that final requirement; existing #347/#137 retain the related pipeline work.

FULL receipt SHA256:
`6b58f09e4d8ec9340c2c3bdcf0c7e8500d73295cba95d97027cc15334d46d7bb`.

One earlier private FULL wrapper incorrectly made the entire transaction read-only,
although the shipping validator writes its census checkpoint. Its failure was
retained. The corrected operational wrapper kept all actual validation floors and
warnings, and independently proved that the census was its only write. This was a
verification-harness error, not an application defect or a skipped gate.

## Cache refresh and public acceptance without deployment

At 12:54 UTC the actual signed backend invalidation, worker acknowledgement and
frontend revalidation completed in order. All ten allowlisted page paths were
acknowledged; no path was rejected. The serving worker adopted the observed
generation-file identity and reported synchronised=true.

Before and after the refresh, Render retained master PID 1/start 77749887 and
worker PID 25/start 77749962, the same source hashes and commit above. Final runtime
observation was 13:07:30 UTC. Vercel retained the same Ready production deployment,
`wdzupWALoVSTDriuainHePn7fqQ1`, at that commit. No deployment or process restart
occurred during the experiment.

Actual public HTTP200 responses and rendered browser results showed:

- Audit findings **5,209 → 8,918**, exactly the 3,709 added findings.
- All three corrected finding texts, including Nairobi Assembly's 586-character
  official-transport finding with the source/institution and page 239.
- Correct publishers for1840/2383 and source-bound CPI values/units/base/page.
- Legacy county routes still resolving Nairobi/Mombasa; rendered comparison
  headers explicitly showed `Nairobi #047` and `Mombasa #001`.

Signed-refresh receipt SHA256:
`3170ad95427af45c54b330e86257eb31cf9514969788243b98db5cd66d64314f`.
Public API receipt SHA256:
`5c3607c1d21f867aa477f172e89ad909daac327cfc089b87c29200b5213e1c2e`.
Append-only production summary SHA256:
`94f8ef2864a836f24080bf468ec9ed611a4c6e0bc8c0af24131e69a8ee7ac118`.

Raw credential-bearing backup material and detailed private captures are retained
outside the repository. The public screenshot is
`ROUND20_AUDITS_TOP_AFTER.png` in the owner's Round20 evidence bank.

## Closure boundaries

#273's original PR #262 was consolidated through #317 into merged #327. The current
fetcher declares National Treasury and the writer updates an existing publisher
only on an explicit declaration. The actual source 2383 correction and public
readback complete that issue. #379's parser regressions, exact stored correction,
protection and public/rendered readback complete that issue.

#468/#469 are covered by the validator fixes in this change. #319/#230 remain
open for their other source/disposition/publication requirements. #298/#299 retain
the unresolved revenue and four county cash sources. #231 has actual runtime/cache
acceptance, but its final hosted workflow/account prerequisites remain pending.

GitHub Actions were read back as `enabled:false`. No hosted workflow, paid bot
review or external publisher message was initiated. #291/#343 and hosted parts
of #137/#347 await the owner's separately approved final Actions batch. These
results do not claim that every open issue or every production data problem is fixed.
