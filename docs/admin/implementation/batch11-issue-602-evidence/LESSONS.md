# #602 lessons proposed for coordinator skill updates

Proposals only; shared skills and SPEC are unchanged. Each item cites the
receipt that demonstrated it.

1. **An ORM mutation of a JSON column can silently not happen** (state-persistence-invariants,
   regression-fixture-on-fix). Assigning a dict that is `==`-equal to the stored
   one (`{"schema_version": True}` vs `1`, `39.0` vs `39`) is treated as unchanged by
   SQLAlchemy and no UPDATE is issued. A replay test that "tampers" stored JSON
   that way passes or fails for the wrong reason. Mutate in SQL (`jsonb_set`) and
   read the raw `::text` back before asserting. Receipts: red-01 (ORM mutation,
   inconclusive) vs red-02 (SQL mutation, genuine red on writer `55aa7263…`).
2. **Type-strict identity for replay guards** (generative-boundary-tests). Python
   equality equates `True == 1 == 1.0`; compare canonical JSON
   (`json.dumps(sort_keys=True, allow_nan=False)`) plus explicit `type(x) is int`
   for columns. Receipt: writer boundary tests red-02 → green.
3. **Parse a publication's table by reviewed position, not by searching header
   text** (verify-boundary-shapes, no-silent-fallbacks). Substring checks accepted
   "Not Recommended", "Previously Recommended" and "FY 2026/270", and "last amount
   in the row" accepted swapped columns. Exact header cells by position plus the
   table's own arithmetic identities (baseline + adjustment = recommended, totals,
   "of which" lines) refuse all of them. Receipt: red-01/02 parser cases.
4. **Bound decimal inputs before arithmetic; prefer integer minor units**
   (generative-boundary-tests). The default 28-digit Decimal context rounded a
   32/33-digit cell pair into a "reconciled" total. Receipt: retained
   `table-decimal-context-rounding` red → green.
5. **A suite runner must reproduce CI's fixture settings, not just its
   databases** (verify-test-prod-parity, prove-baseline-alive). The draft cohort
   built the reconciliation template in an autovacuum-enabled container; CI's
   preparer forces `autovacuum=off` because autovacuum workers appear in
   `pg_stat_activity` and trip the fenced-maintenance refusal. It also pointed
   `DATABASE_URL` at an inert port, turning a mandatory PostgreSQL case into a
   connection-refused error. Receipt: full-core-current-01 (historical) vs the
   autovacuum A/B probe and the final full run.
6. **A hard-coded "current head" goes stale on every new migration** (#613
   recurred one PR later). Derive readiness from the repository's single ordered
   head and refuse two heads. Receipt: red-03 → green-03.
7. **zsh does not word-split unquoted variables**; a test list in `$T` became one
   bogus path (cohort-current-03 setup failure, preserved). Use arrays.
8. **A recorder must return nonzero unless the run is green, complete and
   drift-free**; printing `complete: false` while exiting 0 let a wrapper report
   success. Receipt: cohort-current-03 `suite.json` (historical) vs record_v3 fix.
