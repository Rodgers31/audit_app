# Current review acceptance

The 2026-10-09 review corrections and fresh acceptance evidence are indexed in
[PR590_REVIEW_ACCEPTANCE.md](PR590_REVIEW_ACCEPTANCE.md). The report below is
the preserved author history at `813acb0b75c6eccadf514dbbaffbc6439fd7fb63`; its
source hashes, dependency state, default-skip setup and previous acceptance
claims describe that earlier candidate. They do not certify the repaired source.

---

# Batch 9 bootstrap ownership evidence (#582)

All verification is local against the held #584 seam
`9e97ca3f1ca43f103a8655447a86d889456a218a`. Final bootstrap source SHA256:
`4d28994ffa3e1b8564e7969b2f105633f6e93a8f40fefe2c142ed5913570f12d`.
No hosted execution, deployed acceptance, pooler verification or live sources
are established here. `record.py` appends raw output and JSON receipts with
command, inert environment, commit and source hashes, generator hash, exit code
and output hash; it reads the written provenance back. `verify_receipts.py`
checks every JSON receipt and the independent Spec raw headers from disk.

## Final local results

| Receipt | Executed result |
| --- | --- |
| `ownership-current-final` | 20 passed, 0 failures/skips/xfails; Python 3.13.9 / SQLAlchemy 2.0.46 |
| `ownership-min-final` | Same 20 cases passed; Python 3.12.15 / actual SQLAlchemy 2.0.23 |
| `regressions-green-final` | 143 passed, 0 failures/skips; current runtime |
| `regressions-min-final` | Same 143 cases passed; minimum ORM runtime |
| `additional-scoped` | 45 passed, 0 failures/skips; native SQLite, packaging, national-budget and supersession controls |
| `migration-current`, `migration-min` | Empty owned databases upgraded through actual chain to `e572b8c9a001`; claims table RLS enabled, zero claims |
| `lint-import`, `compile-import` | CI critical flake8 selection clean; 4 sources parsed and actual bootstrap/main imports passed |
| `adversarial/current-1`, `adversarial/minimum-1` | 22 independent controls passed on each runtime; no failures/skips/setup errors |
| `spec-readiness-green`, `spec-readiness-green-minimum` | Actual native-first startup reports ready with 47 counties and only the native handler entered |
| `standards-session-green`, `standards-session-min-green` | 8 independent session cases passed on each runtime |

Runtime replays and independent selections overlap; do not add their counts.
The PostgreSQL tests use real separate OS processes and actual bootstrap,
`main._startup_sequence`, and `python -m seeding.cli seed --domain/--all`.
Only registry handlers are inert. The destructive writer deletes real sentinel
budget rows; sockets outside the owned loopback are blocked. Product claims
are durable PostgreSQL rows, separate from the reference transaction.

## Preserved red and unsuccessful runs

- `baseline`: 30 existing controls passed on the pinned dependency before edits.
- `ownership-red`: six real acquisition-order regressions failed on the pinned
  bootstrap; competing processes entered and gated rather than refusing work.
- `readiness-red` and independent `spec-readiness-red`: the first candidate
  still deferred normal native-first boot and claimed readiness with zero counties.
- `supplied-session-red`, `standards-session-red`, `regressions-green-1`:
  confirmed candidate regression; refused acquisition rolled back a supplied
  SQLite caller transaction. Preserving its Connection and using an explicit
  savepoint fixes it. The independent ORM control demonstrates both modes.
- `ownership-green-1`: earlier 13-case matrix passed, before expanded readiness
  and ambient-configuration coverage. Superseded by the final 20-case matrices.
- `ownership-green-final`: 19 passed / 1 failed due to the test expecting
  `superseded` instead of the preexisting `fixture_superseded` value. The fixture
  expectation was corrected; product code did not change.
- `issue-dedup`: isolated GH configuration was absent; auth exit 4 / wrapper
  exit 1. This is a tooling setup failure. The original authenticated all-state
  fetch had 288 issues (`dedup-before-589-snapshot`); configured replay succeeds
  with 289 including newly created #589 (`issue-dedup-configured`).
- `other-domain-readiness`: successful reproduction of the **unchanged**
  non-budget false-readiness defect, now tracked separately as #589. A pass
  means the defect reproduced, not that readiness is correct.

All earlier receipts retain their original source/generator identity. Final
results changed because of documented product repairs or the corrected fixture
expectation, not a silently edited receipt generator.

## Replay

Recreate only an owned `postgres:16-alpine` container, database
`batch9-bootstrap-1183`, user `batch9_bootstrap`, inert password
`batch9-inert-local`, on **127.0.0.1:55492**. Verify the port is free first.
The author process fixture currently requires that exact port; each case creates
and drops its unique schema. Independent review/migration drivers use separate
databases beginning `batch9-bootstrap-` because advisory locks are database-wide.

From the managed worktree, an example new receipt command is:

```sh
/Users/roger/Documents/projects/audit_app/venv/bin/python \
  docs/admin/implementation/batch9-bootstrap-evidence/record.py replay-process \
  /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest \
  backend/tests/test_batch9_bootstrap_ownership.py -q -s
```

Choose a fresh receipt name; existing evidence is append-only. All exact prior
commands/environment values are in their JSON receipts. The primary runtime was
executed read-only. The owned minimum runtime is
`.local-dev/batch9-bootstrap-min/venv/bin/python`, installed from the backend
requirements plus pytest/pytest-asyncio/flake8 and pinned `SQLAlchemy==2.0.23`.
Its CPython archive was
`cpython-3.12.15+20261009-aarch64-apple-darwin-install_only.tar.gz` from
astral-sh/python-build-standalone release `20261009`, SHA256
`83dcb04777c798bd95f3687acf9ae84b09860272ee6bdfb05be8bcf9447f75b8`.

Review findings and independent limits are in `spec-review.md`,
`standards-review.md` and `adversarial/REPORT.md`.
