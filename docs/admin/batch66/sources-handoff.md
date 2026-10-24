# B66 sources author handoff

Frozen common base `924f1a4f27e1952f97d2291d8878d88603132237`; branch `codex/b66-source-automation`, owned managed worktree `/Users/roger/.codex/worktrees/b66-sources/audit_app`. This is a draft author delivery, not merge/deployment/activation or whole-admin acceptance. The primary dirty checkout and coordinator checkout were not mutated.

## Problem and result

The existing CRA and pinned KNBS handlers were opt-in but their flags never reached the seed workflow. Free-text dispatch domain was spliced into shell, and Sunday requested two serialized all-domain runs. New workflow selection validates the native-domain whitelist and literal flags before migration, passes an argument vector to the unchanged CLI, forwards default-off source flags, and selects one Sunday03UTC run with seed-before-bootstrap preserved. Legacy Monday–Saturday02UTC scope stays fifteen domains. Opt-in CRA/OpenData checks are weekly or explicitly selected manually.

The optional KNBS observer follows a bounded official index → report → workbook path under existing native/dedicated job ownership. Conditional page receipts do not suppress workbook content checks. The accepted pinned URL/hash alone reaches the unchanged parser/writer; unknown future/compatible editions, URL aliases and byte revisions become visible quarantined job candidates. Existing accepted records remain intact. No unqualified figure is promoted to a public fact. This completes bounded observation and safe selection; **future edition semantic admission is deliberately not claimed** without authentic edition-specific evidence. #744 and its cross-file calendar label dependency remain open, as do #602/#554/#583/#699 acceptance.

[Coverage matrix](sources-coverage.md) maps source → handler → CLI/dedicated ownership → workflow flag/cadence → persistence/qualification → UI/readback frontier for all seventeen registered/opt-in domains. [Operating contract](sources-contract.md) gives exact budgets/defaults, uncertainty and rollback. Additional #745 datasets/widgets are excluded.

## Changed paths and invariants

- `.github/workflows/seed.yml`: default-off environment wiring, domain choices, pre-migration selection check, safe native runner, Sunday deduplication, accurate preview label and safe summary interpolation.
- `backend/seeding/source_plan.py`: executable whitelist/cadence/flag plan and argument-vector runner. The UI calendar does not drive this selection.
- `backend/seeding/config.py`: strict literal default-off KNBS discovery opt-in.
- `backend/seeding/domains/opendata/__init__.py`: ownership before/after discovery; terminal conditional/history metadata; refused quarantined candidate outcome. Narrow reads select bounded job metadata and source/extraction IDs/digest. Missing legacy receipt differs from malformed present receipt.
- `backend/seeding/domains/opendata/discovery.py`: official host/path allowlist, six attempts/2MiB cumulative body/45s hard runtime/zero redirects, two bounded pages and one workbook, conditional link observations, fixed backoff, content/provenance identity and pinned-only admission. Direct helper budgets and actual shorter-alarm cleanup are enforced.
- `backend/tests/b66_sources/`: executable planning, HTTP/refusal, real CLI/dedicated command, file/source idempotency, partial rollback, overlap, crash/restart and signal-cancel controls. Own PostgreSQL fixture uses cached pinned image, `b66-sources-*`,127.0.0.1:56973,512MiB/0.5CPU and exact cleanup. Normal lane tests work without a hidden fixture override; the optional plugin shares one owned container across existing affected cohorts.

No other workflow, dependency/lock, model/migration, `main.py`, frontend or financial qualification semantics changed. No expiry/force-release or quota/ownership bypass. No source scrape or provider write was used in author verification.

## Reproduction, red/green and independent review

External evidence root:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH_66_LAUNCH/sources/`.

- `evidence/plan-red.txt`: four expected failures on frozen base: duplicate Sunday, absent executable selection plan, absent opt-in wiring and **actual inert shell marker execution** via domain interpolation. Candidate plan cases green.
- `evidence/discovery-handler-red.txt`: frozen real handler replay (without mutating checkout) ignores discovery opt-in and enters pinned transport. Candidate real handler selection green.
- `direct-budget-red.txt`: nonfinite/future origin and missing direct helper alarm reproduced; corresponding finite-state/remaining hard-budget controls green.
- `first-history-red.txt`: actual PostgreSQL first accepted terminal receipt reported null history; post-persist history lookup fixes it.
- `alarm-red.txt`: real short outer timer plus blocked injected transport left the wrong SIGALRM handler installed; shared owned deadline fixes cleanup. The unchanged independent timed probe also passes.
- `retained-pages-red.txt` and `present-receipt-red.txt`: malformed retained pages and explicit null receipt became absence; shared strict validation and key-presence distinction refuse before transport.

Two independent executable internal reviewers operated on current product hashes. Spec reviewed issue/contract fit and executed source/handler/selection/timing probes; Standards executed100 hostile cases and30 handler/query-boundary cases. Both independently replayed98 focused plan/discovery cases and report no outstanding confirmed findings. Their limits exclude PostgreSQL/production; real PostgreSQL execution is the author's affected cohort. Reports and hash-bound artifacts are under `evidence/spec-review/` and `evidence/standards-review/`. Initial reviewer harness setup failures and earlier failed author runs are preserved, not counted as acceptance.

Final reviewed product hashes:

- `opendata/__init__.py`: `96881678f440d61918107436f52b5760a54516d9fd0aca87d7223c90f067b881`
- `opendata/discovery.py`: `eaa1a6d0dac1a178f102431f920f7fe1dd900ab6a2dfe5ebe0efc6db01e9b489`

## Executed validation

Supported cached Python3.13.9; dotenv disabled and no production env/secrets inherited. Root test database URL is an owned file-engine URL. Native cases use the owned migrated PostgreSQL17 image at digest `sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3`, with per-case databases and existing real native ownership/parser/writer/worker code. Source transport alone is replaced by bounded local fixtures. The final recorder retains resolved inert environment, source hashes, raw output, JUnit cases and exact container/volume/port cleanup.

Final pre-commit affected replay: **644 passed,6 skipped,0failed/errors,79.65s**. Every changed test executed. The six skips are existing workflow syntax checks containing GitHub expressions, named individually in the receipt; no PostgreSQL case skipped. No XPASS, surviving child group or source mutation. `evidence/final-affected/receipt.json` binds this to frozen HEAD plus exact uncommitted source hashes, not a fictitious future commit. The additional explicit SIGINT cancellation case passed separately (`cancel-signal.txt/.xml`); counts overlap and are not added as one suite. After committing the packaged handoff, the author repeats the complete affected selection at that exact commit; that separate receipt belongs under `evidence/final-head-affected/` and the external STATUS records its outcome.

Exact affected test selection, with cwd at the owned worktree:

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 \
DATABASE_URL=sqlite:////tmp/b66-sources-owned-inert.sqlite \
PYTHONPATH=backend:backend/tests B66_SOURCE_EVIDENCE=/absolute/owned/evidence \
/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python -m pytest \
-p b66_sources.pg_plugin backend/tests/b66_sources \
backend/tests/test_b17_opendata_parser.py backend/tests/test_b17_opendata_native.py \
backend/tests/test_b17_opendata_writer.py backend/tests/test_b17_opendata_bootstrap.py \
backend/tests/test_b17_opendata_legacy.py backend/tests/test_batch11_cra_parser.py \
backend/tests/test_batch11_cra_writer_boundaries.py backend/tests/test_batch11_cra_legacy_ownership.py \
backend/tests/test_workflow_inline_scripts.py backend/tests/test_bootstrap_workflow_outcomes.py \
backend/tests/test_receipt_seed_workflow_binding.py backend/tests/test_seeding_cli_budget.py \
backend/tests/test_hollow_run_gate.py backend/tests/test_source_registry_fields_are_read.py \
-q --tb=short
```

The recorded final commands replace the illustrative inert file/evidence paths above with their exact owned receipt directory; see `run_final_checks.py` and `evidence/final-affected/start.json`. Critical flake8 (`E9,F63,F7,F82`) returned0; `git diff --check` passed. The earlier full affected615/6, native first/second failures and lane80/99 passes are historical source states, not cumulative totals. First PG cleanup's non-reusable socket check failed after actual container removal; corrected SO_REUSEADDR cleanup subsequently passed. All original failure bytes remain external. Current/minimum full-suite, Python3.12 and hosted CI were not executed; local fixtures are not production runtime parity.

## Deployment/default-off and rollback

All three source flags remain false by default. Actions/static workflows, previews, publishing/uploads/social/native supervision remain OFF; no bot review requested. API controls are read back before publication; Chrome-derived personal review/preview controls remain launch observations, with exact capture time and hashes retained. No provider plan/resource/budget/DNS/OAuth/access/secret/storage setting changed. Existing Vercel$1PauseOn and Roger's export custody/deadline remain unchanged.

This workflow still migrates, can bootstrap and performs broad validation when eventually authorized. Its dry_run is not a no-write preflight. Quarantined candidates persist as `COMPLETED_WITH_ERRORS` with refused source mode; the legacy CLI may exit0, while real hollow-run and dedicated-command gates refuse acceptance. No fresh publisher data, billed savings, Free viability or public financial verification is claimed from synthetic/local replay.

Rollback: keep all opt-ins false and revert the scoped source/workflow commit. No schema reversal or financial rewrite is needed. Preserve existing accepted records, source history and retained claims. Never release an uncertain owner by age.

Coordinator holds: authentic bounded listing/report/source read; actual intended hostname `.org` versus old `.com`; deployed/runtime/receipt/database identity and fresh custody; intended-host source preview/ingestion/no-change/operator/UI acceptance; representative active SQL/egress/storage/capacity/provider answers. `backend/etl/smart_scheduler.py:112` stale “Continuous dataset updates via API” is outside lane ownership and explicitly recorded in external `DEPENDENCIES.md`; do not relabel this as accepted live automation or close #744/#602/#699 on this draft alone. Keep the author worktree and evidence while PR is open.
