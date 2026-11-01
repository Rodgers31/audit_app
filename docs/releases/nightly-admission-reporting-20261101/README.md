# Nightly admission reporting — local verification, 2026-11-01

The finding is valid: run `41268107359` rejected its unaccepted source revision in `migrate`; the original notification job did not depend on admission and its alert condition selected only seed/validation/page-refresh failures. Its dependent jobs were skipped and no pipeline alert ran. The accepted-source SHA refusal is correct and unchanged.

## Scope and behavior

Only notification wiring, its new reporting helper, its executable fixtures and the existing health-message fixture adapter change. The summary includes database admission and an interpreted table for every critical job. Failed, cancelled, missing/unknown and unexpected skipped jobs produce an incomplete outcome, set the notification step failed and create or update a managed pipeline incident.

The classifier follows the actual dependency behavior:

- Source plan and health check execute independently. Health transport warnings retain their separate issue/recovery handling; a health job that fails to execute is an incomplete pipeline outcome.
- Admission depends on source plan; seeding depends on admission.
- Bootstrap depends on admission and seeding, and an explicit `bootstrap=false` plan makes its skip intentional.
- Validation uses `!cancelled()` and admission success. A seeding failure does **not** excuse a missing validation. A manual validation opt-out does.
- Page refresh requires successful seed and validation; dry run or validation opt-out intentionally excludes it. Other dependency skips remain visible as blocked, not successful.
- Disabled scheduled ingestion intentionally skips the notification job. Manual dispatch still reports while nightly ingestion is off.

The final reporting step uses `always()` so an earlier source-issue API failure cannot silently suppress pipeline assessment. Source warning wording now says probes run independently of admission instead of claiming seeding ran.

Pipeline incidents carry a managed marker. At most one managed open incident is updated once per run attempt; replaying the same run attempt makes no extra issue or comment. Unmanaged incidents and pull requests are untouched. A full 100-item lookup page or multiple managed incidents fails visibly rather than guessing and creating duplicates. Pipeline success does not auto-close incidents. The existing separate source-health issue lookup/comment/recovery logic is preserved.

## Executed evidence

- [red.txt](red.txt): exact admission regression against the original main workflow — one assertion failure, `[]` intercepted calls where alert lookup/create were required. [red-initial-matrix.txt](red-initial-matrix.txt) preserves the first broader reproduction before the helper existed.
- [green.txt](green.txt) and [green-optimized.txt](green-optimized.txt): the actual YAML job/step conditions and github-script execute through an offline GitHub fake; 17 tests pass independently in normal and Python `-O` modes. Cases include admission/source-plan/health/bootstrap failures, every critical job's cancelled/missing/unknown/skipped states, intentional exclusions, schedule/manual gating, null scheduled inputs, malformed input, partial/unknown source health, issue deduplication and bounded API failures. These runs overlap and are not additive.
- [focused.txt](focused.txt): existing health-check, inline workflow scripts, bootstrap wrapper and actual admission-shell tests — `320 passed, 6 skipped in 22.80s`. The six existing skips are shell scripts containing GitHub expressions that are substituted by Actions before execution.
- [summary-compatibility.txt](summary-compatibility.txt): existing selection summary cases — `5 passed, 23 deselected in 6.68s`. The first collection attempt lacked the test namespace on `PYTHONPATH`; its [setup failure](summary-compatibility-setup-failure.txt) is retained separately.
- [early-rejection-observation.json](early-rejection-observation.json): generated summary, failed-step status and intercepted issue payload for the admission-rejection case.
- [verification.json](verification.json): source hashes, runtime identities and equality checks proving all seven non-notify jobs, all top-level workflow configuration and the actual admission shell remain unchanged from main `db713b72ccd4c1938e7dac0401f66770379bdb62`.

The new fixture is part of the existing CI/verification workflow-boundary unittest discovery under `.github/scripts/tests`. The primary local commands were:

```sh
python -m unittest discover -s .github/scripts/tests -p test_seed_notifications.py -v
python -O -m unittest discover -s .github/scripts/tests -p test_seed_notifications.py -v
python -m pytest --confcutdir=backend/tests -q backend/tests/test_healthcheck_is_bounded.py backend/tests/test_workflow_inline_scripts.py backend/tests/test_bootstrap_workflow_outcomes.py tests/github_database_qualification/test_workflow.py
PYTHONPATH=backend/tests:backend python -m pytest --confcutdir=backend/tests -q backend/tests/b66_sources/test_review_round.py -k summary
```

Python 3.13.9 and Node 24.22.1 final results are identified in the receipt. Red replay used `SEED_NOTIFICATION_WORKFLOW=/tmp/nightly-admission-pre-fix-seed-20261101.yml` with the original workflow copied outside the checkout. The earlier system Python environment lacked FastAPI; the provided audited backend entrypoint referenced an absent interpreter, so no dependency installation was attempted and the final pure-workflow selections used an existing local backend environment.

## Limits and pending observation

No hosted workflow, issue API, database write, upload, activation, worker, publication, financial generation or paid service was invoked. Fixtures intercept every GitHub call. Actual hosted issue delivery remains unverified until a separately authorized execution. This job cannot cover a zero-job run, failure before the notification runner starts, failed notification checkout, or cancellation that prevents notification scheduling. `always()` does not guarantee execution after cancellation. Job outcomes do not independently certify extraction, content, freshness or publication.
