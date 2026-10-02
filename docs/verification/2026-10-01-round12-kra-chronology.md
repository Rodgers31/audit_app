# KRA edition chronology: new evidence delta, 1 October 2026

#298 remains unresolved. The fresh investigation adds article-index and file-processing dates, a non-oil Customs discrepancy, and differing domestic rates. None establishes a replacement edition or the Customs-to-Exchequer allocation required for Other Tax Revenue. No parser, qualification, fixture, stored-record or production change is justified by this evidence.

## Exact source identity

The accepted [comparison bank](../../backend/tests/fixtures/kra/fy2025_26_primary_source_comparison_298.json) remains the numeric baseline. Seven bounded public GETs were captured on 1 October Chicago time, `2026-10-02T02:36:35.639993Z` through `02:37:02.702036Z` in UTC. Every response was HTTP 200. The official chain remains:

1. [KRA annual article](https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026), SHA256 `223cd63bdbb77e8eaf4cf3858ddb0aacd5b3bcbfcfcef7d3092136717186a986`.
2. [Embedded dashboard](https://krarevenue2526testingdashboard.bolt.host), shell SHA256 `96c865f0ea9aeca049ca4609fed881419d112e1da9d3a2761f02a6f41ed5213d`.
3. [Named bundle](https://krarevenue2526testingdashboard.bolt.host/assets/index-n9eGcpF_.js), 628,097 bytes, SHA256 `f3cf2fd1075f4af3eb0aafb92ed6c8a1e336437b2603a9dc67a28283561d03d7`.
4. [Linked KRA PDF](https://www.kra.go.ke/images/publications/FY25-26_Annual-Revenue-Performance_.pdf), 1,555,679 bytes, 16 pages, SHA256 `1eca29e68c9e203e4d84a15f5cc6fed2aa075893f7d586d2209e6750a24d52a4`.

The bundle and PDF are byte-identical to their accepted hashes. The fresh bundle also equals the decompressed committed fixture. Their fiscal period is July 2025 through June 2026; monetary comparisons below use billion KES, with trillion displays preserved in the bank. The official embedding relationship remains accepted.

## New chronology evidence and its limits

The [KRA search result](https://www.kra.go.ke/component/search/?searchphrase=all&searchword=KRA+performance) binds the annual article's exact URL and title to `08/07/2026` in its KRA Revenue Performance category. That captured HTML has SHA256 `1dcd3c4e68b8a3dde10af451245fd2b9de10871ed62fc69bdd430aeb5213d0d4`. Following the result returns the same dashboard article, not an independent prose edition. This is an article-index date; it does not date the captured bundle bytes or certify publication/revision of any observation.

The PDF's embedded metadata states:

| Field | Exact value |
| --- | --- |
| CreationDate | `D:20260710064505Z00'00'` |
| ModDate | `D:20260710065050Z` |
| Producer | `iLovePDF` |
| HTTP Last-Modified | `Fri, 10 Jul 2026 06:51:19 GMT` |

These describe file processing/serving. Comparing them with the article's index date does not establish which numeric edition was revised or preferred. The article's own HTTP Last-Modified coincides with retrieval (`Fri, 02 Oct 2026 02:36:42 GMT`); it supplies no reliable release chronology. The bundle's displayed last-updated month remains June 2026. Keep observation publication dates null; retain these separate date clues without promoting them to publication dates.

## New source discrepancies beyond the accepted bank

| Measure | Dashboard field/display | PDF, page 12 |
| --- | --- | --- |
| Non-oil Customs collections, billion KES | 618.397 | 618.375 |
| Oil Customs collections, billion KES | 370.383 | 370.383 |
| Domestic revenue growth | 9.7% | 9.6% |
| Domestic target performance | 93.0% | 92.9% |

Dashboard locators are `customsPerformance.oilVsNonOil.nonOil`, `.oil`, and `domesticTaxesPerformance.growth`/`.performanceRate`; `customsVsDomestic.domestic` repeats the domestic rates. The non-oil difference is 0.022B KES at the same displayed precision. The dashboard's two import streams sum to its 988.780B Customs figure. The PDF streams sum to 988.758B against its 988.757B headline; that 0.001B difference can be compatible with independent rounding and does not justify alteration. Neither arithmetic check authorizes a residual or preferred edition.

Agency/PAYE/Customs/domestic-excise differences in the accepted bank remain unchanged. PDF page 11 identifies multiple agency levy categories; neither that page nor the dashboard's agency definition supplies a department allocation. The dashboard defines Exchequer as collections remitted to Treasury and agency as collections for other government agencies. The oil/non-oil split distinguishes import streams, not Exchequer versus agency receipts. It cannot fill the missing allocation.

## Bounded investigation and controls

Fresh GETs additionally covered the [press-release listing](https://www.kra.go.ke/news-center/press-release) and [performance category](https://www.kra.go.ke/184-kra-revenue-performance). The current listing parser's newest annual-revenue candidates remained July 2025. Official-domain searches covered FY2025/26 annual/revision/erratum terms, the PDF filename and the conflicting exact figures. No explicit replacement/erratum or required allocation was located within that bounded scope. This is not proof that none exists elsewhere.

Executed controls: 59 passed, exit 0, no skips. An independent `pypdf` extraction corroborated the metadata and pages; stdlib HTML parsing verified embed/script relationships. Raw field/value checks bound the new dashboard figures and Decimal arithmetic checked the stream sums/difference. Visual inspection covered PDF pages 11-13. Pure current `kra_discovery.py` execution retained the dashboard's PAYE/Customs edition, accepted supported collections, returned no residual, rejected an absent required head, distinguished an alternate period and returned no release for absent source data. Capture controls rejected wrong hashes and empty bytes. The module was loaded directly without application settings/database imports in an allowlisted child environment.

Two verification setup attempts exited 1 for missing libraries (`pypdf` in the existing backend runtime, then `bs4` in the bundled runtime). The verifier was changed to stdlib HTML parsing and run successfully with bundled Python/pypdf 6.10.0. No dependency was installed or modified. No backend suite, fetcher/writer runtime, PostgreSQL, production API/UI or human language acceptance was executed; previous such receipts remain inherited.

An independent GPT-6.1 Sol/high reviewer executed 41 read-only source/identity/date/definition/arithmetic and pure parser/listing controls in two allowlisted child runs, both exit 0. It confirmed the evidence and found no remaining load-bearing issue. An initial review of the note during verifier expansion caught the stale 53-control count; the final note and receipt both report 59. The review is local evidence verification, not source-owner or production acceptance.

Raw bytes, response URL/hash/time/header manifest, both external capture/verification scripts, PDF text and source-page renders are retained under `ROUND12_SESSION_6_` in `/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170/`. The complete executed control receipt is `ROUND12_SESSION_6_VERIFICATION.json`; response identities/times are `ROUND12_SESSION_6_CAPTURES.json`.

## Continuing owner/source decision

Before choosing an authoritative revision, obtain an explicit publisher revision/replacement statement binding the exact artifact, or a defined measure/edition policy that justifies one bounded observation while retaining the other. A human owner may choose a clearly labelled display edition as policy, but that choice cannot certify supersession or create an allocation. Any ingestion still needs the separately reviewed exact source/schema/delta/recovery basis and production authorization. Preserve incompatible editions and continue withholding the residual and partition shares.

Duplicate candidates: the expanded numeric/rate discrepancies and chronology ambiguity belong to existing #298, with the completed prevention work in #334/#341. No new independently reproduced code defect or separate ticket is proposed. Actions, GitHub, production data/configuration and signed caches were not changed.
