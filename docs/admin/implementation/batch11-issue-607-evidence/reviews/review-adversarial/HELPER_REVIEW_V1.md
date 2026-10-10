# Independent adversarial helper review

Status: helper guards pass on the exact hashes below. The final published packet has not been executed by this reviewer. This document does not approve the product, hosted browser acceptance, or production.

Tested verifier: `13af0a0087e632bd88f622990cdaea4519d5a8607bdce719d7f22eab35511ef7`.

Tested replay helper: `be16b7b91f6578457b2fec44295c8d6ed77286adba2d1d5bf09315d3755e3f95`.

The independent reviewer executed 101 verifier/parser/corpus controls and 63 path/parser/replay controls using host Python 3.9.6. Valid controlled fixtures succeeded; all hostile inputs in the latest matrices rejected. The verifier corpus uses a controlled Git inventory; replay guards use controlled Docker metadata and child execution. No browser, Docker container, database, app chat, or provider was accessed.

Executed targets included direct `cases()`, `verify()`, `relative_file()`, `load()`, and `execute()` calls plus verifier CLI output guards. Inputs covered missing/empty/malformed files and schemas, duplicate JSON keys and case/run IDs, bools where numbers are required, NaN/infinity/negative durations and counters, retries, hidden errors, omitted and same-count substituted reports, outside/symlinked inputs and outputs, unsupported replay modes/cohorts, failed children, declared source/helper drift, and source inventory omissions.

The author reproduced and repaired the findings reported by this reviewer:

- Report-level invalid durations were accepted by `cases()`.
- Historical-red could contain only passed cases and could reuse a green report.
- A declared helper drift could be accepted for red or diagnostic-positive receipts.
- A focused run could contain only skips or six unrelated passing cases.
- Diagnostic-positive could contain a failure or have no executed pass.
- Replay accepted truthy non-boolean `State.Running` and a boolean child exit code under controlled dependency inputs.

The latest independent executions are preserved in `attack-v5-20261010T101222/results.json` and `guards-v3-20261010T101223/results.json`, with immutable producer scripts `run_hostile_v5.py` and `run_guards_v3.py` and raw stdout/stderr logs. Earlier scripts, verifier snapshots, and results remain preserved. `review-executions-v1.json`, `v2.json`, and `v3.json` bind commands, observed process exits, producer hashes, and log/result hashes.

Scope limit: these synthetic controls establish guard behavior, not the authenticity of a browser run. The final corpus must be checked using actual Git and published artifact paths, without the controlled Git dependency. `run_final_packet_v1.py` is prepared for that check and has not yet been executed.
