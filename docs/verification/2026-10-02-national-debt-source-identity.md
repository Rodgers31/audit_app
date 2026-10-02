# National debt source identity preflight — 2 October 2026

Issue #274: the configurable JSON path allowed null/empty source titles with no
locator to create a display fallback document repeatedly. The full writer also
reconciled external creditors and deleted subset loans before looking up sources.

Every parsed record now requires a nonblank recorded locator or a declared title.
The writer validates the entire batch before its first session query or mutation;
the source helper enforces the same rule for direct calls. Missing/null/blank
payload titles remain undeclared. Absent row fields may inherit the payload's
source, but malformed types remain visible for refusal. A row with a different
locator does not inherit the payload's title or publisher. Monetary/date parsing
and the existing handling of unrelated malformed loan fields are unchanged.

Identity labels are trimmed for lookup/storage without mutating caller records.
Nontext and nonprinting labels are refused, including unencodable Unicode;
errors name the parsed record number and field without echoing source values.
Locators retain the existing HTTP(S), file and local-path forms. This prevention
patch does not add an HTTP scheme or fetch policy. Literal spaces and `%20` stay
equivalent; reserved `%2F` and distinct edition URLs stay distinct.

A locator-only source may still need a display title. Newly created sources record
`metadata.national_debt_title_is_display_fallback`. Title-only lookup excludes
sources marked true, so an unrelated genuine declaration cannot match that
created display title or change its publisher. A declaration for the same locator
can replace its generated title and clear the marker while preserving the source
ID and other metadata. The declaration is explicitly flushed because application
sessions disable autoflush, and later records in the valid batch may use it.
A real declared title spelled `National Treasury Debt Bulletin` remains valid.
Legacy unmarked titles keep their existing identity: historical declaration
provenance cannot be inferred from spelling. No stored cleanup or backfill occurs.

The actual domain already catches writer errors and returns `Write failed:` in
`DomainRunResult.errors`, with zero created/updated counts; configured-file tests
exercise that path without a domain refactor. The CLI's existing handling records
such results as `completed_with_errors`, rather than clean success.

The initial 26-case baseline run, after launcher repair, produced 19 failures and
7 passes. Expanded baseline execution used exact parser/writer blobs from
`748eea8e0d67f1a8a2337d18fe692d803455d820` rebound in the real domain modules:
32 failures and 10 passes. The fallback-title collision was independently found
and reproduced red before its correction. Six Unicode identity cases were also
seen red before hardening. Final focused execution: **142 passed, zero skips**,
including all 51 new identity cases, source publisher, full writer, fetcher,
external reconciliation and interest/API controls. Critical flake8 and whitespace
checks passed. Independent reviewer receipts are external to the repository.

These are local SQLAlchemy SQLite controls, with application-engine connections
and unstubbed outbound HTTP refused, dotenv/Pydantic env files disabled, synthetic
loopback settings, inert lifespan, seeder/warmup off and Redis empty. They do not
establish PostgreSQL or production adoption. Document1840 publisher correction,
historical source provenance and public acceptance remain separate inputs to
#274. No production data/configuration/cache writes, push, PR, GitHub mutation,
Actions run or dependency change was performed.
