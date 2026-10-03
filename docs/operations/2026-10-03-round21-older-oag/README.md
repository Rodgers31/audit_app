# FY2020/21 OAG completion plan — 3 October 2026

This is local source proof and a guarded adoption plan for issue #234. No
production operation ran in this lane. The completed five-volume operation and
376 newer county/institution/year cells are not repeated or reclassified.

## Source evidence and defect

One acquisition per exact recorded official URL returned HTTP200 with matching
historical MD5 and SHA256. The [replay receipt](replay-receipt.json) records URLs,
bytes, hashes, runtime versions, actual full-reader results and artifact digests.
The acquired files and images remain in the owned worktree's
`.local/round21-older-oag/`; shared caches and dependencies were not changed.

| Source | Pages | Native unreadable pages | Real OCR | Plain cover | Findings | Confirmed chapters |
| --- | ---: | --- | --- | --- | ---: | ---: |
| 2395 executive | 469 | 465,469 | 465 | 469 | 986 | 47 |
| 2396 assembly | 232 | 227,232 | 227 | 232 | 512 | 47 |

PDF465/227 contain scanned publisher conclusion, appreciation and signature
pages. They require OCR and remain rejected when OCR fails or is disabled.
PDF469/232 contain a uniform green back cover: no characters, images, lines,
curves or annotations; their only object is one unstroked filled rectangle.
The baseline reader always treats empty OCR text as unreadable, so these covers
make otherwise complete extractions fail the strict guard.

The fix recognizes a plain background only after checking the original page's
objects **and** raw PDF operators/graphics state. Unsupported painting,
shadings, patterns, soft masks, transfer functions, hidden characters,
annotations, images, CID text, complex drawings and partial rectangles cannot
use this classification. It consumes no OCR budget. The strict rejected-page
and rejected-finding guards remain in `extract_blue_book`.

The shared reader serves the Blue Book parser and newer county-volume parser.
The single-entity county reader and county-volume `read_head` use separate
readers. Blank pages contribute no lines or findings. No walk-version bump is
needed: finding output is unchanged and the partial attempts never earned a
current version stamp.

## Executed verification

`python -m pytest backend/tests/test_oag_decorative_pages.py -q` with the baseline
`read_pages` loaded from main `b19a69a5082a6f931dabb4b642903ff373260581` returned
**2 failed,16 passed**. The failure is forbidden OCR of the empty/vector cover.
The final reader returns **21 passed**. An intermediate objects-only prototype
incorrectly accepted five unknown-paint/malformed cases; those failed controls
were retained, and raw-operator checks fixed them before the final proof.
Root independently reproduced an unterminated inline-image false blank.
The same fixture and an unterminated string failed before the complete raw-byte
lexical check (**2 failed,19 passed**) and pass afterward. The parser's EOF can
silently swallow those forms; EOF alone is not a completeness proof.

The focused Blue Book, county-volume, county-audit and prior-year suites return
**160 passed,0 skipped**. Final full PDF reads used real Tesseract5.5.0 with eng
data, pdfplumber0.11.10, pdf2image and poppler at the existing 200dpi/default OCR
configuration. The owned Docker image installed the same system packages as
the seed workflow from standard Debian package sources; runtime networking was
disabled and the workspace mount was read-only. Shared installations were
untouched. The final reads took65.648s/49.952s locally; these are not production
duration estimates.

Direct real `_ocr_page` calls for PDF469/232 both return the empty string;
the baseline's rejected-page outcome is therefore reproduced with its actual
OCR dependency as well as the source-shaped regression fixture.

Both full final reads have zero rejected pages/findings, zero skipped chapters,
47 TOC entries and 47 positive finding cohorts. Real candidate payloads match
every one of the fresh986/512 extraction payloads, pages and confidence values.
All finding keys are unique; there are **zero insertions, revisions or
retirements**. All1,498 audit IDs, extraction IDs and audit→extraction links
remain accounted for. No new entity, attribution, amount or historical-table
rewrite is proposed.

The fresh parent-owned read-only capture at14:47:50UTC is bound by SHA256
`a985d2934f3882b447cf45d2e2463e66c9a0233ea3e99352ee0195066806e292`.
The [exact completion plan](completion-plan.json) retains both full source
before-images, historical partial attempts, after-images, all row IDs and
cohort hashes, plus protected table digests and sequences.

Root's independent actual-PDF reader probe executed19 passing controls at
reader SHA256`61f17532e8ad92e40fb265f542fa719f6aa387a720bef4e47df2dc1612cfda1a`,
including the real covers/conclusions and hostile graphics states. Its raw
receipts are `ROUND21_OAG_READER_INDEPENDENT.py/.json` in the coordinator's
retained evidence directory; the historical failed probe is retained there too.

## Exact forward and inverse contract

The proposed existing-writer transition changes only `source_documents.metadata`
for2395/2396. For each source it adds `extractor_version=3` and replaces the old
`last_extraction_attempt` with `{"status":"complete"}`. This is the normal
success shape produced by `extract_and_load` after parser and loader success.
The existing `extracted_md5` and `extraction_stats` already equal the actual
completed replay and therefore need no change. Every other source column and
metadata key, including prior fetch evidence, must stay exactly equal.

This plan is **not an instruction to set status manually**. The dedicated
`tools/oag_older_completion.py` performs the real final-reader parse over pinned source bytes
and compare every candidate payload/page/confidence/key with the locked current
cohort before deriving the success transition. It reuses typed JSON comparison,
exclusive durable receipts and the existing explicit TCP/TLS database URL
validator. It defaults to ROLLBACK; final
execution remains the coordinator's separate reviewed action. If its source
proof adds fields to the completed attempt, its exact after-image and inverse
must be reviewed and rehashed before execution.

The executor pins the exact manifest SHA256, reader bytes and actual source
hashes. It locks all15 protected tables and the scoped source/Audit/Extraction
rows, checks full current images, and computes a predicted source-table digest
by substituting only the two approved metadata objects. It executes only two
metadata updates, compares the actual full after-images and all protected
digests/sequences, then rolls back by default. It performs two full protected
digest passes; source prediction scans only the source table. Forward commit
requires `--expected-manifest-sha256` and an exclusive fsynced intent receipt.
Inverse requires that exact recovery receipt/hash, canonical before/after
images and unchanged unrelated protection; it also defaults to ROLLBACK.

The actual `source_proof()` producer ran in the isolated real OCR runtime and
returned both complete cohorts with proof SHA256
`b8921947d14d5ee35b4b22636a4239add16d8a46819512ee67178f3f30d6e5a7`.
This proof's payloads remain local, separate from the synthetic operator tests.
Owned PostgreSQL17 controls return **21 passed,0 skipped**. They explicitly stub
the source proof and manifest authority for synthetic fixtures and exercise
default rollback, legitimate forward/inverse, new/missing/changed source or
cohort rows, unrelated drift, malformed proof, receipt collision and an inverse
with a maliciously recomputed receipt digest. Sequence advancement refuses
before metadata writes; a real update-trigger side effect refuses the full
post-image and rolls back all changes. Direct producer calls also refuse a
recomputed manifest authority. The combined selection before the final operator
controls returned **178 passed,0 skipped**.

The coordinator's independent final operator review passed **79 cases: six
healthy cases and 73 refusals**, at operator SHA256
`e6c1cac0c416ae64a3388ae165113d9bbd6fe4c01330d61045a76e80e63a02e1`.
It executed the real 701-page OCR/parser proof and confirmed all 1,498 exact
payloads at the same proof hash above. Default rollback, forward commit and
guarded inverse preserved all 15 protected tables and sequences; concurrent
writers were blocked and a trigger side effect rolled back. This gate permits
the scoped local commit; actual production adoption remains separate.
The retained independent receipt is
`A/latest/ROUND21_OLDER_COMPLETION_ADVERSARIAL.json`, SHA256
`1d1bc067ef177a1ead7ea1c38829f850fcb1c8cab24e8a81e0677881fa6b98ab`.

Allocate at least **6 GiB** to the isolated OCR runtime for this replay. The
coordinator's initial 2 GiB capped run exited137 during setup, consistent with
a memory kill; its removed container did not retain an OOMKilled flag. The
reviewer observed 3.74 GiB RSS during real OCR. The initial failure receipt is
retained; that proof-only attempt opened no database connection and made no
production writes. A runtime setup failure is not a completed source proof.

Forward prerequisites:

1. Acquire the approved backup and compatible isolated restore/recovery proof;
   coordinate all writers. Fix/release version and reader bytes must be pinned.
2. In a transaction, lock both source rows and compare their **entire** source
   before-images and the complete scoped Audit/Extraction cohorts with this
   packet. Recompute hashes canonically; missing/extra/duplicate rows, changed
   IDs, content, source identity, metadata or bytes must refuse before writes.
3. Parse each actual PDF with real OCR; require the exact source hashes,
   page counts, 47 confirmed chapters, all47 positive cohorts, zero rejected
   pages/findings, zero skipped chapters and unchanged1498 candidates.
4. Write only the two reviewed metadata images. Require two matched rows and
   exact whole-source after-images; preserve all Audit/Extraction fields/IDs,
   all other source rows, entities, financial tables, jobs and sequences.
5. Independently execute no-write default, source/metadata/row/hash drift,
   incomplete OCR, unknown-paint and unauthorized-scope refusal controls on an
   owned database. Test a legitimate forward transition and guarded inverse.

Inverse prerequisites:

1. Default to ROLLBACK. Lock both sources and require the exact adopted
   **whole-source** after-images plus all scoped and unrelated protected-state
   digests/sequences. A later writer change refuses the inverse.
2. Restore only the two exact prior metadata objects retained in this plan,
   including the real historical partial attempts. Require exact full source
   before-images and unchanged Audit/Extraction rows/IDs afterward. Do not
   delete/reinsert findings or reset any sequence.

The existing eight-edition observation authority and five-source CLI manifest
intentionally cover FY2021/22 onward. The older sources must not be relabelled
as `oag_county_volume` or added to that authority to make its checks pass.
Generic `county_audit_coverage` already evaluates the old rows' actual latest
attempt, stats and MD5; its production receipt must be recaptured after the
separately approved adoption. Preserve the existing qualified listing/newer
edition observations and operational job history.

## Remaining closure requirements

Local parser/source completion and a no-finding-change plan are now established.
Issue #234 remains open until the guarded actual metadata adoption is accepted,
protected production cohorts are proven unchanged, strict coverage/FULL
validation succeeds and any required actual cache/API/rendered acceptance is
recorded. A local complete replay cannot clear production partial flags.

The defect belongs to the existing #234 requirement; no new duplicate issue is
requested. Closed #468/#469 and completed newer-volume adoption are outside
this change. #347/#137 retain their separately unresolved history/programme
requirements. Actions, production writes, provider operations, pushes, PRs,
issue edits and external messages were not performed in this lane.
