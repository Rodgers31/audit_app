# Nightly recovery for issues 812–814

The failed 25 October Chicago nightly run retained published evidence: the OAG
parser proposed 23 text revisions; CoB's 53,561,130-byte PDF did not finish within
its 300-second transfer phase; fixed ordering then exhausted the 1,320-second
whole-run budget before later domains received an admission opportunity.

## Explicit OAG repair

The manual `audits_review=oag-2542-20261026` input applies only the committed
receipt in `backend/seeding/extractors/reviews/`. Scheduled plans reject it.
The exact previous rows, published audit IDs, source bytes, candidate content,
pages, confidence, and revised IDs must match. A fresh download's artifact
binding is independently verified by the extractor; only that new acquisition
context is excluded from the content digest. The full actual proposal and
review receipt remain in the document's reconciliation history.

Source document 2542, official County Executives FY 2024/2025 volume, has SHA-256
`033e2aa26aa77351ec46f062573f25ede47d3e3a99978aeacf9a66af5ba717a5`.
Complete native replay produced 1,269 findings across 47 chapters. All 23 text
changes remove a detached list of unresolved 2023/2024 matters appended to the
last 2024/2025 finding. Amounts, attribution, fiscal year and citations do not
change; no evidence or published link is retired. Source-page references and
before/after digests are listed in the committed receipt. Human source review
used all 23 text boundaries and rendered representative list pages 21, 45, 276
and 683. This is not blanket approval of future parser changes.

## CoB acquisition and scan

Only the hosted seeding profile selects a 420-second CoB transfer allowance.
It is capped again at the domain limit minus a 180-second parse/write reserve.
Other PDF transfer limits remain unchanged. Incomplete CoB downloads refuse
publication before fixture rows reach the writer; partial bytes stay in the
existing resumable cache. Range assembly or cache sidecars do not acquire new
HTTP provenance authority, and verified-source activation remains off.

Only the exact, fully compared report bytes take the fast path; future or
reissued PDFs retain the full scan. This prevents unfamiliar moved aggregates
from disappearing under a partially recognized index. The supported report's
own table index and independently checked captions
select summary and all 47 county revenue tables, including continuation pages.
Unsupported layouts use the existing full scan; inconsistent recognized
layouts refuse. Source SHA-256
`919930622bc9fbc0c0b5cdcb566219e4f1432e7c9a3329dfd5bb23616cd33c20`
produced identical 421-record digests from full and indexed scans. Existing
source-quality refusals for four county revenue tables remain in force.

## Fair progress and release gates

Multi-domain live workflow plans explicitly select fair admission. A bounded
read-only history query orders legacy sources by their last real entered job;
bootstrap jobs, dry runs, unlinked claims, and not-run observations do not
advance that queue. Explicit opt-ins retain priority. Failed real source
attempts do advance so one unavailable publisher cannot monopolize every run.
History failure admits no domain. The explicit one-off repair gives OAG and then
CoB priority for the two source checks; ordinary scheduled plans do not.

The domain limit remains 600 seconds, whole-run limit 1,320 seconds and Actions
step limit 25 minutes. Admission remains serial through the existing native
owner and exclusion claims; no hidden second pass or parallel writer is added.
A bounded refresh is a qualification attempt, not a guarantee all sources fit.

Deploy only the reviewed tree to the existing services. Verify resolved source,
flags, database identity, runtime limits, health and zero active claims before
advancing write admission to that exact commit. Dispatch at most one approved
manual refresh with bootstrap false, validation true and this exact OAG review
input. Observe the admission plan immediately, source refusals, claim closure,
data changes and downstream cache/page steps at completion. Stop for wrong
source/flags/DB identity, overlapping owners, missing timeout enforcement,
unexpected write scope or publication activation. Keep publishing, uploads,
new-source activation and worker supervision off.

Rollback the code to accepted commit
`3f09dd05fd765977c4467d953829c17300633460` on the existing services and restore
its exact `INGESTION_WRITE_APPROVED_SHA` only after that serving revision is
verified. Pause nightly admission if the new release fails qualification; do
not erase jobs, claims, retained downloads or reconciliation history. A source
repair is not automatically reversed by a code rollback: any reversal requires
its own exact source-checked reconciliation. No migration, new access grant,
credential, hosted review, paid resource or plan change is part of this repair.
