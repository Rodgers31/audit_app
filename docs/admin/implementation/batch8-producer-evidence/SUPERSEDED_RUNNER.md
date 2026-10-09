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
