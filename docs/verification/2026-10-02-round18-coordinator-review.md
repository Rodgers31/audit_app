# Round18 coordinator verification

Reviewed 2 October 2026 against main
`4acd7c0270a78a035557575125d77743ac2dbd5d`. All six sessions completed.
Four supplied commits; fixture integration and county-tab diagnosis supplied
evidence without a product patch. Two independent PRs separate recovery/context
work from the opt-in five-source OAG execution boundary.

## Changes and discoveries

- Local backup rehearsal adds a dump watchdog, sampled transport abort, private
  archive publication, hash-bound inputs and isolated restore comparison. It
  deliberately has no production acquisition mode and never certifies a full
  production recovery. Sampled aborts can overshoot; no hard 256 MiB transport
  ceiling is established.
- CPI inverse now binds retained shared-source images to the reviewed manifest.
  Rehashing an edited receipt cannot omit or replace that authority. Four
  regressions and independent baseline controls reproduce the prior bypass.
- Independent coordinator review found two malformed catalog inventories that
  compared equal to themselves: null identity metadata and duplicate relations.
  Both reproduced before the fix. Catalog identities now must be meaningful and
  unique; PostgreSQL's actual JSON string OIDs are preserved. An initial overly
  strict integer-only OID check failed real restore tests and was corrected before
  publication. These findings are recorded under the existing recovery scope in
  #231/#319; no observed production damage is asserted.
- The new explicit `--audits-source-manifest` accepts only the exact reviewed
  five-edition packet. CLI, handler, registration, fetched bytes, extraction and
  loader boundaries enforce it. Publication backfill is restricted to selected
  sources without changing its predicate. Normal scheduled execution remains
  unchanged; no schedule or production feature was enabled.
- A fresh consistent read-only observation supplies prospective correction
  context. It is not a full backup. Actual Render observation found Gunicorn
  master/worker processes and no observed generation marker; signing/adoption
  requirements remain unresolved.

## Executed verification

Fresh coordinator checks on the consolidated source:

| Check | Passed | Failed | Skipped | Boundary |
| --- | ---: | ---: | ---: | --- |
| OAG scope, CLI budgets, default ingestion, loader, publication and coverage |297|0|0|Isolated SQLite; application engine and unstubbed outbound requests refused|
| CPI forward/inverse and preservation |51|0|0|Disposable PostgreSQL 17.11 with retained source PDFs|
| Backup, archive, restore, timeout and inventory |24|0|0|Owned PostgreSQL 17.11/Docker resources; no application bootstrap|

Total: **372 final focused passes**. Earlier executions are retained separately:
an invalid test filename stopped collection, the two new inventory regressions
failed before their fix, and the first catalog patch rejected genuine string
OIDs. None is counted as a pass or hidden by retry.

Independent final checks include 71 inventory controls, 42 CPI function controls
(four reproduce the baseline bypass), and seven OAG specification controls.
Counts belong to their stated boundaries and are not pooled with author suites.
No full frontend or hosted Actions suite was rerun; product frontend files did
not change. Actions remains OFF and no paid review was requested.

The OAG author's retained-PDF PostgreSQL replay traversed CLI, fetcher, real
parser, reconciliation, loader and publication gate: five volumes, 47 chapters
each, 3,709 findings. Seven protected synthetic source cohorts retained their
complete fingerprints. A cached repeat created none; two Decimal/float update
counters did not change persisted audit columns. This is local source replay,
not a migrated full production restore or production timing forecast.

## Standards

No documented standards breaches or actionable Fowler smells remained after
the inventory fix. Direct malformed comparisons now refuse; the captured real
PostgreSQL inventory and legitimate overloaded/zero-argument routines,
large-object pages and role memberships pass independent checks.

## Specification

No confirmed local implementation defect or scope expansion remains. Successful
bounded ingestion honestly records no fresh publisher listing. The existing
coverage gate therefore warns that the newest run lacks a valid listing.
Independent controls showed that older qualified listing fallback still detects
missing institutional cells and newly listed missing years. A subsequent genuine
qualified inventory/outcome observation clears the warning; it must not be
fabricated from five successful downloads. This remains #234's live-adoption
requirement, not a gate to suppress or a duplicate issue.

## Issue closure and production boundaries

No whole open issue is fully resolved by this round. #319 still requires actual
publisher/code/CPI/fixture correction and public readback; #273 the actual BROP
publisher correction; #379 actual corrected public audit text; #234 adopted
catch-up/full validation; #231 actual signing, worker generation acknowledgement
and seed-to-render refresh. Code merges alone do not change these stored records.

#450 remains unresolved. The diagnostic session captured two actual stalls,
including a resolved MoneyFlowTab module with no pre-intervention money-flow
request. Four focused browser tests passed, but no causal fix exists. Forced
chunk rejection reaches a generic application error without recoverable retry;
that also falls within the ticket's existing supported-selection criterion.
Successful repetitions do not close it.

Fixture cleanup was rehearsed after local publisher/code/OAG-text/CPI changes;
it did not include the five-volume catch-up's after-state. Recapture actual
post-write context before cleanup. Inverse preserves CPI archival source rows
and consumed sequence values; transaction rollback does not undo allocation.

These merges authorize code only. Live changes still need the exact reviewed
operation, coordinated writers, a consistent full compatible backup/restore,
independently accepted recovery and final owner approval. Source decisions,
competent human Swahili review and final approved hosted checks remain separate.
The protected dirty primary checkout and existing dependency installations are
preserved. Owned coordinator test resources are removed.

## Deployment and rollback

The OAG path is opt-in at the CLI; omit its manifest option to keep ordinary
execution. Local backup acquisition cannot target production. No schema
migration, live correction, secret, cache invalidation or job activation is part
of these commits. Initial release observation is deployment SHA/readiness;
actual data/refresh acceptance belongs to its later approved execution window.
If code rollback is needed, revert the two squash commits in reverse merge order
using `git revert <oag-squash-sha> <recovery-squash-sha>` and the normal deployment
path. No stored state was changed by this code merge to unwind. Separately
executed future operations require their own current guarded inverse.
