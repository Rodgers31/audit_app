# Batch 9 legacy ETL writer ownership — #581

**Author delivery for coordinator review; not deployment acceptance.** This lane
routes supported legacy DatabaseLoader writes through #584's reviewed shared
authority. #581 stays open until coordinator/deployment acceptance. #584 remains
held and draft; #572/#554/#545, bootstrap #582 and operational #583 remain open.
No production access, migration, activation, merge, Actions change or billable
bot-review request was performed.

## Exact identities and ownership

| Item | Identity |
| --- | --- |
| Main observed before and at final packaging | `672c5c011ce57dc41551f5fbc642bc4e69134c43` |
| Required dependency / PR target | #584, `codex/batch8-native-exclusion`, exact head `9e97ca3f1ca43f103a8655447a86d889456a218a` |
| Branch | `codex/batch9-legacy-etl-ownership` |
| Implementation commit | `38d91bc60d528d32e54bab0e94fca42503b26636` |
| Delivery head | The commit containing this handoff; resolve with `git rev-parse HEAD` and the draft PR's `headRefOid`. The PR description records its full exact hash after the single finished push. |
| Managed worktree | `/Users/roger/.codex/worktrees/af79/audit_app` |
| Final writer source SHA256 | `27c7b20eac3229118685cb278a9473ab1d843fad1c0350cc8fcb7879993b94e8` |
| Owned PostgreSQL fixture | `batch9-legacy-etl-af79-db`, postgres:16-alpine, PostgreSQL 16.15, loopback `127.0.0.1:55491`, db `batch9-legacy-etl-af79`, user `batch9_legacy`, inert password `batch9-inert-local` |
| Image identity | `sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` |
| Runtimes | Owned `.local-dev/sa2023`: CPython 3.12.14 / SQLAlchemy 2.0.23; owned `.local-dev/current`: CPython 3.13.9 / SQLAlchemy 2.0.46 |

Only seven legacy ETL files, dedicated tests/fixtures, evidence and this unique
handoff are changed. Shared native API, models, migrations, bootstrap, main,
seed.yml, frontend, manifests, common contracts and sibling worktrees were not
edited. The primary checkout and its dependencies were read-only; current owned
venvs reference existing primary site-packages and install schedule/flake8 only
locally. Minimum dependencies were installed only in the owned minimum venv.

## Resulting authority and lifetime

`etl/writer_ownership.py` calls unchanged `enter_domain` and
`DomainExecution.acknowledge`. A fixed lexical set of thirteen claims conservatively
covers shared country/entity/fiscal/source rows and overlapping financial tables:
audits, counties_budget, county_officials, debt_timeline, economic_indicators,
fiscal_summary, national_budget, national_debt, national_gdp, pending_bills,
population, revenue_by_source and stalled_projects. Learning hub and IMF WEO
use independent tables and remain concurrent. Admission occurs before any
reference-row or financial effect, including nested calls.

The outer public loader coroutine holds claims through synchronous return and
all session closes. Standalone ensure/sample methods and manual
`get_db_session`/`SessionLocal` callers enter the same boundary. Multiple manual
sessions share a group and settle only after the last close in either order.
Scope reuse requires the original Engine and thread/task. External Connection
binds, raw Connection escape and alternate mapper/table/statement binds refuse;
closed sessions cannot reopen. Private `_load_*` helpers are internal supported
implementations, reached with an owned session. No production external caller
was found; existing tests injecting raw sessions into private helpers do not
define a supported manual writer API.

One continuity transaction stays pinned per domain. NullPool avoids starving the
loader's write/observation connections behind the default small engine pool.
This increases required concurrent database connections; production capacity and
actual transaction-pooler/idle-cutoff evidence remain unexecuted gates.

Correlated RUNNING/terminal IngestionJobs record `writer=legacy_etl` and
`counts_scope=ownership_only`, with zero counts. These are ownership observations,
not fabricated financial census receipts. Normal synchronous failure is FAILED
and can release only after every session returns and the shared API validates
each terminal observation on its original continuity backend. Cancellation,
commit/storage uncertainty, backend death or absent/malformed receipt retains
ownership across restart. Partial admission refuses before loader work; its
previously acquired subset can settle honestly because no writer started.
There is no expiry, fabricated return or operator unblock path.

Readiness checks required tables/columns and the unique active-domain partial
index at startup and acquisition. Worker, backfill and scheduler refuse missing
schema. Loader unavailability no longer returns fake document id 1. Ownership
errors propagate through KNBS fallback, download, full pipeline, monitor and
scheduler, including failure to store an optional refusal observation. Worker
subprocesses use the same interpreter and nonzero exits propagate. The parent's
scheduling lock 874321 remains a scheduling mechanism; the actual writing child
owns claims, including after parent death. Small Path/logger import-order repairs
were necessary to exercise the real monitor/optional-loader paths. Financial
parsers, source selection, normalization and publication behavior are unchanged.

Detailed executed callsite inventory and supported boundaries:
[`writer-inventory.md`](../../../batch9-legacy-etl-evidence/writer-inventory.md).
Direct Engine/manual database writes and other Batch 8 inventory writers still
require operational quiescence; this lane does not claim all-writer coverage.

## Executed acceptance and evidence

The pre-comparison alive plan declared distinct real legacy/native Audit effects,
actual commit markers, before/after commit gates, refusal exits and observable
claim state. The schema came from actual Alembic, not `create_all`, for PostgreSQL
process tests. Separately launched real legacy public loader, pipeline, backfill,
worker and scheduler processes run alongside actual native CLI or dedicated
dispatch worker/adapter. Only source transport/extraction and native domain
handler data are inert fixtures; writer/authority/CLI/dispatch code is real.
Subprocess environments disable dotenv and permit only the owned loopback DB;
no provider, alert, S3 or financial endpoint is used.

| Evidence | Observed result |
| --- | --- |
| Pinned base original valid red | `baseline-red-4.json`: 3 defect failures |
| Pinned base with final identical process measurements | `baseline-final-red.json`: 3 failures, 57 deselected. Native returned 0 while legacy paused; dispatch became running; simultaneous contenders both reached writer admission. |
| Final SQLAlchemy 2.0.23 | `process-final-minimum.json`: **77 passed, 0 failures/skips/xfails**, 115.97 seconds |
| Final SQLAlchemy 2.0.46 | `process-final-current.json`: **77 passed, 0 failures/skips/xfails**, 141.56 seconds |
| Actual fresh dependency migration | `migration-current-chain.json`: upgrade from empty database to e572b8c9a001; required index inspected; separate owned migration DB removed |
| Critical CI Python lint set | `critical-lint-final.json`: E9,F63,F7,F82 passed |
| Final provenance read-back | `delivery-provenance.json`: source/generator bindings, immutable baseline measurements and raw archive bytes verified |

The 77 comprise 60 PostgreSQL process controls, 14 portable legacy controls and
3 existing native SQLite regressions. Process coverage includes both writer
orders; each public/manual boundary; all twelve other shared-reference domains
in both orders; simultaneous contenders; legacy SIGKILL before/after committed
effect and restart refusal; parent SIGKILL with live child; actual PostgreSQL
backend termination; invalid then valid receipt on the same lock backend;
successful release followed by the next native run; uncertain manual commit;
and absent/false/different-inert dispatch flags preserving default-off.
Portable tests cover close ordering, task/thread/bind escape, cancellation,
closed-session reuse, missing schema/index, independent domains and unavailable
loader failure propagation. Test warnings remain in raw output; critical lint
has zero errors. Full web/frontend/deployment gates were not run or claimed.

All three required independent reviewers completed final rechecks against the
frozen final writer hash above: Spec 4 controls, Standards 6 executions across
both runtimes, Behavior 8 executions across both runtimes. No unresolved finding
within their reviewed scopes. Their repairs cover swallowed ownership refusal,
external/raw Connection lifetime, standalone scheduler import, manual close
order, incomplete schema and commit uncertainty. Their exact source/generator
hashes, red receipts, green receipts and limitations are preserved in
`spec-final-recheck.md`, `standards-final-addendum.md` and
`behavior-review-recheck.md` in the evidence directory.

The author additionally reproduced optional refusal-observation storage failure:
the original OperationalError could be swallowed; the same immutable control
now propagates DomainOwnershipError with zero effects and one retained claim on
both runtimes. Independent behavior replay also proved the actual monitor remains
failed and creates no fabricated jobs.

Receipts were generated before implementation commit while HEAD still named
the dependency; their source hashes bind the actual uncommitted tested files,
which are identical to implementation commit `38d91bc60d528d32e54bab0e94fca42503b26636`.
Original failures, examiner setup errors, intermediate/source-drift runs and
corrected controls are honestly classified in
[`evidence README`](../../../batch9-legacy-etl-evidence/README.md).
Raw process outputs are archived with original paths and per-file hashes;
generator/read-back scripts are committed. No failed/setup run is counted as
acceptance and no original red receipt was overwritten.

## Remaining facts and follow-ups

The missing-index review also proved the unchanged shared native CLI can commit
an inert effect despite an abandoned retained claim when its uniqueness index is
removed on SQLite. All-state issue dedup found no existing admission issue;
[#594](https://github.com/Rodgers31/audit_app/issues/594) now tracks concrete
reproduction, impact and acceptance (including PostgreSQL). This lane's legacy
guard refuses that schema; shared native/dispatch repair is separately owned.
Normal migrated schema is protected; no deployed drift is asserted.

Before migration/activation/coordinator acceptance: resolve the held dependency,
execute #583's production RUNNING census, prove actual pooler behavior/capacity,
establish all-writer quiescence (including #582/bootstrap and manual paths), and
review audited reconciliation. Operator release cannot be inferred from age,
process death or the local green controls. #594 remains separately open.
The five repository YAML workflows were observed disabled_manually, while
dynamic Copilot workflows were active. These read-only statuses are recorded;
no workflow was enabled, dispatched or edited and no hosted CI pass is claimed.

## Resume and cleanup

Owned test process groups were stopped by fixture cleanup. Container
`batch9-legacy-etl-af79-db` and its anonymous data volume
`3ced5b6168fe28df3c70be40af1d096220463091f70e8a73cf747a05fec9737c` were removed;
loopback port 55491 was proved free afterward. Only this lane's resources were
touched. Managed worktree, owned runtimes and committed evidence remain available
for review. `owned-container-cleanup.json` records the actual removal.

For replay, first verify the owned name/port are free. Recreate only the inert
fixture with `postgres:16-alpine`, user/password/db above and
`-p 127.0.0.1:55491:5432`, then use explicit
`DATABASE_URL=postgresql+psycopg2://batch9_legacy:batch9-inert-local@127.0.0.1:55491/batch9-legacy-etl-af79`,
`PYTHON_DOTENV_DISABLED=1`, `PYTHONDONTWRITEBYTECODE=1`. Run actual
`alembic upgrade head` from backend using the owned interpreter. Final JSON
receipts contain complete clean-env argv, paths and basetemp; replay the three
named pytest files with `--confcutdir=backend/tests` on each owned runtime.
Run suites sequentially because the fixture truncates its owned DB per case.
Do not run `baseline_replay.py` concurrently with tests/reviewers: it temporarily
restores only owned legacy source bytes, executes expected reds and restores
the candidate in finally. Offline verification:

```sh
PYTHONDONTWRITEBYTECODE=1 .local-dev/current/bin/python \
  batch9-legacy-etl-evidence/verify_delivery.py
git diff --check
```

Lesson from the receipts: successful private-helper tests do not prove public
transaction lifetime. External/raw connections can commit after ORM close, and
optional-source catches can erase a correct refusal. Actual public entry points,
committed-effect gates and end-to-end monitor status exposed those defects;
unchanged probes and independently verified source hashes proved the repairs.
