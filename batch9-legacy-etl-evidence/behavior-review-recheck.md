# Independent final recheck after refusal-observation storage repair

This recheck supersedes the **latest-candidate applicability** of `behavior-review.md` and `behavior-review-final-acceptance.json`, whose executions remain valid historical evidence for writer source hash `c66e04d352a5782db434bbf508116d144a18af9d3afc93860039e9e194539054`. Those receipts, generators and logs were preserved without modification. Dependency HEAD remains `9e97ca3f1ca43f103a8655447a86d889456a218a`; executions include the uncommitted author candidate and are bound to exact source hashes.

Final recheck writer SHA-256: `27c7b20eac3229118685cb278a9473ab1d843fad1c0350cc8fcb7879993b94e8`. Pipeline remains `36e0f2fd9db7d080180745ae976d846933e0f54e4c1c69228599a4211eb77401`.

## Narrow review conclusion

The new nested `except SQLAlchemyError` catches failure while persisting the optional FAILED refusal observation, emits a bounded diagnostic, closes the partial execution set, and rethrows the original `DomainOwnershipError`. This preserves the refusal category that real pipeline callers propagate. It does not manufacture a return receipt or a financial success. The author preserved a measured pre-fix control in `refusal-storage-red.json`; that author receipt reports the escaped `OperationalError`, effect0 and retained1. This reviewer did not rerun that historical version and makes no independent-red claim for that new defect.

Independent `behavior_review_refusal_storage_v1.py` injected an actual SQLAlchemy `OperationalError` at the `before_cursor_execute` event for refusal-observation INSERTs. It exercised actual `DatabaseLoader.ensure_country_exists()` and actual `KenyaDataPipeline` download/full pipeline code with inert HTTP/parser inputs, plus the actual `ETLMonitor`. Both minimum and current runtime executions preserve the original refusal diagnostic `Domain ownership unavailable; reconcile retained execution`, keep monitor `success=False`, leave countries/documents/audits at zero, retain the preexisting native claim, and write no fabricated ingestion jobs. New receipts: `behavior-review-recheck-refusal-storage-minimum.json` / `behavior-review-recheck-refusal-storage-current.json`.

Same immutable v4 generator replays (`behavior-review-recheck-minimum.json` / `behavior-review-recheck-current.json`) confirm raw connection/task/thread refusal, normal success and subsequent run, uncertain Session.begin commit retention, interruption retention, missing/unsupported storage refusal, optional-loader failure propagation and missing dispatch seam failure propagation. Same immutable cancellation and dynamic-routing generators also replay with NEW recheck receipts on both runtimes. None of these controls accessed PostgreSQL or a live provider/storage service.

`behavior_review_acceptance_v2.py` reads back eight new execution receipts, verifies each source is stable across execution and still matches the current product bytes, verifies generator hashes, and asserts the observed outcomes. Output: `PASSED: eight recheck execution receipts; zero failures/skips; source and generator hashes verified.` These are eight evidence documents, not eight pytest tests. V2 is a new assessment tool that adds recheck paths and the refusal-storage expectations; V1 and its earlier assessment remain unchanged.

No unresolved finding remains within these executed independent SQLite controls. PostgreSQL connection-death/process races, CI, operational quiescence and deployed acceptance are distinct author/coordinator gates.

## Exact commands

From `/Users/roger/.codex/worktrees/af79/audit_app`:

```sh
PYTHONPATH=backend:. PYTHON_DOTENV_DISABLED=1 .local-dev/sa2023/bin/python batch9-legacy-etl-evidence/behavior_review_controls_v4.py batch9-legacy-etl-evidence/behavior-review-recheck-minimum.json > batch9-legacy-etl-evidence/behavior-review-recheck-minimum.txt 2>&1
PYTHONPATH=backend:. PYTHON_DOTENV_DISABLED=1 .local-dev/behavior-current/bin/python batch9-legacy-etl-evidence/behavior_review_controls_v4.py batch9-legacy-etl-evidence/behavior-review-recheck-current.json > batch9-legacy-etl-evidence/behavior-review-recheck-current.txt 2>&1
PYTHONPATH=backend:. PYTHON_DOTENV_DISABLED=1 .local-dev/sa2023/bin/python batch9-legacy-etl-evidence/behavior_review_cancellation_v1.py batch9-legacy-etl-evidence/behavior-review-recheck-cancellation-minimum.json > batch9-legacy-etl-evidence/behavior-review-recheck-cancellation-minimum.txt 2>&1
PYTHONPATH=backend:. PYTHON_DOTENV_DISABLED=1 .local-dev/behavior-current/bin/python batch9-legacy-etl-evidence/behavior_review_cancellation_v1.py batch9-legacy-etl-evidence/behavior-review-recheck-cancellation-current.json > batch9-legacy-etl-evidence/behavior-review-recheck-cancellation-current.txt 2>&1
PYTHONPATH=backend:. PYTHON_DOTENV_DISABLED=1 .local-dev/sa2023/bin/python batch9-legacy-etl-evidence/behavior_review_dynamic_binds_v1.py batch9-legacy-etl-evidence/behavior-review-recheck-dynamic-binds-minimum.json > batch9-legacy-etl-evidence/behavior-review-recheck-dynamic-binds-minimum.txt 2>&1
PYTHONPATH=backend:. PYTHON_DOTENV_DISABLED=1 .local-dev/behavior-current/bin/python batch9-legacy-etl-evidence/behavior_review_dynamic_binds_v1.py batch9-legacy-etl-evidence/behavior-review-recheck-dynamic-binds-current.json > batch9-legacy-etl-evidence/behavior-review-recheck-dynamic-binds-current.txt 2>&1
PYTHONPATH=backend:. PYTHON_DOTENV_DISABLED=1 .local-dev/sa2023/bin/python batch9-legacy-etl-evidence/behavior_review_refusal_storage_v1.py batch9-legacy-etl-evidence/behavior-review-recheck-refusal-storage-minimum.json > batch9-legacy-etl-evidence/behavior-review-recheck-refusal-storage-minimum.txt 2>&1
PYTHONPATH=backend:. PYTHON_DOTENV_DISABLED=1 .local-dev/behavior-current/bin/python batch9-legacy-etl-evidence/behavior_review_refusal_storage_v1.py batch9-legacy-etl-evidence/behavior-review-recheck-refusal-storage-current.json > batch9-legacy-etl-evidence/behavior-review-recheck-refusal-storage-current.txt 2>&1
.local-dev/sa2023/bin/python batch9-legacy-etl-evidence/behavior_review_acceptance_v2.py > batch9-legacy-etl-evidence/behavior-review-recheck-acceptance.txt 2>&1
```

Minimum runtime: owned Python 3.12.14 / SQLAlchemy 2.0.23. Current runtime: reviewer-owned Python 3.13.9 / SQLAlchemy 2.0.46, described in the original review. All reviewer databases were owned temporary SQLite files and deleted; engines were disposed, socket transports blocked, no owned process/service remains. No setup errors or skips occurred in this recheck.
