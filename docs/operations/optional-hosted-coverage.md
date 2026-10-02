# Optional backend hosted coverage

Backend tests and local coverage remain independent of Codecov. The existing
local test/coverage commands and their enforcement are unchanged. The separate
`docker-build-deploy.yml` test command retains `--cov-fail-under=50`.

The CI workflow retains the optional Codecov integration. An unset
`CODECOV_UPLOAD_ENABLED` repository variable means enabled; `false` deliberately
skips it. Any other value except `true` warns and refuses the attempt. Enabling
the workflow itself remains a separate owner action.

Uploads require a nonempty `backend/coverage.xml` and an available
`CODECOV_TOKEN` Actions secret. The workflow references that conventional name;
it does not assume a secret exists, create one, or print its value. Missing
credentials (including fork/Dependabot runs without secret access) are reported
as `missing_auth` and not attempted. Tokenless eligibility and OIDC are not
assumed. If the owner chooses publishing, they must separately approve and
configure supported repository authentication. If the owner chooses permanent
removal, remove the integration through an explicit policy change.

The action uses `fail_ci_if_error: true`, with step-level `continue-on-error:
true` to preserve optionality. The final reporter reads the step's **outcome**,
which retains the failure before GitHub changes the tolerated step's
**conclusion** to success. Failure, missing inputs and unknown completion emit
warnings and a job summary. An intentionally disabled upload has a visible
summary. A successful action is reported as `uploaded_unverified`, with a
warning and exact commit link. No script output certifies hosted acceptance.

| Result | Meaning |
| --- | --- |
| `disabled` | Explicitly disabled, zero upload attempts |
| `missing_auth` / `missing_coverage` / `invalid_configuration` | Prerequisites absent/invalid, zero attempts |
| `not_attempted` | Upload step skipped, zero completed attempts |
| `upload_failed` | Action ran and rejected/failed; inspect its log |
| `upload_unknown` | Action completion is unknown, attempt count unknown |
| `uploaded_unverified` | Action exited successfully; hosted processing/acceptance unverified |
| Verified hosted report | Requires separate provider readback for the exact SHA; never inferred from action exit |

After owner approval for the final CI batch, retain the real workflow run URL,
raw upload step outcome, warning/job summary and local test/coverage outcomes.
If publishing is configured, inspect the linked Codecov commit report and
record an actual processed report for the exact coverage SHA (PR head SHA on
pull requests, `github.sha` on pushes). A queue acknowledgment or successful
action alone is insufficient. If upload remains optional and cannot run or
fails, retain the explicit optional result from that real run. Either verified
hosted reporting or an accurately reported optional failure can satisfy #343's
original CI acceptance; local fixtures alone cannot.

Offline controls:

```sh
python -m unittest discover -s .github/scripts/tests -p test_coverage_upload.py -v
```

These controls require PyYAML (already in backend development dependencies).
They do not import the application, load dotenv, contact Codecov, or run Actions.

Supported inputs were checked against the official
[v5 action definition](https://github.com/codecov/codecov-action/blob/v5/action.yml)
and [authentication documentation](https://docs.codecov.com/docs/codecov-tokens).
