# Audit query projection receipt — issue #353

## Change

- `/api/v1/audit/findings` selects the fields used in its response, the three extraction identity keys, and only `source_documents.metadata.extraction_stats`. Its count query selects only the count. It never materializes an ORM `SourceDocument`, `Extraction`, `Entity`, or `Audit` that could lazy-load omitted fields.
- The unaccounted-cases prefilter selects the response fields, six extraction context keys, and only the source document's `extraction_stats` subfield. Its bodyless-finding table-row scan selects four JSON keys and identifiers rather than complete extraction records. Historical extraction JSON stored as a serialized string is fetched separately and parsed as before.
- Freshness selects only `metadata.publication_date` from accepted source documents. The existing strict ISO/date and publisher checks remain in Python.
- The retained `last_extraction_attempt` evidence stays in storage. Cache behavior, publication rules, response fields, filters, ordering, and TTLs are unchanged.

## Local verification

All commands set `DATABASE_URL` explicitly before imports. They used in-memory SQLite fixtures or the coordinator's disposable local PostgreSQL database `audit_perf_audit`; no production database or `.env` was used.

The new regression fixture includes a 220 KB retained diagnostic in a document shared by findings. It replays each selected SQL statement on the same isolated connection and counts the UTF-8 bytes of selected DBAPI values, including fields later discarded by the API. These are comparative selected-value measurements, not packet captures or billable egress totals.

| Query and fixture | Original query | Projected query |
| --- | ---: | ---: |
| Findings page with two rows sharing a source document | 440,922 bytes | 325 bytes |
| Unaccounted prefilter with two rows sharing a source document | 441,231 bytes | 537 bytes |
| Accepted source publication date, one document | 220,297 bytes | 12 bytes |
| Findings page with two extraction records carrying unused diagnostics | 440,476 bytes | less than 10,000 bytes |
| Unaccounted prefilter with two extraction records carrying unused diagnostics | 440,701 bytes | less than 10,000 bytes |
| Bodyless case scanning five extraction records, four diagnostic-rich | 880,949 bytes | less than 10,000 bytes |

The original three fixture tests were run against commit `37c6c37c565b3190ae0f72fb5fa895daf68abe24` before implementation and failed on the selected-byte assertions after their response assertions passed. The extraction and bodyless-path fixtures likewise failed against their respective pre-fix queries and pass after projection. Cases include county assembly identity derived from document context, a conflicting executive declaration, national identity, missing and malformed metadata, pagination, page links, a sourced zero, a withheld record, and string-encoded extraction JSON.

Command: `DATABASE_URL=postgresql://postgres:password@localhost:5432/audit_app /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest backend/tests/test_audit_query_payload.py backend/tests/test_audit_dashboard.py backend/tests/test_audit_dashboard_absence_and_labels.py backend/tests/test_audit_findings_source_url.py backend/tests/test_audit_citations_conflicts.py backend/tests/test_audit_headline_derived.py backend/tests/test_freshness_publication_evidence.py backend/tests/test_audits_publication_gate.py -q`

Result: **164 passed**, two existing SQLAlchemy deprecation warnings. The national citation fixture now retains its entity ID before calling an endpoint that closes the shared test session; the old ORM query happened to refresh that test object as a side effect.

PostgreSQL 17 smoke command: `DATABASE_URL=postgresql+psycopg2://audit_perf:local_test_only@127.0.0.1:55437/audit_perf_audit /Users/roger/Documents/projects/audit_app/venv/bin/python /tmp/audit-query-pg-smoke.py`. It created and dropped only the seven fixture tables in its assigned disposable database. With oversized diagnostic keys in both the document and extraction JSON, findings selected **390 bytes** across one count and two detail rows (1 + 26 selected columns), unaccounted cases **501 bytes** across two case rows and a two-ID publication check (22 + 1 columns), and freshness **10 bytes** (one column). A separate bodyless scan selected **301 bytes** across seven rows (seven columns). The expected labels, source page links, case count, publication date, and string-encoded JSON fallback matched.

## Limits

The byte figures come from deliberately small local facts plus oversized retained diagnostics. They prove those diagnostics are absent from selected results; they do not estimate the production quota reduction or attribute the previous billing cycle. Serialized-string extraction rows still require a full-payload fallback to preserve historical parsing, limited to those rows. No further actionable issue was found in this scope.
