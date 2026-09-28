# PR #360 federal review follow-up

Base: `78ceb7ec55357737129bc712b461b3ee0eac73cc` on
`origin/codex/supabase-query-performance`. Review branch:
`codex/pr360-federal-review`.

## Disposition

Copilot's overview named federal cache fencing and downstream projections, but
did not attach an inline federal finding. Both claims were checked against the
branch rather than treated as instructions. The one inline comment concerns
Docker and is owned by the coordinator; the derived-audit N+1 review is owned
by the audit-derived session.

- **Valid cache race:** `main.cached` keyed by route and arguments alone. A
  federal load that began before signed invalidation could finish afterward,
  refill the same key and serve stale findings for the normal one-hour TTL.
  The same decorator has 30 callers, so its key now includes the generation
  identity captured before loading. A late fill remains under the old key for
  every caller; the next request uses the new key. Existing argument filters,
  transient-failure TTLs and response shaping are unchanged.
- **Valid source overfetch:** the federal report-title lookup hydrated a whole
  `SourceDocument`, including internal metadata, while the payload uses only
  ID, title, publisher and fetch date. It now selects those four columns.
  Publication and report-year filters, ordering, headline source ID, and
  `last_updated` inputs are unchanged.
- **Full versus homepage contract preserved:** `/audits/federal` still uses
  the complete cached payload. `?top_findings` returns a new dict with a
  selected findings list; other summary fields still describe every finding.
  Server prefetch and the homepage hook request the same trimmed API form.

## Executed evidence

Tests ran with dotenv disabled, an explicit inert local database URL and the
auto seeder disabled. The SQLite fixture database was isolated; no production
database or environment file was accessed.

- New forced interleaving test: start a federal load, pause at its output
  boundary, invalidate the cache, release the old load, then read again.
  **Red on base:** the second result carried the old fixture version.
  **Green after:** the second result carried the new version.
- Generic `main.cached` forced interleaving test: **red on the unfenced
  decorator**, **green after the shared key change**. This pins the invariant
  for the other 29 routes as well.
- A 64 KB internal `SourceDocument.metadata` fixture: **red on base** because
  the report-source SELECT included metadata; **green after** with the same
  public report title and one four-column source SELECT.
- Focused federal, publication, provenance, county-query and response-cache
  suites: **114 passed**. These include full → trimmed → full ordering,
  withheld records, sourced zeroes, fiscal-year coverage, cache cancellation
  and failure recovery. Python compilation and `git diff --check` passed.

The source fixture measures selected columns, not production egress. This
round does not change the already recorded sourced-zero correctness issue
[#358](https://github.com/Rodgers31/audit_app/issues/358). No review reply,
push or PR update was made from this worktree.
