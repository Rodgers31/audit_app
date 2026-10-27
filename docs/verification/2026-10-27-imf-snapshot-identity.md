# IMF acquisition and revision identity (#825)

An IMF DataMapper check is not an authoritative publication date. The existing
`vintage` column records acquisition time for a retained observation cohort;
historical rows are preserved without purging or redating. Successful unchanged
checks are recorded by the ordinary ingestion job, not another set of facts.

The debt readers select one country-wide snapshot to keep debt, GDP and other
indicators comparable. Therefore a meaningful revision retains a **complete**
country cohort. Inserting only the changed rows would silently hide unchanged
companion observations from those readers. A new fetch timestamp alone never
constitutes a revision.

The writer compares identity `(country_code, indicator, year)` and stored content
`(value, is_projection, source)` against each country's latest retained cohort.
Values use PostgreSQL Numeric(20,4) rounding; null and zero remain distinct.
An unchanged acquisition inserts zero rows. A changed/new observation retains
the complete incoming cohort at its newer acquisition time. A→B→A revisions
remain three real states; comparison is against the latest state, not all history.
An incomplete response, conflicting same-time capture, changed older capture,
duplicate identity, malformed value or over-limit snapshot refuses the whole batch.

PostgreSQL requires READ COMMITTED and takes a short NOWAIT table-write lock
before reading current state. A pre-existing repeatable-read snapshot would
remain stale despite the lock, so that invocation refuses without resetting or
rolling back its caller's transaction.
This serializes cooperating and legacy writers without blocking ordinary readers.
A competing write refuses rather than acknowledging unverified progress. A
savepoint encloses comparison and insertion, and the caller retains outer commit
and rollback control. SQLite is supported for local tests; the production
concurrency guarantee is qualified on PostgreSQL. No schema migration is needed.

Ingestion `created` counts newly observed identities and `updated` counts actual
content revisions. `skipped` counts unchanged observations. Metadata separately
reports `snapshot_rows_inserted`, which can exceed meaningful changes because of
the complete-cohort reader contract. Example: one revision among 188 observations
reports created 0 / updated 1 / skipped 187, with 188 physical snapshot rows. Repeating
the same acquisition later reports created 0 / updated 0 / skipped 188 and zero inserts.
Neither count grants social-generation or publication authority.

The fetcher requests all available years for the four Kenya indicators; it does
not truncate acquisitions to a dashboard window. The 512-row writer bound and
prior-identity completeness guard still apply.

A successful live write records each country's exact retained acquisition pointer
in ingestion metadata (`imf_retained_vintages`). The public broader-debt reader
qualifies a completed, non-dry-run live job against its closed native ownership
receipt and the current Kenya cohort. It overlays `last_successful_check_at`,
`check_age_days`, `freshness_basis` and `stale` outside the numeric cache. The
retained `vintage` and `vintage_age_days` continue to describe the observation
cohort. Failed, fixture, dry-run, future, mismatched or operator-reconciled
receipts cannot freshen it. Without a qualified receipt (including older jobs
that predate this metadata), freshness conservatively falls back to acquisition
age. Optional missing job/claim tables are checked before querying them.
PostgreSQL job times use the same session-timezone interpretation and five-second
app/database clock tolerance as native terminal qualification; future check times
must actually elapse before the public reader uses them.

No existing history is consolidated automatically. Provider release identity,
retention/deletion authority, new source activation, social generation/publishing
and Free-plan operating acceptance are separate gates. This repair adds no
scheduler, service, dependency, credential or access grant.
