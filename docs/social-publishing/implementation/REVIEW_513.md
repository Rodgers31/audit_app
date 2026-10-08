# PR 513 review receipt

Review baseline: `c559635`. The saved review contains two concrete findings;
the overview's additional maintenance/preview wording supplies no separate
reproduction or actionable location.

[Legacy cleanup finding](https://github.com/Rodgers31/audit_app/pull/513#discussion_r4220745043):
**valid, understated**. A ready upload with a historical cleaned quarantine flag
was excluded from cleanup and rejected by reconciliation. Version-one rows could
retain pending capacity; version-two rows could still have unknown browser
writes even though pending capacity was already released. Four SQLite cases and
two cases seeded before the actual PostgreSQL settlement migration failed with
`UPLOAD_NOT_PENDING` before the fix.

The migration keeps its conservative backfill. The runtime now permits an
unreleased ready row's scoped reconciliation when uncertainty or held pending
capacity remains. An unsupported verifier leaves the historical marker, unknown
epochs and all reservations intact. Trusted confirmation resets the quarantine
marker so cleanup requires a fresh confirmed DELETE; the historical DELETE is
never treated as proof that a later browser PUT did not recreate the object.
Failed DELETE retains capacity. Ready cleanup releases only reserved excess over
the original's declared size, preventing a second decrement of a historical
one-copy reservation. Settled cleaned ready rows cannot reopen cleanup, and fully
released legacy hazards remain an explicit inventory/backlog acceptance boundary.

The regressions cover held/already-released pending capacity, one/two-copy
reservations, failed-delete retry, once-only release, retained ready originals,
and both actual migrated legacy versions. No schema normalization fabricates
settlement or restores missing legacy accounting.

[Timestamp finding](https://github.com/Rodgers31/audit_app/pull/513#discussion_r4220745125):
**not reproduced; the cited mechanism is incorrect**. `now` is captured in the
first locked transaction and remains the lower evidence bound. The second
transaction samples a separate `current` for the upper bound and lease checks.
No timestamp implementation change was made. The new actual PostgreSQL test
`test_pg_reconciliation_accepts_receipt_between_its_locked_transactions` passed
against the review baseline, asserting first-transaction time < verifier database
time < second-transaction time while accepting the receipt and retaining quota.

Post-fix validation: 90 maintenance, cleanup and actual PostgreSQL migration
tests passed, with no skips. The assigned disposable domain database uses random
schemas; no worker truncation, live storage, provider calls or runtime enablement
was performed. Operational issue #490 still requires its separate real
bucket/host/inventory/write-drain acceptance.

Independent review: the root agent executed 78 maintenance/migration PostgreSQL
tests and reviewed the ledger changes. The scheduling agent separately executed
102 fake-storage/SQLite probes: 60 invalid receipts, 36 scope/claim/readiness
races, four fresh-delete/accounting/reference positives, one reference insertion
during external DELETE, and one healthy baseline. All passed; neither review
found an additional defect.
