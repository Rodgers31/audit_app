# Evidence preservation and shared downloads (session 4)

This branch depends on PR #327 at `3ee591107535280839ff0763b3cf10ddf69ff876`.
It must not bring that unmerged diff into main. Apply only the focused session-4
commits after #327 lands. No production writes, seeding, migrations or deployment
were performed in this session.

## Replacement contract

A parser result is a candidate, not authorization to retire evidence. Automatic
runs accept validated additive findings, exact replay, and page-only moves when
the finding content, attribution, period, amounts, opinion and confidence agree.
They keep extraction IDs and audit IDs. A structurally incomplete re-read
(unresolved county chapters, skipped national chapters, unreadable text) refuses
replacement. An initial county read can bank attributed findings but reports
partial coverage, does not stamp the bytes as fully extracted, and retries.

A removal or content revision requires an explicit source review. Counts cannot
prove completeness: a truncated paragraph can have the same identity and row
count as a corrected paragraph. This conservative boundary means the #327
national walk upgrade will require a reviewed reconciliation before retiring its
old prior-year-table rows. A larger result does not implicitly authorize deletion.

`last_extraction_attempt` on the source records refusal, attempted source checksum,
error and the reconciliation proposal. The proposal records source URL and SHA256,
old/candidate hashes and counts, exact retired/revised extraction IDs, audit IDs,
and before/after content for affected rows. The ingestion result carries an error
and document detail; the CLI maps it to `COMPLETED_WITH_ERRORS`, never clean success.
Non-audit references veto both revision and deletion. Extraction and audit loading
share a savepoint, so loader errors restore the prior rows and source stamps.

## Deliberate reconciliation and recovery

This is an operator path, not automatic authorization to change production:

1. Read the persisted proposal and obtain the exact source bytes named by its
   SHA256. Check the actual report, every proposed retirement and revision, and
   whether the candidate covers its full source. Do not approve a partial parse.
2. Before any production application, obtain the coordinated database backup.
   Export the affected SourceDocument row, all its Extraction rows for this
   extractor, and their Audit rows with IDs and references intact. Preserve the
   prior and new PDF bytes separately; cache replacement is not a source archive.
   The proposal names the exact rows and before/after extraction content. No
   production row set was inferred or changed during this implementation.
3. On a clone, construct `review = {"proposal": proposal, "source_complete": True,
   "reason": "<specific source-checked rationale>"}`. Pass it to
   `extract_blue_book(..., review=review)` or
   `extract_county_volume(..., known_counties=..., review=review)` through
   `reconciliation.extract_and_load(..., parser, load_blue_book_extractions)`.
   Use `functools.partial` to supply the keyword arguments. Retain the candidate
   source file and rollback the clone transaction until the diff is verified.
   The accepted review is saved as `last_reconciliation_review`.
4. Changed source bytes, candidate rows, prior rows or audit identities invalidate
   the proposal. Generate and review a new proposal rather than changing hashes
   to force acceptance. An already applied, unchanged candidate is an idempotent
   no-op. Empty/malformed parser outputs remain refused; an empty publication
   requires a separately verified retirement proposal, not an automated parse.
5. Apply a verified proposal only within a coordinated production transaction.
   On validation failure rollback. If reversal is needed after commit, restore
   the backed-up source/extraction/audit rows by their original IDs, check all
   foreign keys, counts and publication queries, then commit. Coordinate caches
   and deployment with the parent release task; do not restore by deleting a
   whole table or re-running an old fixture.

## Executed receipts

- #327 baseline: six unsafe candidates failed the preservation assertion; the
  unchanged control passed. Empty/fewer/malformed candidates deleted rows;
  same-key truncated content overwrote evidence.
- New guard plus positive controls: additive findings, page-only reissues,
  reviewed correction/retirement, replay, stale approvals, malformed values,
  foreign references, storage failure, loader rollback and persisted domain errors.
- Independent adversarial run found three gaps in the first implementation:
  cross-extractor schema, revised foreign evidence, and first partial county
  reads stamped complete. All three were reproduced red and fixed. A later confidence-only foreign-reference gap was also reproduced red and fixed; the final independent pass had 20/20 probes passing.
- 159 focused tests pass. Core preservation suite also ran on isolated PostgreSQL
  17: 40 passed (including savepoints and real foreign keys).
- Broad #327 suite at the preceding implementation revision: 4,637 passed,
  12 skipped, 9 failed. The nine failure names match untouched main's integration
  baseline; final refinements were rechecked in the 159 focused tests.
- Pending bills previously discarded banked partial bytes and reused old cached
  bytes after a reissue: two red tests. It now uses `download_cbirr`, preserving
  the common fingerprint and resume sidecar. Interruption/resume, byte-for-byte
  completion and genuine replacement tests pass (24 download tests).

Tests used fixtures, mock HTTP streams and isolated databases. No real email was
sent and no production cleanup was executed. Production adoption remains open
under #322 and the parent release checklist #323.
