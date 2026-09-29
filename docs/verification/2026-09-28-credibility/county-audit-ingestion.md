# County audit ingestion scheduling — 28 September 2026

Issues [#347](https://github.com/Rodgers31/audit_app/issues/347) and [#234](https://github.com/Rodgers31/audit_app/issues/234). Base `a7faedb509b63e8ac68557bf90456cb6f2828629`; implementation commits `bf2fdaaf8b1b096f246336bb480f865719418de2` and `31df8182c1c8e44af24615ce0fd551b9516782c8` on `codex/county-audit-ingestion-progress`. This receipt covers synthetic scheduling corrections, not source acceptance or production ingestion.

## Defect and red fixture

The [28 September nightly](https://github.com/Rodgers31/audit_app/actions/runs/36370404355) logged document 2392's national reconciliation refusal from 02:37:08 to 02:38:52 UTC (about 104 seconds). FY2020/21 documents 2395 and 2396 then failed their unreadable-text guards after about 107 and 77 seconds. At 02:42:20, the run reported eight newer county volumes discovered, zero processed, all eight deferred under the 240-second start budget. The 335 proposed retirements and two revisions for document 2392 were refused; this change does not approve them. See `/tmp/audit-nightly-36370404355-failures.log` lines 648–675 in the coordinator's cached log and `backend/seeding/domains/audits/__init__.py` before this commit.

`backend/tests/test_audits_domain_county_ingest.py:274` forces that interleaving with a synthetic 100-second national refusal, two 90-second legacy refusals, and 100-second newer volume work. It uses no external network or production data. Run against the unmodified base with this test added:

```text
pytest tests/test_audits_domain_county_ingest.py::test_slow_refused_national_and_legacy_books_cannot_starve_current_volumes -q
FAILED: assert [] == ['2024/2025 executives', '2024/2025 assemblies']
1 failed
```

The failure was the observable zero-volume outcome, not a test of implementation structure.

## Correction and green evidence

- `backend/seeding/domains/audits/__init__.py:290` runs newer combined county volumes first, then gives national and older county reports one shared attempt-ordered queue. A slow or refused earlier source cannot consume the window before a newer volume starts.
- `backend/seeding/domains/audits/__init__.py:93` gives known URL candidates a stable order; `:123` sorts remaining national and legacy work by the oldest recorded attempt, with a stable tie-break. `:151` records a scheduled turn before slow work on a registered document and preserves its existing metadata; malformed metadata is refused. This prevents a repeatedly slow national report from indefinitely hiding the legacy reports, and vice versa.
- `backend/seeding/domains/audits/__init__.py:389` avoids starting national discovery after the cutoff. `:436` names every volume, known national document and older county document deferred under the same start window in `county_volumes`, `deferred_documents` or `deferred_discovery`. A current volume is also deferred once the cutoff is reached, so its cache/network read cannot quietly extend the queue.
- `backend/seeding/domains/audits/__init__.py:520` commits failed extraction-attempt metadata after the source transaction refuses the candidate. This preserves the refusal and retry order if a later item reaches the CLI's hard domain timeout. The extraction and publication gates are untouched.

Focused checks ran from `backend` with `PYTHON_DOTENV_DISABLED=1`, an explicit loopback-only local `DATABASE_URL`, empty `REDIS_URL`, `TESTING=true`, `AUTO_SEEDER_ENABLED=false`, and `AUTO_WARMUP_ENABLED=false`. The fixtures create in-memory SQLite tables; no PostgreSQL-specific behavior was asserted and no production database was used.

| Check | Result |
|---|---:|
| Scheduling, coverage, review regressions, candidate filter and CLI budget (`test_audits_domain_county_ingest.py`, `test_county_audit_coverage_gate.py`, `test_county_coverage_adversarial.py`, `test_oag_review_regressions.py`, `test_audit_candidate_filter.py`, `test_seeding_cli_budget.py`) | 149 passed |
| Volume parser, old county parser, recovery and publication gate (`test_oag_county_volume.py`, `test_oag_county_audit.py`, `test_extraction_recovery.py`, `test_audits_publication_gate.py`) | 104 passed |
| Combined focused suite after shared-queue follow-up (all ten files above) | 257 passed |
| `flake8` critical errors on the changed Python files; `git diff --check` | 0 errors |

The first fixture yields two newer volumes on run one, two on run two, and four `already_current` outcomes on runs three and four. The shared queue attempts the national report and one legacy report on run three; the other legacy report receives the first turn on run four. Refused older documents remain errors. The zero-budget control defers even current volumes before any PDF fetch. All of these are synthetic behavior checks, not a live OAG replay.

## Follow-up fairness regression

Coordinator review found that the first implementation still let a 200-second national retry consume a 150-second start window on every run after the county volumes were current. The new fixture at `backend/tests/test_audits_domain_county_ingest.py:404` ran three successive synthetic cycles. Against commit `5062b5f25d90f82e13c749567e0cff47c34fb186`, the assertion failed because the observed attempts were `[[national], [national], [national]]`, while both old county reports were deferred each time. The same test now passes for both a national reconciliation refusal and an unchanged national extraction: attempts are `[[national], [legacy executives, legacy assemblies], [national]]`, with every deferred URL recorded. `test_new_national_candidate_is_still_discovered_and_attempted` verifies that a newly discovered national URL still enters the shared queue. No discovery or source parser guard was weakened.

## Release and coverage acceptance

The 27 September [accepted source manifest](../2026-09-27-oag-coverage/accepted-source-manifest.json) and [local coverage receipt](../2026-09-27-oag-coverage/README.md) are the bounded source scope: eight exact combined volume URLs and hashes for FY2021/22–FY2024/25, separate Executive and Assembly institutions. That local replay found 6,607 new findings across 376 county × year × institution cells and left 2,338 prior rows unchanged. It is not a production result.

After coordinator integration and deployment verification, rehearse the exact accepted sources on a disposable, loopback PostgreSQL clone, newest pair first, with source hashes, page omissions, runtime, row deltas and before/after matrix retained. For production, the coordinator's serialized county-only refresh slot and signed refresh configuration (#231) still require release acceptance, backup and rollback preparation. Limit each pass to a bounded pair, inspect the job's processed/current/deferred/failed/partial outcomes, and stop on any partial text or reconciliation proposal. Repeat until all eight are accepted; then verify all 376 cells, source/page citations, exact preservation of prior findings, and the public API/browser by county, year and institution. Do not use this scheduling commit to bypass document 2392's reconciliation refusal, the FY2020/21 unreadable-page guards, or production data approval. #234 remains open until deployed and public coverage is verified. #347 also tracks the separate inflation row-count investigation, owned by the inflation session.

## Adjacent finding for coordinator triage

`backend/seeding/domains/audits/__init__.py:225` catches a national WordPress media API exception, logs a warning, and returns `[]`. A synthetic `RuntimeError('synthetic national media outage')` produced `OAG discovery failed: synthetic national media outage` followed by `national_discovery_result: []`; the caller adds no discovery error to `DomainRunResult.errors` at `:398–404`. If a known national book processes successfully, the job can therefore finish without an explicit national-discovery failure despite missing new candidates. This is a verified code path, not a claim of a current OAG outage. It overlaps the discovery/freshness concern in #234 but concerns the national pass; coordinator should deduplicate before filing. No cross-scope fix was made here.

The nightly's one unreadable page in each FY2020/21 book remains uninvestigated: the cached log does not identify the page content. Source-page evidence is required before changing that guard. The national document 2392 proposal remains unreviewed and refused.
