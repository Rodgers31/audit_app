# Nightly refresh investigation — 4 November 2026

Investigation of the latest ordinary run, not a new production acceptance.
No workflow dispatch, production data change, source admission, control change,
paid check or new resource was used. Publishing, uploads, workers and financial
draft generation remain outside this work.

## What failed

[Run 41759203897](https://github.com/Rodgers31/audit_app/actions/runs/41759203897)
used admitted revision `e94eb980190f6074dcfc0f8ec6f9317fc74cfba0`. It started
3 November at 8:12 p.m. CST and ended at 8:45 p.m. CST (4 November 02:12–02:45 UTC).
All 15 planned domains executed; the CLI succeeded, and stored-row integrity
validation passed. The terminal **Check ingestion job results** step refused
incomplete required fiscal and audit coverage.

- Pending bills job 3643: 48 accepted updates (2 national, 46 county), LIVE and
  complete. Main Treasury/BROP transport recovered; no 47th county was invented.
- Fiscal job 3641: 5 accepted fiscal-year updates. Required FY 2022/23 revenue and
  tax/non-tax coverage remains unconfirmed. Two historical links on
  `oldsite.treasury.go.ke` fail hostname verification. This does not establish
  that no qualifying official alternate exists.
- Audits job 3645: 8,105 processed, 4 updated, 10 accepted document inventories.
  National document 2392 is held for reconciliation (335 proposed retirements,
  2 revisions). Independent retained-PDF content review found parent/text losses;
  reproducing the old candidate count does not qualify that proposal.
- Audit retention: 32 observed, 22 retained, 10 missing. This aggregate does not
  identify the ten documents/events or prove an object-store outage. Conditional
  PUT 412 responses can be successful idempotent inserts followed by readback.
- Cache/page revalidation skipped because it requires whole seed-job success.
  Committed DB updates therefore have no explicit page-refresh receipt here.

The red summary deliberately propagated incomplete prerequisites. The managed
issue updater successfully updated [incident #888](https://github.com/Rodgers31/audit_app/issues/888);
its observation marker is `41759203897:1`. The Octokit deprecation warning was
not an issue-creation failure.

## Why manual runs sometimes looked better

Controlled same-revision comparisons disprove a schedule-only failure:

| Same revision | Manual run | Scheduled run | First material difference |
| --- | --- | --- | --- |
| `11524cc1` | [40615663633](https://github.com/Rodgers31/audit_app/actions/runs/40615663633), green | [40619863092](https://github.com/Rodgers31/audit_app/actions/runs/40619863092), failed | Manual selected revenue only; schedule selected 15 domains. Both had 1,320 seconds; full plan exhausted it in fiscal. |
| `e1a0d6be` | [41112967504](https://github.com/Rodgers31/audit_app/actions/runs/41112967504) and [41114893739](https://github.com/Rodgers31/audit_app/actions/runs/41114893739), pending-only green | [41158948256](https://github.com/Rodgers31/audit_app/actions/runs/41158948256), full 15 green | Current 2,400-second budget was sufficient in this instance. |

A green [manual audits run 41312227919](https://github.com/Rodgers31/audit_app/actions/runs/41312227919)
still had 8 acquisition/discovery errors and 10 unconfirmed captures; national
PDF 2392 returned HTML and was not parsed. A later
[manual source check 41325028482](https://github.com/Rodgers31/audit_app/actions/runs/41325028482)
also failed. Manual invocation does not repair publisher responses.

Older workflows accepted `completed_with_errors` without today's required-source
completion check. That hard gate was introduced by `c380093` and refined by
`7ffd536` on 3 November. Green badges, stored-row integrity, isolated parser tests
and a complete fresh-source night are different claims. Past narrow/older-policy
proofs were insufficient to claim full nightly recovery.

The daily cron is `0 2 * * 1-6`; after daylight saving ended this is 8 p.m.
Chicago, not 9 p.m. Weekly bootstrap uses03:00 UTC Sunday. Queue delay is separate.
No cron change is made by this investigation.

## Durable repair and acceptance requirements

This review round adds bounded phase/reason counters for retained-PDF restoration
and its local-byte fallback, plus validated nightly log output. The existing
missing counts and native-authority refusals remain unchanged. The public admin
API keeps its six-field retention contract; detailed diagnostics remain internal
job metadata and validated runner output. No historical event mapping is invented.
These diagnostics do not repair the remaining official-source or cache gaps below.

1. Repair OAG structural-heading/text-order and clean-statement extraction using
   the exact retained 915-page PDF. Reconcile all parent/list changes and generate
   a new complete candidate/proposal. Obtain independent content review and exact
   source-adoption approval; the current 335/2 proposal stays refused.
2. Acquire a TLS-valid official historical Treasury edition or qualifying
   alternate, verify FY/measure/units and exact bytes, and establish whether the
   missing FY 2022/23 split is published. Never disable TLS validation, invent a
   zero or relax required coverage to obtain green. Any inherently unavailable
   component needs an explicit versioned coverage decision.
3. Add phase/reason retention diagnostics while preserving existing missing-byte
   and source-authority refusal semantics. Retained-source restoration can raise
   ValueError and trigger a successful local-byte fallback; those are distinct
   outcomes. Existing aggregates cannot retrospectively identify all ten events.
4. Separate safe cache eligibility from required-source completion. Only permit
   independent refresh after admitted code/schema, actual successful CLI, exact
   current job inventory, no failed/running/missing/hollow work, successful DB
   validation and selected bootstrap, non-dry plan and no cancellation. Keep the
   overall run red for required incomplete sources. Never use `always()` alone
   or blanket `continue-on-error`. Exercise the actual workflow/HTTP/HMAC path.
5. Repair the known ordinary CLI None/empty-result false-completion seam with
   actual API/PG/adapter/CLI/finish tests, preserving legitimate OAG discovery-only
   dry runs and positive unchanged inventories. This was not the cause of the
   latest run, whose domains executed real work.
6. Record a comparable full 15-domain run on the reviewed/admitted release, then
   observe an actual ordinary scheduled run with required source completion,
   retained evidence, DB validation and explicit cache/page outcome. A narrow
   manual run cannot stand in for either receipt.

This is a combination of historical budget/scope differences, honest stricter
completion and unresolved source/content work. Repeated retries will not make
these gaps reliably disappear. No complete-nightly or launch-readiness claim is
made until the final receipts exist.
