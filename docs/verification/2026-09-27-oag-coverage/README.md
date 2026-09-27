# Current county audit coverage — Session 4

Prepared from main `dc58685bb72007a5654863bfbeee912cfd6b89e3` in isolated branch `codex/current-oag-coverage`. This is local source/rehearsal evidence and a release plan. **No production ingestion or cleanup was performed.** Issues #234, #230 and #322 remain open pending release acceptance.

## Reproduced behavior and changes

- Eleven initial coverage regressions failed on main: unchecked scalar/nested ingestion JSON, malformed fiscal years, Executive-only coverage reported healthy, and a partial extraction ignored by the gate. Coverage now produces a county × fiscal year × institution receipt, using accepted findings with matching source/extraction/year/page and attributable county identities. It explicitly measures finding presence, not an assurance that every possible finding was extracted.
- Six full-validation regressions reproduced crashes before the county gate, in generic ingestion metadata consumers. Narrow shape validation now preserves unknown/partial/refused distinctions. In particular a refused run remains a failure even if its explanation is malformed. Session 5 agreed to this narrow ownership; cadence, source API freshness and cache behavior remain there.
- Both current volumes initially reported partial forever because image covers and blank front matter were unreadable locally. Verified chapter/contents boundaries now delimit the finding pages. All omitted page numbers remain recorded. Missing counties, unreadable chapter pages, conflicting/repeated contents or chapter headings, and chapters yielding no findings remain partial; existing richer evidence survives refused retries.
- Adversarial probes reproduced Appendix citations truncating the final chapter, duplicate chapter headings filing text against the preceding county, null page references comparing equal, duplicate outcomes concealing a missing volume, and empty parser results being reported as processed. Retained executable tests exercise the corrections and valid positive controls.
- Eight actual current-volume institution spellings differ from canonical names: Taita/Taveta, Elgeyo/Marakwet, Tharaka-Nithi and Nairobi City, across both institutions. Five representative alias tests failed before the correction. Printed auditee labels are retained only when both names resolve to the supplied county and the same institution. Genuine county/role conflicts remain withheld.

## Primary sources and limits

Discovery on 27 September 2026 read [OAG's county listing](https://www.oagkenya.go.ke/county-executives-assemblies-reports/), year pages and sitemap: 103 documents, eight combined volumes spanning FY2021/22–FY2024/25, zero discovery errors. FY2024/25 is the newest county year listed. The complete inventory is [discovery.json](discovery.json). Each accepted volume receipt records its URL, SHA256, MD5, fiscal year, institution, extraction/loading counts, omissions, runtime and peak sampled RSS.

The standalone [rehearsal script](../../../scripts/verification/oag_county_rehearsal.py) calls the existing `fetch_document` → `extract_and_load` → county loader path on an existing **loopback `codex_oag_*` PostgreSQL clone only**. It refuses remote hosts, non-PostgreSQL drivers and URL query overrides before creating an engine. Each worker is limited to 900 seconds and 6 GiB sampled RSS, downloads to 120 seconds/40 MiB, and preserves the downloader's resumable cache. Workers run serially, newest first. OCR is disabled; unreadable chapter pages cannot silently become complete.

The source replay excludes national books, FY2020/21 books and individual county reports. The normal domain's duplicate-control tests verify that individually registered county reports covered by combined volumes are not fetched. The pre-existing FY2021/22 Homa Bay row (901) is withheld: no extraction or page. It does not duplicate published combined-volume findings.

## Baseline and failed receipts

Production read-only SQL at **20:05:45 UTC** found 1,499 stored county rows: 1,498 FY2020/21 and one FY2021/22. Paginated public GETs at **20:15:45 UTC** returned 2,311 published findings total, with **1,498 county findings, all FY2020/21**. The extra stored row is not public. [Production API receipt](api-before.json).

The disposable clone originates in the preserved 26 September production dump, not a fresh full production backup. First-run exact-row comparison failed because the already-merged publication backfill changed only `quarantine_reason` on 25 retired fixture audits from `source_document_has_no_url` to `retired_legacy_fixture`. No finding, amount, source, extraction ID or page changed. The failed receipt and exact field diff are retained; that run is not labelled successful.

The final fresh clone applies that existing deployed gate before taking the ingestion baseline; [baseline-normalization.json](baseline-normalization.json) records exactly those 25 label changes. This is local preparation, not #319 cleanup or authorization to delete anything. The final source replay checks every field of every prior audit row against its baseline hash.

The first full replay also honestly returned partial for FY2021/22: its printed end-matter heading is “Appendix A: List of County Executives and Audit Opinions given on their Financial Statements” (the Assembly volume starts directly with “A: List of County Assemblies…” without “Appendix”), followed by blank back matter. The exact heading is now recognized, while a sentence citing “Appendix VI to the financial statements…” cannot truncate a chapter. Failed and partial receipts remain distinct from the final run.

## Accepted local replay

All **eight volumes completed**, with no failed, partial or deferred sources. They added **6,607 findings**, taking stored audits from **2,338 to 8,945**. Every field of all **2,338 prior audit rows remained unchanged**. The gate returned `OK` for all **376 county × fiscal year × institution cells**. This means attributable finding presence in each cell; it does not certify exhaustive extraction. [Final run receipt](final-replay/run-receipt.json) · [Full coverage receipt](final-replay/coverage-after.json).

The [before/after matrix](coverage-matrix.csv) has 376 rows and exact finding counts/source IDs. Its zero baseline for FY2021/22–FY2024/25 is verified by the [read-only snapshot query receipt](matrix-baseline.json); the snapshot had no stored listing, so required years are supplied explicitly by current discovery. This is a local comparison, not a post-ingestion production measurement.

| Fiscal year | Institution | Added findings | Seconds | Peak sampled RSS (GiB) |
|---|---|---:|---:|---:|
| 2024/2025 | executives | 1,269 | 34.6 | 3.52 |
| 2024/2025 | assemblies | 582 | 12.2 | 1.20 |
| 2023/2024 | executives | 1,047 | 56.6 | 4.81 |
| 2023/2024 | assemblies | 541 | 36.5 | 2.88 |
| 2022/2023 | executives | 1,041 | 40.4 | 3.49 |
| 2022/2023 | assemblies | 513 | 23.1 | 1.93 |
| 2021/2022 | executives | 1,082 | 50.2 | 5.04 |
| 2021/2022 | assemblies | 532 | 26.6 | 2.38 |

A second complete replay returned all eight sources as already current, added no rows and preserved every field of all 8,945 stored audits. [Idempotence receipt](repeat-replay/run-receipt.json).

The [accepted source manifest](accepted-source-manifest.json) binds these counts to the exact URLs and SHA256/MD5 hashes. Individual receipts under [final-replay](final-replay/) preserve page counts, unreadable-page lists, loading outcomes and timings.

## Representative page checks

The original PDF pages were rendered and visually inspected, not inferred from printed-page offsets.

| Report / auditee | PDF page / printed page / paragraph | What the source supports |
|---|---|---|
| FY2024/25 County Executives, County Executive of Taita/Taveta | [71](https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-EXECUTIVES-2024-2025-1.pdf#page=71) / 58 / 134 | Twelve sampled projects amounting to KES219,207,350; nine incomplete and three stalled, inspected July 2025. This is the combined sampled-project amount, **not** the amount for the three stalled projects alone. |
| Same Executive volume, County Executive of Garissa | [80](https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-EXECUTIVES-2024-2025-1.pdf#page=80) / 67 / 155 | Seventeen stalled projects, KES509,485,588 contract sum (October 2025 inspection), plus five completed but unused projects valued at KES186,327,912 (May 2025 inspection). Distinct populations/measures; loaded scalar amount remains null. |
| FY2024/25 County Assemblies, County Assembly of Mombasa | [14](https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-ASSEMBLIES-2024-2025-1.pdf#page=14) / 1 / 2 | Six unresolved FY2023/24 matters remained as of 30 June 2025. They remain genuine unresolved findings within this FY2024/25 report, separate from the Executive's findings. No amount is inferred. |

These are audit observations, not county budget/revenue totals. The project amounts retain their stated roles (sampled-project amount, contract sum, project value); no cash/accrual aggregation is claimed. The report year and a later physical-inspection date are retained separately. See [project-candidates.jsonl](project-candidates.jsonl) for extracted evidence, including the Tana River mixed-status observation with no guessed scalar amount.

Session 3's CoB artifact is FY2025/26 annual, SHA256 `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`, snapshot 30 June 2026. Its checked Baringo Sugut/Marigut rows do not establish identity with these aggregate OAG samples. No automatic cross-year corroboration or project-tab re-enablement is justified.

## Verification

The final backend suite passed **5,446 tests, with 24 skipped** (33 warnings), running from `backend` with `python -m pytest tests --ignore=tests/integration -m 'not slow' --maxfail=5 -q`. [Complete test output](backend-tests.txt). Independent adversarial checks covered malformed metadata through the full validator, incomplete/duplicate outcomes, citation conflicts, extraction preservation and unsafe rehearsal connection overrides; the [coverage check output](adversarial-coverage.txt) records 102 passing checks. The full suite includes all retained regressions. Critical Python lint and `git diff --check` also passed.

The actual audit dashboard handler was exercised against the local PostgreSQL replay: **1,851 FY2024/25 county findings, 94 distinct audited institutions**, every finding with an auditee, source URL and page. [Handler receipt](handler-receipt.json). This is an API-handler check, not a live production HTTP/browser check; live release verification remains pending.

## Reproduction and release prerequisites

Use the backend runtime and a separately restored disposable clone. Initialize its publication labels with current main if the snapshot predates the release, preserving a receipt. Then:

```sh
export OAG_REHEARSAL_DATABASE_URL='<loopback PostgreSQL URL; database codex_oag_*; no query parameters>'
python scripts/verification/oag_county_rehearsal.py \
  --manifest docs/verification/2026-09-27-oag-coverage/discovery.json \
  --artifacts /tmp/oag-rehearsal --all-listed
```

Without `--all-listed`, only the newest pair runs and older volumes are explicitly deferred; incomplete overall coverage exits with status 2. Run the same command against the same clone/cache to verify no duplicate rows and unchanged prior evidence. This utility cannot run against production.

Release acceptance still requires review/merge, verified deployment, a fresh bounded production plan and backup/rollback evidence, Session 5's serialized ingestion slot and agreed refresh mechanism, then before/after production county × period × institution receipts and public API/browser checks. Proposed source scope is the eight exact combined-volume URLs/hashes in these receipts, newest pair first; no reviewed reconciliation override, retirement or unrelated seed is included. If the general `audits` domain is used, separately account for its national/legacy candidates and discovery registrations; this county-only rehearsal does not authorize or verify those changes. Missing/refused sources must remain explicitly incomplete. Do not close #234 based on local results.
