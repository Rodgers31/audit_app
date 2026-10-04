# Bounded manual verification during development

Automatic development workflows remain disabled by the owner's direction.
`verification.yml` provides one separately authorized manual verification run.
It uses the seven existing CI job contracts and includes no seeding, production
migration or deployment job. Offline parity controls fail if those contracts
drift from `ci.yml`.

## Before execution

Finish integration and local verification first. The workflow must be reviewed
and present on the default branch before GitHub accepts manual dispatch. Freeze
the complete tested commit SHA and selected dispatch ref. Check current regular
workflow states, dynamic app triggers, account eligibility and all pending or
active runs. Coordinate a short quiet window with other workstreams; do not
assume disabling regular CI excludes app-managed activity.

Enable repository Actions and only this manual verification workflow among
regular YAML workflows. Normal CI, nightly seeding and Docker deployment stay
disabled. Dispatch once with `commit_sha` equal to the immutable approved SHA.
Each test job checks that its real checkout and dispatch SHA match, that the
event is `workflow_dispatch`, and that the run attempt is 1 before installation
or testing. The final gate retains the original required-suite decisions.

The seven configured timeouts sum to 100 runner-minutes. This sum is not a
guaranteed billing limit. No rerun is authorized automatically; any failed run
requires diagnosis before another separately authorized attempt.

## Shutdown and evidence

On success, failure or cancellation, disable repository Actions and this
workflow again. Cancel any unexpected run separately; disabling execution does
not stand in for cancellation. Verify no active or pending jobs before later
pushes or merges. Keep automatic workflows disabled until the owner authorizes
their permanent return after all development workstreams are ready.

Retain run/job IDs, event, attempt, actual checkout SHA, step results, log hashes
and the `browser-original-chromium` and `browser-publication-acceptance`
artifacts before expiry. Measure actual original-suite cases and named skips;
do not replace those receipts with a summary count or local run. A manual run
must be described as manual, not as an executed automatic PR trigger.

Coverage upload remains optional. Preserve its preparation status, raw action
outcome and exact-commit summary. `uploaded_unverified` requires a processed
exact-commit Codecov report before claiming accepted hosted coverage; an
explicit optional disabled/missing-auth/failure result may meet the existing
reporting requirement. The current local coverage step reports a percentage
and does not enforce a numeric minimum.

## Local preparation receipts

- The original write-route scan failed specifically on the signed cache status
  route: 1 failed, 27 passed. The corrected scan and actual refusal/observation
  controls passed 29 cases. This changes the test's signed-route contract, not
  the runtime authorization policy (#480).
- Offline optional-coverage, workflow-parity and real temporary-Git checkout
  guard tests passed 19 cases. Hostile/missing SHAs, mismatched dispatch/checkout,
  automatic events and repeat attempts were refused.
- These are local controls. No hosted execution or issue closure is claimed.
