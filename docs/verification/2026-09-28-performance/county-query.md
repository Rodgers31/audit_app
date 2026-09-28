# County and federal audit query performance — issue #354

Base: `37c6c37c565b3190ae0f72fb5fa895daf68abe24`. Worktree:
`/Users/roger/.codex/worktrees/county-query-performance/audit_app`.

## Change

- `/counties` first selects only audit identity, date, severity, source and full provenance. It applies the existing Python display-grade gate to every publishable candidate, preserving counts and latest-audit choice. A second, single query fetches at most ten 200-character finding prefixes per county after that gate. Audit year remains independent of selected budget year.
- Accountability peer comparison selects only entity ID, amount, audit year and opinion. The same Python roll-up retains sourced zeroes, unknown amounts and opinion behavior.
- The cached federal payload still processes every publishable finding for the full API and all aggregates. Its main query projects only columns the payload reads, plus entity name/type; `top_findings` still trims the complete cached payload at the API boundary. Source-document and publication predicates are unchanged.

## Verification

All Python runs disabled dotenv, set an explicit inert database URL before imports for SQLite tests, disabled the auto seeder, and used an isolated in-memory SQLite fixture. No production database or environment file was used.

- **Red/green:** `python -m pytest backend/tests/test_county_query_volume.py -q` against the base `main.py`: **3 failed**, each after its endpoint's public output assertions passed. Failures showed full finding text/management response/entity metadata selected for county, peer or federal reads. With this change: **3 passed**.
- **Behavioral regression:** targeted county, period, publication, federal, headline and partial-amount files: **159 passed**. The new fixture includes withheld and modelled rows ahead of valid rows, malformed/dict/list provenance, source zero and absent amounts, a selected budget year newer than the latest audit, tied county timestamps, equal federal amounts, two federal fiscal years and peer grades/amounts.
- **Complete response comparison:** the same fixture captured `/counties?fiscal_year=2024/25`, `/counties/047/accountability`, `/audits/federal` and `/audits/federal?top_findings=2` before and after. After excluding the expected `_meta.generated_at` timestamp, all public JSON fields, values, array ordering and nulls matched: **38,933 bytes each**, identical SHA-256 `1ea2389b433843b158aea00d0a67a4321ed1361f17e6e0232c648017f621ec89`.
- **PostgreSQL 17 smoke:** disposable local `audit_perf_county` database, tables created from the models and dropped afterward. The county, peer and federal output assertions passed with PostgreSQL JSONB and enum types. Statement capture found **one candidate audit SELECT, one peer audit SELECT and one federal main SELECT**; county issue prefixes used one additional batched SELECT. No per-row audit lazy loads appeared. `pg_column_size` on the local county fixture estimated **14,356 bytes** for the old complete audit records versus **at most 741 bytes** for the narrowed records plus short issue text. These are fixture row-size estimates, not billed egress measurements.
- `git diff --check` passed.

## Limitations and separate issue

County provenance still has to be read for the Python display-grade gate. The complete federal API still needs every published finding's text and provenance. The local row-size estimate should not be extrapolated into a production egress saving without post-deployment measurement.

An existing federal correctness bug was reproduced separately and left unchanged: with four published findings whose stored and provenance amounts are all sourced `KES 0`, `/audits/federal` returns `findings_with_amount: 4` but `total_amount_in_findings: null`. In `_federal_audits_payload`, `if amount_str and amount_val` treats numeric zero as absent. The coordinator filed [#358](https://github.com/Rodgers31/audit_app/issues/358), linked to the related money-flow sourced-zero issue [#352](https://github.com/Rodgers31/audit_app/issues/352).
