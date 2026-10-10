# Independent bootstrap behavior controls

Executed locally on 2026-10-09 against the uncommitted #582 candidate on pinned
dependency HEAD `9e97ca3f1ca43f103a8655447a86d889456a218a`. The examined
`backend/bootstrap.py` SHA256 was
`4d28994ffa3e1b8564e7969b2f105633f6e93a8f40fefe2c142ed5913570f12d`;
`backend/seeding/exclusion.py` was
`a62033df887862e34bca064a3ddd2aace56730a4f573aced8e07ceb3b8a257a6`.
This is combined candidate verification with the held #584 seam, not a claim
about merged main, hosted Actions, deployment, or production persistence.

No actionable product finding was reproduced. Each runtime passed the same
22 controls with **0 failures, 0 skips, and no setup error**. The overlapping
selections are reported separately rather than added together:

| Receipt | Python | SQLAlchemy | Pydantic | Process exit | Controls |
| --- | --- | --- | --- | --- | --- |
| [current-1.json](current-1.json) / [raw output](current-1.txt) | 3.13.9 | 2.0.46 | 2.12.5 | 0 | 22 passed |
| [minimum-1.json](minimum-1.json) / [raw output](minimum-1.txt) | 3.12.15 | 2.0.23 | 2.14.0 | 0 | 22 passed |

Exact driver commands, from the worktree root:

```sh
/Users/roger/Documents/projects/audit_app/venv/bin/python docs/admin/implementation/batch9-bootstrap-evidence/adversarial/control.py --run current-1
.local-dev/batch9-bootstrap-min/venv/bin/python docs/admin/implementation/batch9-bootstrap-evidence/adversarial/control.py --run minimum-1
```

The primary Python runtime was executed read-only. The control generator is
[control.py](control.py), SHA256
`26054475b0a18a8711b0a598d6bc59c6317ae1b4c02cdf2a7037f3cd10667c95`.
Each receipt records every child command and its explicitly scoped environment,
per-case exit and actual durable state, source hashes, runtime versions, and
raw-output hash. Generator, output, source hashes, case count, and verdict were
re-read from both receipt files and checked after execution; all matched.

The driver created separate `batch9-bootstrap-adversarial-<uuid>` PostgreSQL
databases on loopback port 55492. Each control used its own schema and an
actual separately launched OS process calling
`bootstrap.initialize_reference_data(force=True)`. It replaced only the
registry handler with an inert destructive writer: delete a real owned
`BudgetLine` sentinel, then insert an effect. Returned shapes and release
failure points were independently controlled. The actual bootstrap transaction,
claim acquisition, durable job observation, and acknowledgement paths ran.
Network transports outside the loopback fixture were refused. Termination
verified the target backend belonged to the control's own database. All owned
connections, schemas, and databases were cleaned; no author database was used
for these cases.

## Executed controls and observed outcomes

- Normal result and supplied Engine/default factory: one completed budget
  effect, sentinel removed, 47 counties committed, claim released.
- Supplied `Connection` factory: the same successful outcome with independent
  claim persistence and continuity connection. This covers an ordinary bound
  Connection without an external transaction; it does not certify arbitrary
  externally managed transaction/search-path arrangements.
- `None`, empty dict, and a truthy object with `success=False`: no coherent
  result accepted; budget deletion/effect rolled back, FAILED job committed,
  47 counties committed, active claim retained.
- Constructed/mutated results containing boolean, negative, overflow, NaN, or
  infinite counters; another domain; dry-run `True` or string `"false"`;
  returned errors, string-shaped errors, or `metadata=None`: the same safe
  rejection/rollback/retention outcome. These bypassed model constructor
  coercion using `model_construct`, so the bootstrap's revalidation ran.
- Handler exception after the destructive write: sentinel preserved,
  effect absent, FAILED job persisted with `ownership_retained=True`;
  reference counties remained committed as the deliberate budget-savepoint
  semantics require.
- Failure after actual national reference work but before budget handler:
  counties rolled back, sentinel preserved, budget handler absent, active
  claim retained, FAILED bootstrap job persisted. The committed claim was
  not accidentally rolled back with references.
- An untagged RUNNING `national_budget` observation from 365 days earlier:
  bootstrap refused budget ownership visibly, did not invoke the destructive
  handler, and still committed reference counties. Age did not reclaim it.
- Invalid receipt `-1`, then the valid persisted budget job receipt through
  actual acknowledgement: invalid receipt rejected while continuity remained
  held; the subsequent valid receipt released ownership. Both explicit control
  markers are preserved in raw output.
- Actual PostgreSQL backend termination immediately after acknowledgement's
  continuity proof, before its mutation: process failed and active claim
  remained, with the already committed budget effect present.
- Actual PostgreSQL backend termination after the release UPDATE executed,
  before savepoint/outer transaction commit: process failed and active claim
  remained, with the already committed budget effect present. The release
  mutation rolled back on the same backend. A writer commit before an
  uncertain acknowledgement is deliberately not reported as undone.

## Limits and reusable lesson

These controls do not replace the author's actual native CLI acquisition-order,
web-startup, weekly invocation, dry-run, readiness, kill/restart, or SQLite
controls. This independent suite does not by itself establish all #582
acceptance. PostgreSQL durable behavior was tested here; SQLite behavior and
production pooler configuration were not certified by this report.

A real preexisting sentinel makes destructive-write rollback observable. An
effect count alone could pass even if a handler deleted preexisting rows before
its failure. The 15 malformed/failed-result cases here preserved that sentinel
and kept their claims, on both ORM versions. A release failure after writer
commit must assert retained authority and the durable writer effect separately;
the latter cannot truthfully be claimed rolled back.
