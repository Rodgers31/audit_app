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
the complete-cohort reader contract. Example: one revision among188observations
reports created0/updated1/skipped187, with188physical snapshot rows. Repeating the
same acquisition later reports created0/updated0/skipped188 and zero inserts.
Neither count grants social-generation or publication authority.

No existing history is consolidated automatically. Provider release identity,
retention/deletion authority, new source activation, social generation/publishing
and Free-plan operating acceptance are separate gates. This repair adds no
scheduler, service, dependency, credential or access grant.
