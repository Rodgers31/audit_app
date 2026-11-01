# PR865 independent Standards review

**Scoped pass.** 47 independent executable cases passed normally and the same 47 passed under true Python `-O`, zero skips/errors/failures. No new actionable finding remains. Six actual-writer controls independently fail with the prior gate and pass with the repair.

## Exact source and disposition

Frozen `../candidate`: **6,617 files**, mapping SHA256 `1780790d6e2921c3f2aa2ae232a78346b4979cc1d6aef9cc6fc414316ff0c9e4`; manifest-file SHA256 `3a4a494bf7b7e4676a7f287b41024196d7516e56a786c03f87f9a0813a776e48`. Every file and the complete inventory were verified unchanged after execution. Gate SHA256 `28583346e4be248d0f831d2614d3665d9d4a30786c489e29255c7fbe96842d40`. `DELTA.json` confirms the gate is the only runtime path changed from the previously reviewed admission candidate; tests/docs changes are listed separately.

The original defect is valid and resolved: real national, revenue and county-pending writers rebound current job/value/evidence while the old disabled gate returned before clearing `publishable=True`. The final gate first selects exact native candidates, then clears their previous numeric verdict when source admission is off. Its ordinary disabled path does not ask invalid evidence to pass qualification.

The earlier admission review established a flag-toggle-without-write boundary only. It did not establish refreshed-row safety and is superseded on that point by this review. A flag toggle alone still preserves existing qualified current facts; a valid OFF native writer refresh must clear them.

## Executable evidence

| Independent scope | Cases per mode |
| --- | ---: |
| Three actual writers, same and changed values: all written row identities/verdicts, old/current reader refusal, flag-only non-revival, later ON/source-only readmission | 6 |
| Actual three-writer rollback after invalidation+flush; source/extraction/value/lineage recovery | 3 |
| Actual three-writer interleaved sessions: old committed state remains readable before commit, new disabled state refuses after commit | 3 |
| Actual three-writer replay twice in the same job/transaction, toggling OFF between writes | 3 |
| Invalid/missing/bool/nonpositive/noninteger job contexts; no SQL or mutation | 8 |
| Nonliteral-false dry-run inputs; no mutation | 4 |
| Foreign publisher/URL and absent/wrong/bool binding: scope preserved, current readers refuse | 7 |
| Missing/bool/string row lineage: gate and current reader refuse | 3 |
| Stale receipt, changed amount, archived source and exact operator quarantine: matching OFF row cleared without positive qualification | 4 |
| Unrelated national pending scope preserved; county financial reader remains closed | 1 |
| Empty/duplicate identity iterables; distinct 1000 accepted/1001 refused atomically | 4 |
| Default-off fresh numeric rows remain unqualified while actual dated report-only reader remains usable | 1 |
| **Total** | **47** |

Normal container wall time 8.057s; optimized 9.259s. `CASE-LEDGER.json` pins 94 final case executions to real JUnit. `independent-{normal,optimized}-command.json` records the complete executable commands. Tests: `test_refresh_invariant.py`.

The bounded counterfactual mounts only `prior-gate-1e349292.py.bytes` over the candidate gate, read-only. All six same/changed actual-writer cases fail with assertion failures, exit 1, zero error/skip; `prior-counterfactual.*` and `PRIOR-GATE.json` pin the execution and old source. This is an expected negative control, not a failed final candidate.

The first harness run retained 43passes/four failures (`setup-v1-normal.*`, `fixture-v1.py.bytes`, `SETUP-V1.json`). Three JSON boolean mutations were initially suppressed by ORM equality (`True==1`) and one unrelated Loan fixture omitted required `issue_date`. Explicit dirty marking and the required field corrected the fixtures; these failures receive no final pass credit and were not product findings.

## Runtime, effects and limits

Cached image `sha256:1b4cc12668ffaa5bd5e5aa78bd96c053f8d0778651c040ad4a5d69ef305d983b`: Linux arm64, Python 3.12.16, SQLAlchemy 2.0.55; PostgreSQL 17.11 at Alembic `a756b20a0001`. Tests ran in capped 1 CPU / 768MiB / 256 PID containers, source read-only, joined solely to the owned network-none PG namespace (no host port). PG was capped 1 CPU / 512MiB / 128 PIDs with tmpfs data. URL/live role/database/port/data-directory/schema guards ran before any truncation.

All software fixtures use owned synthetic publisher-shaped HTML/PDF extraction cells and local job clocks/acquisitions. They are not proof of genuine/current official facts or source-adoption permission. Installed restricted-role/view/witness coverage is separate Spec evidence, not counted here. No production/provider/network/hosted/paid action or operational activation occurred. The gate repair changes no reader, view, grant, worker or publication permission.

Every PG control asserted no social post, target, publication, media, cursor or event effects. A separate final read-only query confirmed zero rows in all seven tables (`RUNTIME.json`). The pre-existing ordinary no-op boundaries do not bless changed evidence: foreign/noncounty/malformed-binding controls preserve scope while the actual current reader refuses hostile state.

## Replay and teardown

Copy `prepare_owned.py`, `run_independent.py`, `test_refresh_invariant.py` into a fresh evidence sibling beside the retained candidate; run `python3 prepare_owned.py`, `python3 run_independent.py`, then `python3 run_independent.py --optimized`. This requires only the pinned cached runtime/postgres images. Do not overwrite sealed outputs or run the narrowly named fixture concurrently. The script creates throwaway credentials; no production credentials are needed. Counterfactual command is separately retained and must yield exactly six assertion failures.

Owned `pr865-standards-pg-20261031` and both credential env files were removed; container/file absence and retained-artifact secret scan passed (`CLEANUP.json`). Root/shared resources were untouched. `seal_review.py` is the original non-idempotent seal/cleanup receipt generator. Offline packet verification: `python3 verify_packet.py`.
