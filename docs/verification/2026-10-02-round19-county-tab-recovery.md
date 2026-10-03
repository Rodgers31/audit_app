# County tab code-load recovery — Round19

The county page now retains its header, navigation and sources when a selected
tab's JavaScript chunk rejects. The content area explains the failure and offers
**Reload section**. All five lazy tabs share the boundary; changing tabs resets
only its error state. Existing data-read failures retain their separate handling.

React caches the lazy loader's rejected Promise, so resetting the boundary alone
cannot retry the chunk. Recovery reloads the document when the URL already names
the selected tab. If the selection's router replacement is still pending,
recovery replaces the URL with that selection while retaining the fiscal year,
other parameters and anchor. Neither operation adds a history entry.

An independent browser probe caught a defect in the first implementation:
replacing an identical URL containing a hash could perform a same-document
navigation and retain the rejected Promise. Both mobile and desktop regressions
reproduced the missing second chunk request. The explicit reload branch fixes
that case, including the default Overview URL.

## Executed verification

Assigned checkout: `/Users/roger/.codex/worktrees/round19-county-loading/audit_app`,
branch `codex/round19-county-loading`, base
`4645d0ed602c70c906a42627193f4d2c78fa002f` /
`a5030e9b1eacfdc0770bee6a05ff67b4082eb3f9`. No primary checkout edits.

- Baseline: two browser regressions reject the actual compiled MoneyFlowTab
  chunk, then fail because the page has only a generic application error.
- First patch: six focused browser tests pass, but the two added deep-link
  anchor cases fail at the missing second chunk request. These failures remain
  recorded; the first patch is not presented as the final result.
- Final patch: eight focused browser tests pass, no skips/retries/flaky results.
  Four cover shell selection and anchored deep links at 375/1280px, two rejected
  chunk requests, and successful fresh delivery. They require a consumed money
  request, FY2024/25, KES 8.00B synthetic allocation, the synthetic source link,
  visible committed-amount note, keyboard activation, retained history and no
  horizontal overflow. Four existing tests cover source/amount notes, fiscal-year
  switching and tab reload/history.
- Two focused component suites: 21 tests pass. Production Next build, including
  lint/type checks, passes. `git diff --check` passes.

These are local compiled-browser and synthetic API contracts, not production
data acceptance. Existing Node 22.19.0, Next 15.5.20 and Python 3.13.9 dependencies
were reused without updates. Next's browser renderer remains its vendored
19.2.0-canary-0bdb9206-20250818; the installed app React package is 19.2.4.
The API uses disposable SQLite, an inert lifespan, disabled environment-file
loaders/seeder/warmup, blocked external HTTP and process-local memory cache.
Actions remains OFF. No provider, production, GitHub or deployment write occurs.

## Separate intermittent stall remains open

This patch fixes rejected-chunk recovery. It does **not** fix the resolved-module,
no-request stall in #450. A fresh valid baseline capture after 73 healthy
observations directly awaited the recorded converted native Promise: its value
strictly equalled the actual MoneyFlowTab export and associated lazy payload.
Chunk and money-RSC transport returned 200, with no pre-intervention money API
request or page exception. The selected content assertion still failed after
10 seconds. The frozen root had pending 549505024, suspended/warm 12634112,
pinged 0, entangled 51200 and callback priority 0.

The minimal diagnostic observer records attach-ping/ping/mark-suspended ordering,
navigation events and store updates. One navigation wakeable pinged during a
51200-lane render, followed by suspension with no retained ping or scheduled
callback. This is evidence of the failed schedule, not an identified causal
product mechanism or justification for a private-renderer patch.

Eighteen controls gate the actual fiscal-year/accountability listener callbacks
before selection, after dispatch, or after module resolution; all reach data.
Two further observer batches (100 and 150 healthy observations) do not encounter
a failure, so a correctly targeted generic React state-update intervention is
still untested. The valid failed capture's earlier generic intervention used the
wrong locator and never clicked; its later history intervention does have a
visible-content assertion and a separately recorded consumed money request.
No history workaround is shipped.

An initial observer variant also threw an instrumentation-only error by requiring
the money module before registration. Its 68 healthy observations and one stall
are retained separately and excluded from the clean diagnostic counts. Private
observers can change timing. Repeated healthy observations do not establish race
absence, prevalence or production parity. No timeout increase, eager loading,
quarantine or dependency upgrade is used.

Durable source hashes, commands, baseline/final traces, independent verification,
limits and owned-resource cleanup are in `ROUND19_SESSION_4_HANDOFF.md/json` and
the associated receipts in the Round19 evidence bank. #450 remains OPEN until
both relevant signatures meet its supported-selection contract. New Swahili
keys `county.tab.load_error` and `county.tab.reload` are draft runtime copy;
competent human language acceptance remains within #307/#372.
