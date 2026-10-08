# Fresh CoB PDF page lifecycle — #504 / #137

## Change and boundary

`extract_all_tables` now closes each selected pdfplumber page in `finally`,
after copying every table's strings and coordinates. The CoB revenue-caption
scan also closes each page after extracting its caption, including failures.
All pages, tables, table index gaps, county ownership, period detection,
financial values and refusal rules are retained. This bounds retained page
layouts to the page being processed; it does not impose a hard process memory
limit or eliminate document resources, output tables or source-byte buffers.

The backend minimum pdfplumber version is now 0.10.4, which provides `Page.close()`.
The installed replay version was 0.11.10. Its `close()` flushes the layout and
object caches and clears the text-map cache. See the
[official page lifecycle documentation](https://github.com/jsvine/pdfplumber/blob/stable/README.md)
and [0.10.4 changelog](https://github.com/jsvine/pdfplumber/blob/stable/CHANGELOG.md).
No dependency was installed during verification.
The seed workflow and backend Docker builds install `backend/requirements.txt`.
The separate legacy ETL pin remains unchanged; this receipt does not validate
its independent execution path.

The shared table helper covers direct extraction, fresh county-fetcher parses
(cache disabled or cache miss), and Treasury debt parsing. Their regression
suites passed. The CoB cover scan reads at most three pages; it is unchanged.
OAG's separate text helper, stalled-project parsing and pending-bill extraction
are unchanged. Parse-cache hits retain their existing trust limitations. The
source-file cache fingerprint changes naturally; no cache entries, historical
evidence or database rows were rewritten.

## Local execution receipts

All replays used the retained official PDF, **53,561,211 bytes**, SHA-256
`5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`.
Download was mocked to that file; outbound HTTP was blocked. These were local
macOS process RSS measurements, not hosted memory or provider storage tests.

| Execution | Peak RSS, bytes | Scope |
| --- | ---: | --- |
| Prior independent unchanged parser | 10,028,826,624 | Cache-disabled fetcher plus file-backed mocked R2 adapter; existing receipt |
| Table cleanup only | 1,804,812,288 | New all-page replay, unchanged caption scan, LocalReceiptStore |
| Both cleanup paths, through parsing | 351,322,112 | Same final replay before source-byte receipt capture |
| Both cleanup paths, through converted return | 566,640,640 | Same final replay including actual LocalReceiptStore put/read |
| Independent fresh full producer | 541,835,264 | Separate actual cache-enabled fresh producer with LocalReceiptStore; still above 512 MiB |

The final table-phase checkpoint peak was 299,008,000 bytes. Full producer
elapsed time was 101.86 seconds. The old independent R2 harness and new local
store harness differ: the table-only/final pair is the comparable controlled
measurement. None is a production memory guarantee. RSS above excludes the
subsequent serialization of complete comparison artifacts.

No complete output had been retained with the original 10 GB measurement.
The semantic oracle therefore executed the **exact original table function**
from `77a6892` on consecutive groups of eight pages, reopening the PDF between
groups. Its memory lifecycle differs from the original all-page parse. Its
original global page indices and all table extraction/normalization logic are
preserved. The candidate extracted all **935 pages** in one pass.

Complete tables (1,129), parser records, revenue coverage and all converted
records (468), including 378 cell observations and their sealed local receipt
manifests, compared byte-for-byte equal after lossless Decimal tagging. The
comparison fixes only receipt check time through a test clock. Both output
files have SHA-256
`cbaa3d98e2aaa96071d90260aff69cd619cf7ffe6794a89f27556cd7b08c33e4`.
Local cached bytes retain their actual matched-byte and non-HTTP qualification.

Seven deterministic lifecycle cases preserve full table output, selective and
empty page selection, caption ownership, and extraction/normalization/caption
failure cleanup. Against original function bodies in memory: **6 failed,
1 passed**, specifically on retained layouts. Final focused 15-file suite:
**432 passed, 4 skipped**, with three existing warnings. The skips require
retained-source opt-in environment variables; the full-source replay above
ran separately. Two existing test doubles gained the real page `close` API;
their original publication/refusal assertions remain unchanged.
Independent review also ran the complete retained source: all 935 pages,
1,129 tables, 468 records and 378 observations matched the same complete
semantic output. It observed 1,102 page release events. Its fresh producer
took 102.25 seconds with a 541,835,264-byte peak; that separate measurement
is approximately 516.73 MiB and also exceeds the 512 MiB host budget.
An actual subsequent parse-cache hit took 1.21 seconds with **zero new layout
reads**. All 378 cached observations preserved their explicit unsealed receipt
and cached-result origin qualification. Existing cache correctness and trust
regressions also ran in the author suite.
The independent local receipts are in `REMAINING_COB_MEMORY_INDEPENDENT`:
`full_cache_probe.py`, `full_cache_result.json` and `lifecycle_result.json`.

Exact commands, fresh allowlisted dummy environment, logs, source hashes,
full comparison outputs and RSS checkpoints are retained externally under
`REMAINING_COB_MEMORY_FIX` (`run_tests.py`, `replay.py`,
`original-test-command.json`, `candidate-test-command.json`,
`baseline-result.json`, `candidate-result.json`). No production SQL, ingestion,
Actions or provider operation ran.

## Remaining host acceptance

The verified Render Starter API instance has 512 MB RAM; automatic seeding is
disabled and receipt storage remains local. **566,640,640 bytes exceeds even
512 MiB (536,870,912 bytes), before application/concurrent-request headroom.**
Fresh parsing on that API instance is not accepted by these results.

The separate public GitHub Ubuntu seed job has a documented 16 GB runner
budget, but no actual Linux runner RSS test or workflow execution was performed.
Before enabling fresh ingestion, measure the complete selected receipt adapter,
HTTP acquisition, parsing and persistence on its actual ingestion runtime,
reserve application/concurrency headroom, and refuse activation if that budget
is exceeded. Keep automatic seeding disabled meanwhile. This lifecycle change
does not itself authorize rollout, close #504/#137, establish R2 durability or
solve the separate Supabase Free-plan egress gate.
