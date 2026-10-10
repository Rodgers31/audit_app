# Final adversarial verification: archive integrity passes

Executed 136 controls on actual code, with no remaining malformed-input success found. Verifier SHA256: `34beb8a50a24a81acf29fbd640569e8fc7b9ab5d82528709e8e218510b303b48`; unit source `6dc6f96df70c0a81bb4d01e4cfde22ec9cc3005f07e953c4c8048c70b1ecf6de`; publisher `f19563817e100aafbfa3a62eb8832285151a302f1f5ab2ae2024a989cd8688a5`; manifest `51a12f94f2bad7754f294871d9646ac393c4af6ac4f81bf9b4633c14436b7959`. All stayed unchanged during executions. Original and intermediate review directories remain intact.

The exact original 70 attacks and extended 22 attacks ran against fresh isolated copies. Valid baselines verify; all 32 previously confirmed false successes now reject. Coverage includes missing/malformed schemas, empty cases, hostile counters/durations, omitted controls, case substitution, retries, command and source/generator/log contradictions, runtime/instrumentation omission, contradictory statuses, unsupported compression, symlinks and traversal.

The unchanged original harness records one expected-verify mismatch: changing a duration to zero now rejects the frozen raw-input census. This is correct for the known immutable publication, not a claim that zero durations are invalid. The separate actual original parser execution accepts a valid zero duration.

Thirty-eight additional direct controls execute `verifyPackage(root, repo)` and the original `executionPassed(report, cases, exit)` without an archive-checksum gate. Valid baselines pass; null/missing/wrong-type parameters, zero-case/malformed reports, NaN, ±Infinity, negative, boolean, null, string/fraction counters, invalid exits and durations reject. Six fresh publisher controls verify valid publication and rejection of missing required input, inherited outputs, input mutation and producer mutation; mutation publishes no manifest.

Exact calls, harness/source hashes and raw stdout are retained in `attack.mjs`, `extended_attack.mjs`, `direct_controls.mjs`, `publisher_attack.py`, their JSON results and logs in this directory. All mutations used owned disposable copies; real archive/application files were untouched.

Boundary: this certifies integrity of one frozen historical publication, not cryptographic authentication, a general package validator, browser acceptance or causal scroll repair. #601 remains unresolved. Concurrent writers, disk exhaustion, decompression resource limits, browser/database/hosted paths were not executed in this review.
