# Exact OAG prior-year boundary correction (#379)

This is a release proposal, not a production write receipt. The merged parser
does not refresh unchanged county-volume extractions. Use the exact correction
tool rather than running a broad seed, deleting rows, or rewriting API strings.

## Reviewed scope

Official FY2024/25 Assemblies PDF:
`https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-ASSEMBLIES-2024-2025-1.pdf`

- PDF SHA256: `aa72b0a512fe01ce8f40b9ed8597bd78657a9f441a8daf4963b07e661104d896`
- PDF MD5: `f495cb595c81583af7d8bbd46e2279d6`
- Exact reviewed manifest: `backend/tests/fixtures/oag_boundary_reviewed_manifest.json`
- Manifest SHA256: `8504dd3243d56a5de8b98eea717faf0c8de484be3e3b28a00b2c8342c0228961`
- Source replay: 47 chapters / 582 findings; 579 identical; three text changes;
  finding identities and all other parser fields identical.
- Source document 2541, FY2024/25 period 1, audit year 2025. A fresh read-only
  database observation on 30 September 2026 confirmed the before-state below.

| Audit / extraction | Institution / reference | PDF / printed page | Text characters before → after |
| --- | --- | --- | --- |
| 5545 / 6023 | Narok Assembly / `OAG-CV-2024/2025-A33-P453` | 168 / 155 | 1251 → 500 |
| 5679 / 6158 | Migori Assembly / `OAG-CV-2024/2025-A44-P603` | 221 / 208 | 1640 → 713 |
| 5716 / 6196 | Nairobi City Assembly / `OAG-CV-2024/2025-A47-P645` | 239 / 226 | 5548 → 586 |

The immutable manifest retains full before/after texts and their SHA256s. The
three current conclusions end before separate historical tables. Historical
evidence remains in the original cited PDF. No historical table is promoted
to a current-year finding.

## Mechanism and guards

`scripts/verification/oag_boundary_correction.py` replays both pinned baseline
and current parsers against the exact PDF. It checks the entire source walk's
identity/metadata/change scope, then the three stored audit IDs, extraction
IDs, references, institutions, Kenyan country, fiscal period, pages, source URL,
MD5, extraction metadata, payload, source hash and loader provenance. Public
county/query labels are compared to their underlying canonical source fields,
not mistaken for raw stored labels. It requires the shared publication gate
before and after the correction; it never changes a publication flag.

Prepare records every column of the three audits, extractions, documents,
entities and periods, including columns absent from the current ORM. The plan
is deterministic for the observed database state. Default operation uses a
PostgreSQL repeatable-read READ ONLY transaction, verifies
`transaction_read_only=on`, sets an 8s statement timeout and rolls back. It
does not issue correction DML during a dry run.

Commit requires the exact plan plus its independently reviewed digest and a
new recovery-receipt path. It locks `audits` and `extractions` against concurrent
writers/inserts with a 2s lock timeout, locks the selected related rows,
revalidates every snapshot and refuses drift. These short table locks can
temporarily block other audit ingestion; schedule outside the nightly writer.
Only three extraction payload texts and three audit texts/source hashes change.
Source hashes use the existing loader's canonical payload hash function.

The tool fsyncs an exclusive, immutable recovery receipt before DML. The
receipt deliberately records **intent**, not a possibly misleading commit
claim. If the process dies during commit, inspect the database against both
receipt snapshots to determine whether the transaction committed. Do not infer
success from the receipt's existence. It contains the exact original plan.
Any exception or postwrite mismatch rolls back all DML. Recovery validates the
same source/manifest and the exact after-snapshot before reversing only these
columns. Intervening new evidence makes recovery refuse rather than erase it.

## Owner-reviewed release sequence

1. Independently review this code, source pages and the manifest. Confirm the
   deployed parser fix remains available. Keep the broader national refresh
   and legacy cleanup outside this operation. Arrange an ingestion-free window.
2. Use a safe Python runtime with `PYTHON_DOTENV_DISABLED=1` and the repository's
   pinned baseline Git object `c76ad74877dcd29a284b548c928f59538553fa0f` available
   to `git show` (the source replay requires it). Explicitly provide
   the intended PostgreSQL connection in `OAG_BOUNDARY_DATABASE_URL` using the
   owner's normal secret mechanism. The tool never loads `.env`, never uses
   a default `DATABASE_URL`, and never prints the connection string. Do not
   paste production credentials into command receipts.
   Remote TCP URLs must explicitly include exactly one `sslmode=require`,
   `sslmode=verify-ca`, or `sslmode=verify-full`, matching the connection rules
   in `docs/local-development.md`. No other query options or drivers are
   accepted. The CLI pins the installed `psycopg2` driver for `postgres://`,
   `postgresql://`, and `postgresql+psycopg2://` URLs and enforces the selected
   TLS mode at the driver boundary with an 8s connection timeout. It pins
   `gssencmode=disable` so the libpq GSS preference cannot replace TLS (see
   [PostgreSQL connection options](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNECT-SSLMODE)). Use the
   driver's normal trusted certificate configuration for verification modes.
   Only exact loopback hosts (`localhost`, `127.0.0.1`, `::1`) may omit TLS;
   their local address is pinned so `PGHOSTADDR` cannot redirect this exception
   remotely. Explicit weak modes (`disable`, `allow`, `prefer`) are refused.
   Both host and database must be explicit. CLI failures report only the
   exception class, because driver error details can contain a connection URL.
3. Prepare a **fresh read-only plan**. Review the complete diff and digest;
   source/row timestamps can drift, so do not reuse a stale observation blindly.

```sh
python scripts/verification/oag_boundary_correction.py \
  --pdf /path/to/hash-verified-assemblies.pdf \
  --manifest backend/tests/fixtures/oag_boundary_reviewed_manifest.json \
  --output /secure/release/boundary-plan.json
```

4. Review the expected change set: three `extracted_json.finding_text` values,
   three `audits.finding_text` values and their three `source_hash` values.
   All IDs, amounts (null in these findings), severity, status, recommendations,
   responses, provenance, publication state, source links and periods stay
   identical. The 30 September live READ ONLY plan was
   `57a73173edaa838a589c3e5e5a091042da801db3a23c6d8050ab6b0ced36338a`;
   it is an observation for review, not authorization or a permanent release key.
5. Run the reviewed plan without `--commit` first. Only after the owner's
   separate production authorization, add `--commit` and a fresh receipt path:

```sh
python scripts/verification/oag_boundary_correction.py \
  --pdf /path/to/hash-verified-assemblies.pdf \
  --manifest backend/tests/fixtures/oag_boundary_reviewed_manifest.json \
  --plan /secure/release/boundary-plan.json \
  --expected-plan-sha256 REVIEWED_PLAN_DIGEST \
  --output /secure/release/boundary-recovery-intent.json \
  --commit
```

6. Independently read the three stored audits and authoritative payloads in a
   READ ONLY transaction. Verify exact after-text/source hashes, unchanged IDs
   and fields, and continued shared-gate eligibility. Clear only relevant audit
   response caches through the normal release process if necessary; this tool
   does not flush Redis or restart services. Fetch both bounded public finding
   pages, check each ID against the manifest's after-text hash, and visually
   check the cited paragraphs and current finding rendering. Verify a subsequent
   normal loader run does not restore the old text. Keep #379 open until those
   public checks pass.
7. If rollback is necessary, run the original plan with the same digest and
   `--recover`, first without `--commit`, then after owner authorization with
   `--commit` and a new receipt path. Recheck the public before-state. The tool
   refuses recovery after unrelated intervening edits; escalate that drift for
   a new reviewed plan instead of forcing a rollback.

## Separate shared-version national impact

A 30 September READ ONLY inventory found three documents with
`oag_blue_book` extractions and no version stamp: 2392 (national FY2024/25,
813 stored extractions), 2395 (legacy county executives FY2020/21, 986) and
2396 (legacy county assemblies FY2020/21, 512). They fail the current version-3
`extraction_is_current` condition; the county-volume MD5 skip is separate.

The actual current national source was fetched and matched document 2392's
MD5 `7e6a6850102a3cadcba38e1f7af9cae3`, SHA256
`d8c72b4fbda2c920f30f79b3e0554f9965165735d220a810e6ae3994e2dbf899`.
Both pinned version-2 and current parsers produced 1867 findings across 915
pages, with **no added/removed identities, text or metadata differences** from
this boundary change. OCR-disabled replay rejected cover page 1. The parser
count differs from 813 stored extractions; this receipt does not establish why
or authorize expansion. A broad current extraction would also encounter its
unreadable-page gate unless OCR succeeds. Do not stamp those documents as
accepted, re-extract, delete, or widen this correction on that basis. Any broader
refresh needs its own source/payload/coverage/reconciliation rehearsal and
retirement review. This tool touches only document 2541's three reviewed rows.

## Executed acceptance and limits

- Disposable PostgreSQL 16 clone using captured audit/extraction/source/period
  shapes and synthetic entity-profile/unrelated controls: prepare, READ ONLY
  apply, commit, future real loader preservation and guarded full recovery.
- Midwrite trigger failure rolled back both copies; inaccessible or existing
  recovery files refused before mutation. Wrong row/source/institution/period,
  extraction/provenance drift, missing/malformed artifacts, and JSON numeric
  type drift refused. Independent probes verified a blocked concurrent writer,
  recovery after evidence drift, and PostgreSQL rejection of injected default
  DML. Exact-comparison defects were independently reproduced red then green.
- Full CLI prepare → dry-run → commit → recovery succeeded against a disposable
  PostgreSQL schema and restored the complete synthetic inventory.
- Connection regression tests execute CLI parsing and the actual SQLAlchemy
  engine/DBAPI boundary with network calls intercepted. They verify all three
  remote TLS modes, driver pinning, loopback environment-redirect protection,
  refusal of missing/weak TLS and unsupported options, and URL-free failures.
  The revised CLI also completed prepare, dry-run, commit and recovery on
  disposable PostgreSQL with conflicting `PGHOSTADDR`, `PGSSLMODE` and
  `PGGSSENCMODE` values;
  the full synthetic inventory was restored. The bounded follow-up passed
  44 connection and affected persistence tests, including atomic rollback,
  unrelated JSON-type preservation and future-loader/recovery controls.
  These tests do not establish a remote TLS handshake or certificate validity.
- No production write, seed, deletion, cache flush, deployment, GitHub Actions
  run, paid review or issue closure occurred. Tests do not establish power-loss
  durability or complete source accuracy outside the reviewed scope.
