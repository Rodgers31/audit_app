# Review 495: executed receipt boundary evidence

Reviewed base: `2376b07b8f4f570dc0dc90352defdfcf03f43e64`.
Both comments are false positives at this base. No production patch is needed.

## Comment 4175752289: alleged GDP lexical scope error

`backend/seeding/domains/debt_timeline/writer.py:101` initializes `gdp_doc`
inside `write_debt_timeline_records`. The nested `_doc_for` ends at line 110.
The assignment at line 123 is in the outer writer's observation loop; it does
not assign a closure variable. Adding `nonlocal` there would be incorrect.

New executed control uses the actual World Bank fetcher, parser, writer and
qualification reader with an isolated SQLite DB fixture. One retained response
contains two years. First call creates two rows; second call updates the same
IDs after changing one source GDP by exactly one KES. Both calls commit, expire
and reload the stored rows. GDP precision survives, each GDP independently
verifies, two observations reuse one GDP document/receipt per acquisition, and
each GDP document differs from its row's debt document. Both old and new
immutable Extraction digests survive. Debt totals and derived ratios remain
qualified because the synthetic debt input has no independent receipt.

## Comment 4175752304: alleged premature full-response metadata

`backend/seeding/http_client.py:314-315` removes the previous URL receipt and
initializes `full_response=None` on every call. Lines 505-506 assign successful
200 metadata only after `iter_bytes()` and file writing finish. An iterator
exception enters the handler at line 511 before that assignment. Receipt
creation at lines 555-580 requires this completed response metadata.

Six new stream controls use real httpx Request/Response/headers and
MockTransport/SyncByteStream, with actual CAS readback and fresh source parsing
through persisted Extraction qualification:

| Acquisition | Executed outcome |
|---|---|
| Uninterrupted complete 200 | Exact bytes retained; `verified` |
| Interrupted 200 followed by matching 206 in the same call | Exact assembled bytes; no download receipt; `qualified/unsuccessful_response` |
| Initial full receipt, later interrupted call stalls, following call completes with 206 | Old receipt removed even on error; durable partial retained; no download receipt; qualified |
| 200 yields all PDF-shaped bytes then iterator raises at EOF | Local completion accepted; no successful response receipt; qualified |
| Interrupted 200 followed by server ignoring Range and delivering a complete 200 | Replacement whole body, not spliced; exact digest; verified |
| Existing complete partial on a later call | No new request; old acquisition removed; qualified |

For local-only completions, the helper retains local bytes and may persist
metadata with an Extraction ID. Its receipt has `status=None`; the qualification
does not claim transport, document-byte verification or value verification.
That local record is not a successful HTTP acquisition. Full 200 positive
controls assert actual CAS digest/readback plus verified byte and value checks.

These are synthetic ingestion capability controls, not a claim that the tiny
PDF-shaped test source is a rendered publisher PDF. Existing PDF parser and
receipt ingress tests were also executed. The production callers are the debt
domain runner (`debt_timeline/__init__.py:60`) and shared PDF downloader
(`seeding/pdf_download.py:370`); their shared writer/download boundaries are
the tested functions.

## Executed validation

Python: existing read-only `.venv313`. Database: isolated SQLite fixtures; no
PostgreSQL/provider/network call and no optional skip was counted as executed.
Acquisition: mocked HTTP, actual source bytes and local CAS.

Environment explicitly sets `DATABASE_URL=sqlite:////tmp/review495-inert.sqlite`,
`AUTO_SEEDER_ENABLED=false`, `AUTO_WARMUP_ENABLED=false`,
`PARLIAMENT_PIPELINE_ENABLED=0`, `PARLIAMENT_RECONCILE_ENABLED=0`.
Seeding settings use `_env_file=None`. No application lifespan is started.

Commands in `backend/` (absolute interpreter above):

```text
python -m pytest tests/test_review_495_receipt_boundaries.py -q --tb=short
7 passed, 3 warnings in 0.25s

python -m pytest tests/test_review_495_receipt_boundaries.py tests/test_pdf_resume.py tests/test_debt_timeline_row_provenance.py tests/test_receipt_ingress_trust.py -q --tb=short
50 passed, 6 warnings in 1.57s
```

Finite hostile experiment modifies functions only in a separate Python process:
move 200 metadata capture before stream iteration and deliberately associate
the GDP operand with the debt document. The two interrupted-stream controls and
the GDP association control each fail: **3 failed in 0.17s**, expected. Production
source on disk is unchanged; rerunning the normal full files gives 50 passed.
This proves the added controls reject the failure shapes, rather than merely
asserting source text. Initial test drafting exposed incorrect expectations
that local receipts have no Extraction ID and derived ratios have no
qualification entry; these fixture assumptions were corrected to the actual
honest qualification contract. No production defect was reproduced.

Evidence under the approved artifact directory:

- `REMAINING_REVIEW495_NEW_CONTROLS.log`
- `REMAINING_REVIEW495_BOUNDARY_TESTS.log`
- `REMAINING_REVIEW495_HOSTILE_MUTATIONS.py` and `.log`
- `REMAINING_495_COPILOT_COMMENTS.json` (pinned review text)

Scope is these two review mechanisms and their receipt qualification boundary.
This does not establish hosted CI, production durable storage acceptance, or
qualification for unrelated historical observations.
