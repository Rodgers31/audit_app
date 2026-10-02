# Round15 coordinator verification — 2 October 2026

## Accepted scope

Reviewed local author commit `4021e8d924040482bb4ba1007946dbbfd3341fea`,
tree `23a8eedce2a24a7525ffbff17af8968b409f7e6d`, against merged main
`829268cafb45f68b807d67e54de3b065eb87681e`. The consolidation checkout contains
that exact author tree before the coordinator's final query correction below.
Initial tested backend tree was `cc53b1dc7344aff97a2fc23185c11a2fee8506c9`;
the final393-test selection covers the subsequent query correction and nine tests.

Normal successful fetch retains validated PDF-byte identity. The county-volume
extractor binds each supported extraction to the actual artifact used, validates
bytes around reading, and preserves stable findings during legitimate replay.
For individually bound extractions the loader preserves their snapshot MD5 after
a document reissue. Missing legacy binding is not synthesized from current source
metadata. Historical observation acceptance requires actual ingested records,
matching artifact and canonical JSON hashes, exact retained edition/text/locators,
county, Assembly institution and period. Candidate-only identity stays qualified.

The supported producer is `oag_county_volume`; this is not a general provenance
rollout for Blue Book or single-entity paths. Historical PDF and extraction JSON
hashes have distinct fields and purposes. Existing current CoB observations,
conflicting paid scalar, table counts/money, unknown states, schema compatibility,
publisher guard, later metadata and legacy county routes are preserved. Frontend
and workflow subtrees are unchanged. Projects remains hidden.

## Coordinator execution

Commands ran in the clean consolidation checkout using a new allowlisted launcher
and synthetic loopback55533. Before application imports the launcher disabled
dotenv/Pydantic env files, removed inherited provider/database credentials, set
test/env secret settings, empty Redis and owned storage/cache namespaces, suppressed
startup/seeder/warmup, refused application-engine connections and unstubbed HTTP.
Only in-memory SQLite and in-process TestClient/MockTransport were used.

Retained external evidence directory:
`/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170`.

| Receipt | Executed outcome |
| --- | --- |
| `ROUND15_COORDINATOR_VERIFIED.log` | Initial17-file regression selection: exit0,384 passed,0 skips,3 existing warnings,11.37s; application-engine attempts0. |
| `ROUND15_COORDINATOR_FINAL_VERIFIED.log` | Final17-file selection after query correction: exit0,393 passed,0 skips,3 existing warnings,11.39s; application-engine attempts0. |
| `ROUND15_COORDINATOR_BASELINE_5.log` | Original tracked modules from starting main rebound in memory: exit1,5 failed,50 deselected,0 skips; engine attempts0. Missing candidate/binding, changed-byte refusal, unchecked sidecar and old-bound MD5 replay controls are genuinely sensitive to the original code. |
| `ROUND15_COORDINATOR_RETAINED_PIPELINE.log` | Actual retained217-page PDF through existing mock-network fetcher, visible reader, reconciliation, loader and comprehensive API: exit0,1 passed,34.20s,engine attempts0. |
| Critical flake8 and diff checks | `--select E9,F63,F7,F82` on changed Python modules/tests and `git diff --check` both exit0. |

The regression command uses `ROUND15_COORDINATOR_RUN.py VERIFIED` and these files:
`test_oag_project_evidence`, `test_fetch_documents`, `test_pdf_download`,
`test_oag_county_volume`, `test_county_volume_adversarial`,
`test_county_volume_loading`, `test_blue_book_extractor`, `test_blue_book_loader`,
`test_audits_loader_roundtrips`, `test_extraction_preservation`,
`test_extraction_hostile_inputs`, `test_extraction_recovery`,
`test_project_narratives`, `test_stalled_projects_pipeline`,
`test_stalled_projects_not_invented`, `test_county_identity_http` and
`test_county_identity_contract`, all under `backend/tests/`, with `-q`.
Baseline command adds `--baseline-oag` and selects the five controls recorded in
the baseline log. The retained producer command runs the new external
`ROUND15_COORDINATOR_RETAINED_PIPELINE.py -p conftest -q -s` through the launcher.

Actual retained producer result:541 findings across47 complete county chapters,
no refused chapter, stable IDs/bindings on same-byte cache replay, no new/updated
audits on replay and zero real HTTP requests. Historical paid24,158,208 and
payable2,457,540 stay separate; current annual paid scalar remains null/conflicting.
The API emits a qualified candidate, not current verification or combined totals.
These are local source/SQLite results, not a new production coverage census.

Source SHA256:
`683fa522bf11eaa2b0bc2a9eef51eadc3d664d9a512d3af63cb6e9479820f8a2`;
MD5 `15cd6108a0f08498a9e9f699430b365b`;32,379,711 bytes.
Coordinator recomputed every entry in the author's four-source and54-artifact
receipts:58 distinct files, zero mismatches. Final coordinator changes are
separately covered by final code/commit and independent query receipts.

## Independent review and findings

A fresh GPT-6.1 Sol/high reviewer executed49 independent actual loader/service/API
controls, exit0,0 skips,engine attempts0. It checked coherent wrong artifact/JSON
hashes, reissues, county/institution/period/text/locator/provenance mismatches,
malformed optional evidence, independently hashed retained bytes, optional payable
refusal, both table paths and legacy absence. No new confirmed defect remained.

Its first48-pass/1-fail result was an external harness expectation: the inherited
generic project-heading matcher does not list the pinned residence heading.
Only the ordinary legacy visibility fixture heading was corrected. The separate
actual historical API positive already passed. This is not a code regression or
a reason to broaden matching. Complete script, commands, hashes, limitations and
cleanup are in `ROUND15_COORDINATOR_REVIEW_RECEIPT.md` and `REVIEW_TEST.py`.
The reviewer did not repeat full PDF extraction or PostgreSQL concurrency.

Session discoveries are covered and fixed within existing #230: missing byte/
individual evidence binding, the bound-extraction replay attribution boundary,
malformed optional paragraph/title refusal and county API resilience. A subsequent
concrete query regression was reproduced, filed separately as #444 and fixed
before the final push. Source/payment/institution uncertainty and production
requirements remain tracked separately.

### Final cached-query correction — #444

The new `already_extracted` had replaced a legacy scalar count with full Extraction
ORM loading. Independent actual SQLite execution selected seven columns and
materialized both findings for legacy and bound inputs. In the two-row fixture,
full JSON serialization was3769 bytes for legacy/5145 for bound, including2373
finding-text bytes; a bound-only projection was1318 bytes and a legacy count is
scalar2. These are local serialization/query measurements, not wire bytes,
production prevalence or billing attribution.

The coordinator restored a scalar legacy count and selects only the versioned JSON
binding for bound rows. Existing valid/stale/missing/invalid/mismatched/empty
decisions remain unchanged. Two repository transfer controls were executed before
the fix: exit1,2 failed,62 deselected,engine attempts0 (`QUERY_RED.log`). The final
393 selection includes these passing plus seven decision controls. Independent
actual patched-module verification: exit0,9 passed,2 deselected,engine attempts0.
Final extractor SHA256:
`4395805ecc1de25fe31bf59f82349968018980878868e614b58d23e4d677d43b`.

Exact SQL, tested prototype, first code-sensitive reds, final actual-code command,
script/module hashes and cleanup are in
`ROUND15_COORDINATOR_QUERY_REVIEW_RECEIPT.md`. PostgreSQL projection compiled;
PostgreSQL runtime was not executed. Search for `already_extracted` found no issue;
the `extraction payload` match #379 is a distinct source text-boundary defect.
This new pre-release regression is addressed by this PR and #444 may close on merge.

## Closure and remaining acceptance

The local historical extension is complete. #230 remains open for authoritative
payment/identity/institution clarification where needed, legacy stored cleanup,
actual deployed provenance/API publication acceptance, competent language review
and separately approved Projects exposure. No production record was sampled or
certified clean here; no production fetch/seed/backfill/correction/configuration/
cache operation occurred. SQLite is not PostgreSQL concurrency or publication
acceptance. Original linked #137/#234/#322 requirements remain incomplete.

Actions is confirmed disabled; no workflow dispatch or billable review was
requested. Owner approval permits the verified local PR merge/admin override.
Production execution retains fresh exact plan, writer coordination/freeze, full
consistent backup, successful isolated restore, recovery review and separate final
action approval. The dirty primary checkout is preserved. Root and reviewer
remove only their newly owned temporary test storage; retained evidence survives.
