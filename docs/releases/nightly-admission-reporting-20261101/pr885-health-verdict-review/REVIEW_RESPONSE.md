# PR #885 health-verdict review repair

Classification: **valid**. The [complete review](https://github.com/Rodgers31/audit_app/pull/885#pullrequestreview-5730688325) contains one actionable note: malformed health-check verdicts were interpreted as a partial probe before their validity was checked. The “No open issues” summary does not dismiss that note. The review's hosted-observation limitation remains correct and open; no hosted execution is performed here.

The suggested verdict-before-partial ordering is sound. The adjacent count case requires the same invariant: a missing or malformed `unprobed` output cannot establish that the health-check budget expired. The repair therefore validates both fields before describing a partial/complete probe. The actual producer writes literal `true`/`false` and decimal counter strings. The recorded monitoring contract keeps transport failure, incomplete coverage and unknown state distinct (`docs/operations/2026-09-27-freshness-browser.md`, Monitoring #294). No decision requiring malformed outputs to count as a measured partial result was found.

`healthDescription` now handles outcomes in this order:

1. An unfinished/unknown job result stays unknown.
2. A verdict other than literal string `true` or `false` stays unknown.
3. A known critical-source failure remains a warning, even when the coverage counter is unavailable.
4. A no-critical-failure verdict requires a canonical nonnegative decimal **string**, bounded to the existing five-digit display limit. Missing values, booleans/numbers, leading-zero aliases, negatives, fractional/exponent notation, whitespace and hostile text stay unknown.
5. A positive valid counter describes partial coverage; valid zero preserves the no-critical-failure message.

Both summary and managed incident body call the same function. The actual workflow-selected script is executed by the tests with every GitHub call intercepted. The separate source-outage issue and recovery scripts, planned exclusions, all seven non-notify jobs and accepted-source SHA guard are unchanged.

## Executed receipts

- [Verdict red](red.txt): one selected regression method, **90 failing subtests**, before the repair. Missing/malformed verdicts with nonzero or unavailable counters produced “Partial”.
- [Counter red](red-count.txt): one selected regression method, **43 failing subtests**, before the repair. Invalid or missing counters invented partial coverage.
- [Normal](green.txt): **20 tests passed**, 6.721 seconds.
- [Optimized](green-optimized.txt): **20 tests passed**, 6.729 seconds. This overlaps the normal selection and is not added to it.
- [Existing bounded-health workflow tests](existing-healthcheck.txt): **20 passed**, 17.74 seconds, including real loopback health probes and the existing actual-alert script harness.

The three added regression methods exercise both healthy pipeline summaries and failed-pipeline issue bodies. Existing cases continue to cover early admission rejection, cancellation/unknown results, source-plan/bootstrap/preview exclusions, scheduled/manual paths, API failures and incident deduplication. Unknown health output alone does not invent a new pipeline incident; source transport and job execution keep their existing separate alert scopes.

Commands, with existing Python/Node runtime directories selected through `PATH`:

```sh
python -m unittest discover -s .github/scripts/tests -p test_seed_notifications.py -v
python -O -m unittest discover -s .github/scripts/tests -p test_seed_notifications.py -v
python -m pytest --confcutdir=backend/tests -q backend/tests/test_healthcheck_is_bounded.py
```

The current scoped hashes and equality checks are in [repair-receipt.json](repair-receipt.json). The canonical [verification receipt](../verification.json) now names the repaired helper/tests; its exact prior bytes are preserved in [verification-before-review.json](verification-before-review.json). Original raw red/green/historical cross-lane captures remain unchanged. Independent executable review is complete: media_launch_acceptance ran 481 actual-wrapper/direct-function adversarial cases with zero external calls and no finding. [The independent binding](independent-review.json) hashes the separate reviewer artifacts and the repaired helper. The same probe was replayed here successfully; that replay is not an additional independent count. The reviewer also reproduced the old malformed-output result directly from the actual PR head blob.

No Git/GitHub mutation, hosted run, issue write, source ingestion, production write, upload, worker activation, financial generation or paid service was invoked by this repair lane.
