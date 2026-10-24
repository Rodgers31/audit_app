# B66 preflight author handoff — 24 October 2026

Implementation is complete for the additive, default-off manual preflight and
retained-cost planning interface. This author work does not accept production
ingestion, close #699/#583/#481/#778, or authorize activation/downgrade. Worktree:
`/Users/roger/.codex/worktrees/b66-ingestion-preflight/audit_app`; branch
`codex/b66-ingestion-preflight`; frozen base
`924f1a4f27e1952f97d2291d8878d88603132237`.

## Source and design

Read B66 COORDINATION, B65 CURRENT_REPORT/QUERY_AUDIT/NIGHTLY_READINESS, current
issue bodies/latest comments for #699/#583/#481/#778, existing rollout/reconciliation
operator and operating-evidence contracts. Raw issue snapshots and local evidence
are retained under the coordinator's `BATCH_66_LAUNCH/preflight/` directory.

`seed.yml` is owned by the source lane and untouched. Exact frozen workflow
extraction confirms the migrate job and its `cd backend && alembic upgrade head`
step have no dry-run conditional. Executing that exact shell with an inert owned
alembic produced a migration marker with dry-run=true: the no-write baseline is
red. This reproduces shell dispatch, not an actual provider migration.

The new workflow only dispatches manually, has contents:read, one concurrency
group, standard Ubuntu and five-minute job limit. It refuses without an exact
externally owner-admitted workflow SHA. No admission variable was created; a
scoped read returned404. Tool and policy checkouts use literal immutable pins.
Policy bytes are hash-checked and parsed once, separately from the earlier tool
HEAD they describe, avoiding self-referential commit identities. The shipped
policy is disabled with absent production expectations. It refuses before
dependency/credential scope. The existing DATABASE_URL secret is referenced only
by the final read step; its value was never read/copied here. Installation has no
credential scope and uses isolated, hash-pinned binary driver requirements.

The invoked API/CLI enforce read-only connection defaults and an explicit bounded
read-only transaction, exact identity/role/TLS/schema/source expectations,
allowlisted fixed SQL, strict primitive types, RLS visibility refusal and no
arbitrary dispatch SQL/URLs/refs/paths. Unknown/NULL/nonterminal states refuse.
Cleanup rollback/close failures invalidate an observation. The single outer
deadline covers CLI admission, inspection and publication without extension by
nested API calls. Reports bind tool/source/config/runtime, stay bounded and
untrusted when imported, and never grant writer or receipt authority.

The cost interface delegates to the existing operating evaluator and returns
BLOCKED, including when that evaluator returns an owner-review candidate. It
preserves the retained90.1MB/43.126GB/cached0/MAU1 distinction and records no
optimized daily rate. Representative source/backup traffic, provider cutoffs,
caller/peak/reserve/memory, recurring offsite backup policy, retention/recovery and
owner decisions remain unmet. Current Supabase plan/spend cap, Vercel$1PauseOn and
the28October21:45:54America/Chicago export-custody deadline remain unchanged.

## Changed paths

- `.github/workflows/ingestion-preflight.yml`
- `scripts/verification/ingestion_preflight.py`
- `scripts/verification/ingestion_preflight_readiness.py`
- `tests/ingestion_preflight/{conftest,test_inspector,test_readiness_workflow}.py`
- `docs/admin/batch66/preflight-{admission.json,driver-requirements.txt,contract.md,handoff.md}`

No shared workflow, backend/main.py, source registry/config/CLI, dependency/lock,
migration, conftest or peer-lane implementation changed. The primary dirty
checkout and coordinator checkout were not mutated.

## Executed validation

Runtime: cached Python3.13.9, psycopg2 2.9.12, actual owned PostgreSQL17 at exact
loopback56972. One cached-image container `b66-preflight-pg`,512MiB/0.5CPU; no
production connection, new image pull or environment copy. The fixture is a
small realistic operational-schema contract, not the migrated production schema;
its TLS-disabled local exception is explicit. Hosted verified TLS remains
unexecuted. Container/resource cleanup is recorded externally before delivery.

From the owned worktree, the following new cohort passed **176 cases, zero skips**
under normal and optimized Python (separate runs, not additive counts):

```sh
B66_PREFLIGHT_OWNED_PG=56972 /Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python -B -m pytest -c /dev/null --rootdir=. -p no:cacheprovider -o asyncio_default_fixture_loop_scope=function tests/ingestion_preflight -q --tb=short
# Repeat with python -O -B for optimized interpreter guard coverage.
```

Actual CLI/PG checks include exact identities/readonly context; wrong DB/role/
schema/source/TLS; no application data/schema/role/ACL/membership change; blocked
DML independent of owner ACL; unrelated active writer; retained uncertain claim;
unknown/NULL/PENDING state; real statement cancellation and lock timeout; RLS
invisibility; strict malformed/absent/nonfinite/truthy-failed input; disabled
receipt authority; no secret/error/private-record leakage; exclusive regular-file
publication, readback, traversal and policy replacement controls; request/row/byte
and whole-deadline guards; direct API admission, concurrency and cleanup refusal.

Existing affected operating evaluator/collector controls passed **358 cases**:

```sh
PYTHONPATH=backend PYTHON_DOTENV_DISABLED=1 /Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python -B -m pytest --confcutdir=backend/tests/egress -c /dev/null backend/tests/egress/test_operating_acceptance.py backend/tests/egress/test_social_operating_collection.py backend/tests/egress/test_social_operating_independent.py -q --tb=short
```

The first affected-cohort attempt failed setup because backend was absent from
PYTHONPATH; no tests ran. Corrected receipt is separate. Pytest's /dev cache-path
warning is retained; final runs disable its cache. A YAML scalar parsing failure,
an admission-shape regression during repairs, and every real red reproduction are
preserved rather than relabelled as acceptance. Normal formatting/AST checks and
bounded secret-pattern/full diff review are required before explicit staging.

An initial global WAL-position assertion proved unsuitable as a mutation oracle
when unrelated cluster-wide WAL moved in an independent review. That failed
receipt is retained. The committed oracle instead compares exact owned table,
catalog, role/ACL and membership snapshots; it does not infer application mutation
from a global maintenance counter.

The tests intentionally form a standalone required local cohort. This lane did
not edit shared CI/verification discovery or enable Actions. Coordinator must run
the cohort explicitly with the owned fixture; missing fixture admission fails
rather than skipping green. No full17000-case backend/release/hosted gate is
claimed. Linux wheel execution and production TLS remain unexecuted.

## Independent executable reviews

Spec and Standards/adversarial reviewers independently executed the candidate.
Their complete source/runtime manifests, commands, raw logs and findings live in
`preflight/review-spec/` and `preflight/review-standards/`.

Confirmed findings were independently reproduced red before repair: output `..`
containment, unsupported/NULL lifecycle state success, direct-API admission
outside its deadline, and CLI admission outside its whole-invocation deadline.
Corresponding green controls are committed. Policy hashing/loading was also
changed to consume one exact raw byte sequence; the deterministic replacement
control refuses and no unexecuted earlier false-green is claimed for that case.

Final inspector SHA256:
`44a51b0581d1912502409c9834541d5d5d06ef57d9659e56b6f90ce7d1bf029a`.
Both reviews are clear on those bytes. Standards executed168 cases plus96
transport/cleanup controls, five actual-PG ACL/RLS/snapshot controls and six
timer/CLI controls. Spec re-executed its actual-PG unknown-state attack and final
deadline/cleanup attacks. After the last workflow-only external-pin correction,
both ran35 workflow/readiness cases and independent hostile shell controls. Final
176-case author runs include those eight added workflow cases. Earlier review
counts/hashes remain historical, not silently promoted to the final package.

## Production state and next acceptance

No merge, deployment, hosted Actions, provider probe, source run, migration,
upload/publish, grant/credential/retention/budget/plan change, backup/export or
support message occurred. Publishing/uploads/native/supervision stay OFF.
GitHub API readbacks confirm Actions globallyOFF and five static workflows
disabled at the recorded times. Personal review/Preview controls use coordinator
launch captures, without seizing Chrome. Dynamic bot listings do not override
the global OFF state. No bot review was requested.

The exact future admission/run/abort/observation sequence and rollback boundaries
are in `preflight-contract.md`. Coordinator owns fresh control readbacks, merged
accepted-source/policy pins and an independently approved exact main workflow
SHA. The author delivery does not provision that admission. Future read success
still leaves `safe_to_write=false`, custody UNMET and live receipt backend
NOT_OBSERVED. Existing DATABASE_URL format/privileges may refuse and are not
certified here. No privilege expansion is suggested to force a pass.

Preserve existing Render stop/capacity/restore fixture limits; do not label this
fixture or a quiet window production Supabase active-workload proof. Native
preview, actual one-source ingest/idempotency, UI/cache/provenance/receipt and
representative operating acceptance remain separately scoped work. The observed
.org/.com hostname difference is for coordinator verification, with no DNS/OAuth
or session transfer performed here.
