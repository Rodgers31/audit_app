# Round15 local OAG artifact and historical project evidence verification

Executed 2 October 2026 in the assigned `codex/round15-oag-project-evidence`
worktree, starting at `829268cafb45f68b807d67e54de3b065eb87681e`.
This verifies the bounded local continuation of #230. It does not certify
production ingestion, PostgreSQL concurrency, public Projects exposure or issue
closure. No provider call, production write, push or workflow run occurred.

## Behavior and supported caller

The existing PDF fetcher now records separately versioned actual-byte SHA256,
MD5, byte size and source association after its existing PDF validation. A real
matching downloader sidecar may supply download time; otherwise the new identity
explicitly records unknown time. Existing verification timing remains intact.
The county-volume extractor snapshots and checks that identity against the file
before and after visible-text extraction. Reconciliation validates each binding;
the loader preserves it in Audit provenance. The canonical extraction-JSON hash
remains distinct from the PDF digest. Same-byte replay and hash-only binding
additions retain extraction IDs and Audit references. Partial reissues and loader
failure cannot relabel older findings.

The real comprehensive route supplies its already batched source/extraction rows
and canonical county to both stalled-project projections, retaining publication
gates. Exact artifact, source, institution, period, locator, text and provenance
checks accept only the approved Nyamira FY2023/24 Assembly residence passage.
The older observation remains separately sourced; candidate-only identity cannot
combine money/counts, resolve the current paid conflict or establish current
verification or loss. Optional payable requires its own valid same-edition
passage. Missing or malformed historical evidence preserves valid current data.
Truthy non-string finding headings are now refused before regex evaluation.

Supported extraction binding is the existing `oag_county_volume` path, including
its actual reconciliation/loader caller. Blue Book and other single-entity paths
remain compatible but do not gain supported artifact binding from this change.
Legacy records need a legitimate future normal complete extraction to establish
binding; loader replay cannot invent it from today's document metadata.
The [narrative contract](../contracts/round13-project-narratives.md) defines storage
keys and API fields. Comparative examples remain documentary.

## Executed evidence

External immutable logs, launcher, source receipts and independent review are
banked under:
`/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170/`,
with owned prefix `ROUND15_SESSION_1_`. The external handoff records exact commands,
commit/tree, hashes, cleanup and earlier failed harness runs.

- Final regression selection, `FINAL_VERIFIED.log`: **384 passed, no skips,
  3 warnings, 11.62s, exit0**, application-engine connection attempts0. Seventeen
  files cover artifact/projection controls, fetch/cache, county volume and Blue
  Book extraction/loading, hostile/preservation/recovery behavior, project
  narratives/stalled blocks and county identity API contracts.
- Actual retained-byte producer/read, `RETAINED_PIPELINE_GREEN.log`: **1 passed,
  exit0**, real217-page PDF,541 findings/47 complete county chapters. Existing
  downloader with one local MockTransport response; no network request.
  Same-byte replay retained IDs/bindings and created/updated0 audits. The API
  returned candidate-only historical paid24,158,208 and payable2,457,540;
  current annual paid scalar stayed null. PDF and extraction hashes differed.
- True starting-code baseline, `RED_BASELINE_GUARDS.log`: **5 failed,
  44 deselected, exit1**, original tracked modules rebound from starting HEAD in
  the isolated launcher. Failures cover absent fetch identity, unchecked sidecar
  context, changed bytes during read, old-extraction relabeling after reissue,
  and absent actual-record historical projection. Final selection passes these
  controls. `RED_ARTIFACT.log` and `RED_PROJECTION.log` bank initial incremental
  feature reds; they are not additional unique coverage.
- New hostile read controls found a list paragraph number causing500 and repaired
  it through strict locator types. A later `RED_HEADING_SHAPE.log` reproduced
  boolean/integer headings causing500 (**2 failed/2 passed**); final heading
  selection passes all6 malformed-type controls. Current data stays available.
- Independent GPT-6.1 Sol/high behavioral review: corrected full retained-source
  run **43 passed, exit0**; final fast controls **43 passed/1 deselected, exit0**;
  final heading addendum **4 passed/43 deselected, exit0**. All engine attempts0.
  Coherent positive and hostile API controls, actual downloader replay/reissue,
  stable references, partial refusal, exact dates, private-path exclusion and
  unsupported Siaya are covered. No further confirmed production-code finding.
  Counts overlap and must not be added.
- Final critical flake8 selection `E9,F63,F7,F82` and `git diff --check`: exit0.
  No dependency install or shared-cache mutation.

The17-file command uses the read-only interpreter and owned launcher:

```sh
/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python /Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170/ROUND15_SESSION_1_RUN.py FINAL_VERIFIED backend/tests/test_oag_project_evidence.py backend/tests/test_fetch_documents.py backend/tests/test_pdf_download.py backend/tests/test_oag_county_volume.py backend/tests/test_county_volume_adversarial.py backend/tests/test_county_volume_loading.py backend/tests/test_blue_book_extractor.py backend/tests/test_blue_book_loader.py backend/tests/test_audits_loader_roundtrips.py backend/tests/test_extraction_preservation.py backend/tests/test_extraction_hostile_inputs.py backend/tests/test_extraction_recovery.py backend/tests/test_project_narratives.py backend/tests/test_stalled_projects_pipeline.py backend/tests/test_stalled_projects_not_invented.py backend/tests/test_county_identity_http.py backend/tests/test_county_identity_contract.py -q
```

The launcher disables dotenv and Pydantic env-files before app imports, uses an
allowlisted synthetic test environment, empty Redis, inert lifecycle and disabled
seeder/warmup. Resolved psycopg2 destination is loopback55531; every application
engine connection is refused. Only SQLite fixtures, TestClient and synchronous
MockTransport are permitted; real and async HTTP are blocked. No PostgreSQL
resource was created. Test files/cache copies use exact owned external directories.

## Sources, compatibility and limits

Actual retained source hashes recomputed locally:

| Source | SHA256 |
| --- | --- |
| CoB FY2025/26 annual PDF | `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3` |
| OAG FY2023/24 Assembly PDF | `683fa522bf11eaa2b0bc2a9eef51eadc3d664d9a512d3af63cb6e9479820f8a2` |
| OAG bounded PDF205–209 text | `15890d0fdb5991bfb3f5c7bf174cb9185e94c867c6062e0738c51ffeabb7ccc1` |
| Retained source receipt | `cfa04435f416e45209369f8b14739ecf77199f6ec0fd89d7096384e9e4a0258d` |

A small faithful fixture contains actual normalized page/finding text and source
locators, never a production row. Current annual source-backed168 detail rows/47
county records,188 numeric summary counts and189 stated counts are protected by
the selected existing tests. Zero, unknown, withheld and conflicting remain
separate. Table/no-table paths, old schema2/narrative schema1, publisher/county
guards, later metadata and legacy county routes remain covered. Siaya's unknown
institution and investigation stay unchanged; no extra project rows are fabricated.

Earlier failures attributable to harness wiring are disclosed in the external
handoff: disallowed local MockTransport, foreign-key-invalid fixture, missing
external conftest plugin, malformed annual fixture envelope, fixture-session
lifetime, and the review fixture's temporary PDF-reader stub. These are not
production red-before/green-after claims. Final warnings are AnyIO assertion
rewriting, deprecated Starlette/httpx pairing and existing test transaction
cleanup. No implementation acceptance rests on the warnings or on source strings.

Authoritative payment/project identity resolution, competent language review,
legacy cleanup, actual stored/deployed publication acceptance and separately
approved exposure remain open under #230. General pipeline/coverage and broader
production corrections remain separate (#137/#234/#322 and their existing lanes).
