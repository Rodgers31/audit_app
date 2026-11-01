# Scheduled refresh failure — 31 October / 1 November 2026

The [scheduled run41268107359](https://github.com/Rodgers31/audit_app/actions/runs/41268107359)
started at2026-11-01 03:10:41UTC: **10:10p.m. Chicago time on31October**,
before the overnight daylight-saving transition. It failed at the accepted-source
revision guard, before the ingestion writer or database verification proceeded.

| Observed stage | Result |
|---|---|
| Data source health check | Success; this does not establish complete ingestion |
| Validate source selection | Success |
| Refuse writes outside accepted revision | **Failed**: dispatch`ce352b7` versus approved`178ff97` |
| Seed domains, data integrity, bootstrap, cache/page refresh | **Skipped** |
| Summary job | Completed; its success does not override the failed admission gate |

This is not another parser/lineage write failure. No domain writes from this
scheduled run were admitted. UI PR864 had advanced `main` to`ce352b7` at
2026-10-31 21:22:59UTC, while ingestion remained pinned to the previously
admitted backend revision. Exact-SHA admission also notices frontend-only Git
commits. The subsequent backend release PR865 merged at2026-11-01 12:03:12UTC;
its reviewed deployment and ingestion admission were completed later that morning
as`4386f49`. The nightly occurred between those release checkpoints.

The write guard worked as intended. The release/reporting handoff should have
made the unadmitted nightly window and skipped full refresh explicit. The fix
is completing and verifying the release/admission sequence, not automatically
allowing whatever SHA is on `main` or weakening the guard. A main commit and
its approved ingestion pin can intentionally differ while a release awaits
review; that state must be reported as a held refresh.

## What the later manual runs established

| Actual run | Selected scope and result |
|---|---|
| [41311313399](https://github.com/Rodgers31/audit_app/actions/runs/41311313399),01Nov13:27UTC /7:27a.m.CST | National budget only: live job3579, ten rows/twenty cells revalidated; stored amounts unchanged. |
| [41312227919](https://github.com/Rodgers31/audit_app/actions/runs/41312227919),01Nov13:38UTC /7:38a.m.CST | Audits only: workflow success, but native job3581 completed with errors and acquired no report authority. All8,920 findings unchanged. Cached bytes lacked original persisted HTTP acquisition receipts; separate broad discovery/API/PDF warnings remained. |

Neither was a rerun of all nightly domains or the Sunday bootstrap. Other
domains were not refreshed by those two operations. A green workflow summary
must not be presented as complete source acceptance; the OAG result remains
refused until actual receipt, current-reader and data-preservation checks pass.

PR869 addresses the finite OAG acquisition gap with four reviewed PDF editions,
fresh acquisition, canonical finding checks and explicit source-only child
controls. It does not itself replay the missed full nightly refresh. Its release
requires matching reviewed/deployed/admitted SHAs, two bounded OAG checks and
exact before/after evidence; acceptance is recorded separately after execution.

## Release and next scheduled-run checks

The release must finish with `main`, the actual Render source and
`INGESTION_WRITE_APPROVED_SHA` equal. Both owned OAG checks must pass that same
workflow admission gate. Publishing, uploads, workers, financial generation and
native financial source admission remain off; other original repository
variables and schedules are restored exactly after bounded checks.

The existing cron is02UTC Monday–Saturday and03UTC Sunday. Following the local
clock change, its next configured slot is **8p.m. Chicago time on1November**
(2026-11-02 02UTC), subject to GitHub queue delay. It is not a fixed9p.m. local
schedule. The actual next run still needs observation; this report does not
claim that a future full refresh has passed. No additional full hosted rerun,
continuous monitor, paid check or resource is introduced here.
