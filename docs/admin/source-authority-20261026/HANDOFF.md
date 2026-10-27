# Native report publication authority — 26 October 2026

Base: `6fdce855950e94cb30c43dfdcd8307885795b3cf` (PR816 merged tree
`90724835b5e36a99677314a39f5078e52944d76c`). Related issues: #801 and #802.
Neither issue's full acceptance is completed by this change.

## Concrete change

CoB's actual annual report download posts supply an explicit publication timestamp
in `article:published_time`, corroborated by the visible `Publish Time` and full
visible day. The native producer can now retain this second official artifact
instead of requiring an artificial full-day label inside the PDF. This is the
**publisher post's report-availability date**, not the PDF's creation, signature,
reporting or last-modified date. The later post modification is retained separately.

The narrow `cob-publisher-post-v1` contract requires one published WPDM post, exact
post ID/download link, canonical official URL, a reviewed annual title and fiscal
year agreeing with independently extracted PDF cover scope, consistent timestamp
and visible day, and intact retained acquisitions for both bodies within 900 seconds.
Unknown layouts, conflicting explicit PDF dates, post/PDF edition mismatch, stale
acquisitions, redirects to another identity, duplicate dates and copied JSON refuse.
Create Date, file-size labels, retrieval time and Last Updated cannot substitute.
A cache-only PDF receipt with unknown HTTP acquisition remains ineligible; no new
request-side PDF download is added to committed readers.

The native national-budget producer uses one additional bounded metadata stream
only after retained PDF acquisition and annual scope qualify. The stream has a
512 KiB/20-second ceiling, temporary owned scratch, and no separate social crawler.
Its failure leaves financial qualification independent and report eligibility
refused. It does not promote any financial value.

County pending bills now has a neutral annual **county report** adapter through
its native fetcher, domain writer, existing Extraction receipt, exact running job,
committed reader, preview, admin detect and existing default-off CLI hook. It uses
the native producer's existing `Office of the Controller of Budget (OCOB)` identity.
Its canonical destination is `/debt`. It does not claim a Treasury BROP report,
individual county audit, complete borrowing register or qualified financial draft.
The writer checks the same annual period/stock day, preserves its existing
savepoint and caller-owned commit, and invalidates prior authority on an
unqualified replacement, including direct legacy writer calls. No aging producer,
county borrowing mapping, financial publication rule or schema is changed.

Two existing PDF scope defects were exposed by the genuine national report:
equivalent `2025/2026` and `2025/26` headings were counted as distinct editions,
and the annual foreword's statutory “quarterly” duty was treated as subperiod
scope. Fiscal years now normalize before comparison; explicit subperiod refusal applies across all three inspected pages without
treating generic statutory “quarterly” prose as a report period. Duplicate
authority-bearing HTML attributes are refused before parser normalization.
The authority guard and existing financial parser now share the native CoB
subperiod vocabulary, including `FIRST HALF` without `YEAR`, with unchanged
financial period labels/end months. The first three pages independently establish scope; cached supplied text cannot grant authority.

## Source and completion matrix

| Source/domain | Code and checked evidence | Remaining qualification |
| --- | --- | --- |
| National budget / CoB | Native post/PDF contract implemented; genuine current retained PDF and official post replayed into owned PG and admin preview/draft | Production successful job/receipt adoption and separate draft-only rollout remain unperformed; cache-only acquisition still refuses |
| County pending bills / CoB | Native county report producer/writer/reader/adapter implemented; official post retained; synthetic PG/domain/CLI controls | Full genuine county PDF-to-native-job qualification, real job authority and live operator acceptance remain |
| Revenue / KRA | Existing article authority retained unchanged | Current FY2025/26 page contains an external testing-dashboard iframe and no accepted labelled article publication day; no iframe fetch/admission or older-release substitution |
| Audits / OAG | Existing explicit auditee/year-ended PDF adapter retained | Genuine publisher publication-day/artifact binding remains unqualified; no signature/upload/report date substitution |
| County borrowing | Existing editions/mapping guard unchanged; still zero genuine qualified instruments | Explicit issuer contract reference, namespace, exact issue date and dated outstanding stock evidence remain absent for checked facilities |
| Other native domains | Existing unsupported/refused capability contracts retained | Per-source authority/lineage and adapters remain under #802; KNBS enhancements #744/#745 stay deferred |

Fresh bounded trusted acquisition retained these public primary bytes outside Git:

* CoB national post: https://cob.go.ke/download/national-government-budget-implementation-review-report-fy-2025-2026/
  — 93,880 bytes; SHA256 `6ca2bf994f7d43eb7a462268ca251a194f581a1a4dd09f12b10554e885b3122e`;
  publication `2026-09-04T10:32:37+00:00`, modification `2026-10-14T08:40:37+00:00`.
* Exact linked national PDF (`?wpdmdl=16454`): 15,609,728 bytes; SHA256
  `f99ec2997f13400d2fc1fb340154c9b91640591c6d1351415fc075b259a7c4b1`.
  The cover says August 2026, and the annual foreword describes 1 July 2025–30 June
  2026. The month is not completed to a publication day. The official website's
  displayed 13.19 MB file size is not used as artifact identity.
* CoB county post: https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/
  — 94,312 bytes; SHA256 `34b44d867b0e3b1ce50210d290496a8d56c95bfe69017fdfac48cc788350324b`.
  This page alone does not qualify the retained 935-page county PDF or a live job.
* KRA current page: https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026
  — 91,512 bytes; SHA256 `52dbf4737111688eda96639c3193e841196741b4702cc1336ab973964217ab10`.

These are source research reads, not production ingestion. Local HTTP receipts
replaying those exact national bytes have explicitly synthetic acquisition/job
chronology. Genuine bytes plus local lineage are not a successful production job.

## County borrowing bounded follow-up

The existing B86 source review remains authoritative for the checked Homa Bay,
Meru and Mombasa facilities: their reported facility balances lack explicit
instrument references and exact issue dates. Repayment arrears, interest costs,
county-owed receivables and proposals remain separate. No zero or contract ID was
invented and no facility aggregate was added to instrument stocks.

Seven focused county/official-domain follow-up searches (plus two report-metadata
searches) did not yield an admissible positive mapping. Results included a
procurement bid-security addendum, a Mombasa Gate Bridge project loan reference,
and the existing Laikipia proposed bond/guarantee report. A project location does
not establish a county borrower. The Parliament report is an approval/guarantee
proposal, not an executed outstanding-stock account:
https://parliament.go.ke/sites/default/files/2022-08/Report-%20laikipia%20county-%20borrow%20issuance%20of%20ksh.1.16%20billion%20infrastructure%20bond.pdf
A Treasury external-register result described central-government borrowers; its
fresh direct web open returned 404, so no newly verified register is claimed.
No blanket county crawl, new mapping, checksum advancement or source activation.
Issue #801 remains the deduplicated source-evidence follow-up; no duplicate issue.

## Verification and operating boundary

External lane evidence:
`/Users/roger/.codex/visualizations/2026/10/26/01a17a90-5b58-7f22-8838-8a27b95df82d/source-authority`.
Source-bound run receipts retain command, source hashes, toolchain hashes, image
identity, raw bounded output, exit status and cleanup. Initial missing database
configuration, migration privilege setup, test import setup and first failing
controls are retained as failures/skips, not passing acceptance.

All execution uses a private network-none Linux container, read-only source and
cached toolchain, empty allowlisted environment, unprivileged OS user, dropped
capabilities, no socket/credentials, and bounded CPU/memory/PIDs/files/disk/wall
limits. PG17 runs only in that container's private loopback namespace, migrated
through unchanged `a756b20a0001`; the synthetic fixture DB owner is privileged to
exercise historical migrations and is not a production-role qualification.
Python3.12 cached runtime is compatibility evidence, not exact serving-version
parity. Synthetic controls preserve null/zero and financial qualification, silent
baseline, reasoned explicit backfill, replay/concurrent deduplication, source/job
refusal, rollback and metadata mutation rejection. Counts from overlapping runs
must not be added. Final reviews and exact receipts are listed in the local final
handoff; no hosted checks are certified.

Chrome remains reserved to the coordinator. No browser tab was claimed or
navigated. The exact existing admin detect/preview API paths execute locally;
Chrome rendering of the new county report option is pending a coordinated slot.
Before publication, retained current review/Preview controls must be consulted;
this lane does not change them or request bot review.

Rollback is reverting this code or disabling the existing generation ceilings.
Retain receipts, cursors, events, corrections and command history; never delete a
baseline to force another announcement. No new migration/grant, dependency,
workflow, dispatch/admission or source flag change. No production read/write,
refresh/backfill, deployment/merge, schedule activation, automatic approval,
publishing, upload, worker/native supervision, credentials, provider message,
plan/budget/retention/backup/key change or paid service/review occurred. The dirty
primary checkout and coordinator CURRENT_ACCEPTANCE remain untouched.

## Review observability correction

County report publication refusal now logs its controlled reason when authority
is withheld; the payload still retains the same reason and financial loading
remains independent. The interrupted-download fixture reproduces the missing
operator diagnostic before the fix and verifies it afterward. No new report
authority, rollout, writer permission or live source run is implied.
