# Nightly audit recovery: #812 and #814

Base release: `6fdce855950e94cb30c43dfdcd8307885795b3cf` (#816).
This change repairs two audit-ingestion boundaries. It does not raise the
600-second domain or 1,320-second run limits, authorize another hosted refresh,
change source/publication contracts, or activate publishing/uploads/workers.

## Typed review receipt (#812)

The held review is `oag-2542-20261026`, source document 2542, with 23 revisions
and zero retirements. The retained proposal export lost integral-float JSON
representation on nine BEFORE and nine AFTER amount literals across six rows.
Python equality does not distinguish those values from integers, but the strict
JSON digest does. Isolated PostgreSQL JSONB preserves the floats; a separate
JavaScript JSON parse/stringify control reproduces the representation loss.
The original historical export operation was not re-executed.

Regenerate the expected proposal digest and the twelve documentary checksums
(before/after on extraction IDs 4704, 4869, 4978, 5412, 5544 and 5614) from the
actual source/ORM proposal. Keep all other review metadata unchanged. In
particular, do not normalize numbers globally or relax the review algorithm.

| Boundary | SHA-256 |
| --- | --- |
| Exact 688-page source PDF | `033e2aa26aa77351ec46f062573f25ede47d3e3a99978aeacf9a66af5ba717a5` |
| All 1,269 previous rows, IDs and typed payloads | `665f73daf550ce77114683ddadb8d84d575380b17b27a749aac005acd3f9a956` |
| Complete candidate content without artifact binding | `4161605e45f79c7e0e89b4ed71cb811308fe39db06e816bfa13b165623cc4330` |
| Correct fresh proposal content | `0fe0ac4927fcf93e4fdd52f1b1a6c6b5fe9bbee15e231037cde7a2a6167b9b3f` |
| Corrected canonical review manifest | `b612f59661322355f93c05a85964bfe539e7738922af99f0c88ab0ec35a214c9` |

The old `f404...` proposal expectation and `9cf...` manifest describe the
failed hosted attempt; retain that history. An intermediate `2dcc...` proposal
fixed only AFTER values and is not accepted. Source/candidate/previous-state
hashes, every extraction/audit association, amounts, fiscal years, county
attribution, page citations and the zero-retirement decision remain strict.

`test_oag_review_source_postgres.py` consumes externally supplied, hash-pinned
PDF/proposal assets and a private PostgreSQL fixture. It reconstructs the full
previous state, proves its digest before and after a real ORM/JSONB round-trip,
then invokes the actual review guard against the actual candidate. The PDF and
raw findings are not committed. Missing assets/fixture cause an explicit skip;
that skip is not source acceptance. Retain raw Python-generated proposal bytes
before any browser/JavaScript transport when preparing future review receipts.

This fixture explicitly disables OCR: it qualifies typed source/receipt
integrity, not the deployed OCR toolchain, production roles, migrations or a
complete hosted extraction/loader run. The full candidate-content hash remains
the refusal boundary if the deployed runtime produces different output.

## Bounded audit updates (#814)

The failed hosted refresh reached a psycopg2 `executemany` update of 1,047
existing audit facts. That driver operation sends individual update commands.
PostgreSQL now receives at most 100 facts in each `UPDATE ... FROM VALUES ...
RETURNING` statement: at most eleven payload-update commands for that case.
This is a command-count reduction, not a claim about deployed elapsed time.

Audit IDs must be distinct across the entire operation, before any writes.
Each batch matches audit ID, source document, extraction ID and previous source
hash; returned IDs must equal the intended set. Missing/stale rows refuse the
operation without an upsert. One nested transaction covers all batches and new
facts. The caller retains commit, source-savepoint and publication ownership.
The existing SQLite path remains available for its fixtures.

Only the ten existing update fields are written. Unrelated operator fields are
preserved. Typed SQL casts preserve all-null values and enum/JSONB handling;
unknown amount and explicit zero remain different. Expiration in a `finally` block plus SQLAlchemy's public `flag_dirty` registers
identity-map rollback custody on success and failure without producing a second
ORM payload update. This includes a row refreshed while an early batch is in
flight before a later batch refuses.

The private PostgreSQL suite exercises 205 and 1,047 changed rows, idempotent
replay, outer rollback, rollback after an ORM refresh, missing later rows plus
pending inserts, duplicate identities across batches, an ORM refresh during a
subsequently rolled-back batch, and a separately committed concurrent source-hash
change.
These tests use only an owned isolated schema and explicitly checked loopback
fixture identity; they must not target an application database.

## Release and acceptance boundary

Review and local fixture acceptance do not close either issue. Deployment and
a separately authorized bounded live refresh must confirm the exact new
manifest, update-command reduction, later-domain progress, claim release,
source/publication validation and physical cleanup. Preserve visible partial
and not-run outcomes. The prior refresh authorization has already been used;
this handoff does not authorize another run or an admitted-SHA change.
