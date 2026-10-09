The first two receipts (`baseline-critical-lint.json` and
`baseline-regression.json`) were generated with runner SHA256
`43a1342960db0a8ae3660f9f86ff0bc4595da23bd914a9d74dd99fe68a3315d6`.
The runner was then changed from in-memory SQLite to a file under the owned
output directory, because application database import rejects SQLite's memory
pool with the configured pool options. An unused import was also removed.
These receipts remain historical evidence of the observed lint failure and
collection failure; they are superseded as evidence of current harness
execution by `baseline-critical-lint-v2.json` and `baseline-regression-v2.json`.
No producer code changed between these runs. No runtime assertion ran in the
first collection failure. Subsequent receipts bind their current runner bytes.

## Coordinator review: create SQLite's parent before the child starts

PR #578 comment 4232125457 identified that the file-backed runner created its
output directory only after the child completed. The coordinator's fresh-path
regression executed the real application SQLAlchemy engine and failed with
`sqlite3.OperationalError: unable to open database file`. Moving the existing
directory creation before `subprocess.run` made that same regression pass and
preserved the committed SQLite row plus its passing read-back receipt.

The following receipts retain runner SHA256
`b1b95496b933a5d4fff17d72b76214ef64ad1408b9415a8213f33b0498b597b8`:

- `baseline-critical-lint-v2.json`
- `baseline-regression-v2.json`
- `baseline-regression-v3.json`
- `delivery-critical-lint.json`
- `delivery-suite.json`
- `evidence-provenance-check.json`
- `final-critical-lint.json`
- `final-regression.json`
- `receipt-regressions-v2.json`
- `receipt-regressions.json`
- `runtime-versions.json`
- `workflow-pin-control.json`

They are historical observations with their original source, command, exit and
generator identities intact. They are superseded as claims about the current
runner, whose ordering repair does not modify the producer or its capture
fixture. Coordinator receipts with new labels bind the revised runner bytes;
the fresh-directory regression is `backend/tests/test_r2_producer_runner.py`.
