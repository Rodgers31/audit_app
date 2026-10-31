# Replay the independent review

Use an isolated copy of this directory. The `versions` directory archives the alias fixture manifest/lock as `.json.txt` research inputs. In the isolated copy only, restore their `package.json` and `package-lock.json` names before installation. Keeping these archival names in the repository prevents dependency discovery from treating intentionally vulnerable historical fixtures as application manifests. Install there, never in the candidate checkout. Dependency installation may contact the public npm registry. The candidate's installed dependencies are consumed read-only.

Set `SPEC_NODE` to the verified Node 24.22.1 executable and `SPEC_SOURCE_ROOT` to the candidate checkout root. The run scripts default to the exact original review paths. Use the corresponding npm executable with that Node on PATH for `npm ci --ignore-scripts --no-fund` in `versions` only. That fixture install is not the application's audit result.

From the review directory run:

```sh
python3 run-version-matrix.py
python3 run-candidate-controls.py
python3 run-other-pattern.py
python3 collect-binding.py
```

`run-version-matrix.py` runs 50 bounded, separate Node children; each records its exact argv, implementation hash, row counts, phase observations, exit, stdout/stderr and duration. All must exit normally. The independent cross-version table is interpreted in REPORT.md.

`run-candidate-controls.py` runs the actual 74 permanent tests, installed source check, deliberate minimatch RED, real legacy callers, two portable applicability tests, the direct exclusion RED/GREEN, the legacy major-API incompatibility control and the deepmerge/installer adversarial harness. It requires the minimatch RED's precise assertion and interception diagnostic. Every other command must exit zero. Mutation fixtures stay under this directory's runs folder and are removed after execution. No candidate package is edited. It uses 45-second wall/30-second CPU limits; the application and worker are never started.

`run-other-pattern.py` is a separate diagnostic, not a passing security gate. It permits only n=4/8/12 and uses a 750 ms wall limit, one-second CPU limit and 64 MB V8 heap. The recorded 3.1.5 n=12 timeout means the child was killed after reaching matching; it does not establish an infinite hang. The 11.0.3 measurements are controls for that exact finite input.

`collect-binding.py` captures actual candidate, lock and installed implementation identities. The version fixture lock preserves registry integrity values. `artifact-hashes.json` binds the curated review output. Files with `setup-failed` or `guard-transition-red` names in the original evidence directory are diagnostic development history, not accepted controls; they are excluded from the portable review package.

Publication packaging: the author renamed only the archived fixture manifests and updated these replay instructions; the independent report, receipts, candidate bindings and executable harnesses are copied unchanged. Downloaded upstream source snapshots remain in the original external evidence directory; the report links their primary sources.
