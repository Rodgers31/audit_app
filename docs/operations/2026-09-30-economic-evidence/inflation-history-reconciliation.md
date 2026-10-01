# Historical inflation reconciliation — 30 September 2026

The historical 15-to-11 census change is unresolved. This CPI correction cannot reconstruct or authorize recovery of the removed inflation history. No restoration, baseline relaxation, annual reclassification or live data mutation is included.

## Separate measures

- `CPI` / `cpi`: monthly **index levels**, here national Overall CPI with February2019=100. These are the three #380 observations in the correction manifest. Case/type/date/ID identities remain distinct.
- `cpi_index`: World Bank annual index, **2010=100**; retain this separate base and annual period.
- `inflation_rate`: current World Bank CPI inflation **annual average**, each year at December31.
- `inflation_rate_12m`: CBK-hosted KNBS monthly **year-on-year percentage**; month-end dates. A monthly rate cannot be restored into the annual measure merely to restore a count.

## Captured surviving annual history

The September29 bounded READ ONLY diagnostic records national source1856, World Bank, https://data.worldbank.org/indicator/FP.CPI.TOTL.ZG?locations=KE, declared measure `CPI inflation, annual average` and source label `World Bank, World Development Indicators` for all eleven selected observations below. These are captured selected fields, not a newly read production snapshot or recovered full before-images. All are preserved by the CPI plan; the PostgreSQL regression reproduces these selected tuples with explicitly synthetic remaining fields and proves their full test images unchanged.

| ID | Observation date | Percent |
| --- | --- | --- |
| 35 | 2015-12-31 | 6.6 |
| 34 | 2016-12-31 | 6.3 |
| 33 | 2017-12-31 | 8 |
| 32 | 2018-12-31 | 4.7 |
| 31 | 2019-12-31 | 5.2 |
| 30 | 2020-12-31 | 5.4 |
| 29 | 2021-12-31 | 6.1 |
| 28 | 2022-12-31 | 7.7 |
| 27 | 2023-12-31 | 7.7 |
| 26 | 2024-12-31 | 4.5 |
| 98 | 2025-12-31 | 4.1 |

The captured diagnostic is `release-2026-09-29-receipts/inflation-production-diagnostic.json`, SHA-256 `f855343034713878b47bf2bf5f86b8485416920e2aa3ed7b4d5eca60ced1f10e`. The checked-in selected fixture labels the limits of the receipt; it is not a seed or restoration fixture.

## Removed tuple evidence and limits

| Off-cycle tuple | Receipt | What it establishes |
| --- | --- | --- |
| 2023-06-30 = 7.9 | September26 production-derived clone receipt reported in PR248; captured historical cross-check | Tuple existed in the clone. Original live row ID, source and full metadata remain missing. Its value matches an old bootstrap literal; deletion actor/time is unproven. |
| 2024-01-31 = 6.3 | Same clone; job3160 September28 removal tuple | Logged removal by the economic job, but the old-format record has no ID/source/full metadata or coverage proof. |
| 2024-06-30 = 4.6 | Same clone historical cross-check | Tuple existed in clone and matches bootstrap literal. January/December2024 KNBS tables give 4.6 as June2024 monthly inflation; this does not establish the missing original source or deletion chain. |
| 2025-01-31 = 3.3 | Same clone; job3160 September28 removal tuple | Logged removal. January2025 KNBS Table1 gives 3.3 as monthly inflation, distinct from index142.68 and annual-average2025=4.1. Original full lineage remains unavailable. |

A measure-specific caution: the reviewed January2025 and December2024 KNBS Table1 rows give **January2024 monthly inflation6.9**, and **February2024 6.3**. The historical tuple January31=6.3 therefore cannot be promoted to source-verified January inflation from these tables. It may have another measure, a dating error or unsupported lineage; without its original source/metadata, none of these explanations is established. Do not reconstruct a missing row from this clue.

The exact cached cross-check is `release-2026-09-29-receipts/inflation347-history.md`. It explicitly states that PR248 did not exercise bootstrap cleanup against PostgreSQL: a clone domain sweep removed the rows first. The two June tuples matching old bootstrap values and startup code are a deletion hypothesis, not an executed live deletion receipt.

The diagnostic records job3180 (September29) COMPLETED, errors[], removals[], annual coverage2015–2025. It records job3160 (September28) removal tuples for the two January observations and unrelated GDP2023-09-30=5.4, but no coverage/source/ID receipts. Jobs3128/3112/3095 have no saved removal/coverage identity receipts. Censuses3139/3123/3106 record count15 without identities; census3171 count11 without identities; census3191 count11 with surviving identities. A count difference cannot identify which actor removed which original row.

## Exact missing evidence

Obtain the original September26 production snapshot or pre-September27 backup, preferably from the release owner's retained provider backup/clone export. It must supply each removed observation's **original ID, exact type/date/entity/value/unit/confidence, source_document_id, source_page, complete metadata, created_at, extraction_id/page_ref/source_hash/basis/publication/quarantine fields, and any extra database columns**. Also obtain the referenced source document and extraction preimages/bytes/page/hash. The original census identities or exact database before/after snapshots are needed to link the15-row count to these four originals.

Recover the deployment/startup logs and original job receipts spanning the drop, with deployed SHAs, timestamps, removal identities and coverage, so the actual deletion actor/time and reviewed authorization can be determined. If the backup is only a clone, document when/how it was taken and whether prior test sweeps had already changed it. A production-derived tuple summary without original IDs/lineage is insufficient.

Only then classify each observation by source measure and period, preserve the currently sourced annual series, and prepare a separate exact before/after reconciliation with release-owner approval. Do not guess IDs, replace an absent source with a plausible monthly number, reinstate literals, reset the baseline to11 or close #347/#378 because a rolling validation window expires. No remaining annual-history code defect was independently reproduced here that justifies changing the existing guarded supersession/preservation logic.

## Current acceptance boundary

Current issue bodies/comments for #347/#378 were reread and captured in this session's receipt directory. #347 still requires original history evidence; #378 also retains county coverage, full validation and signed refresh acceptance. The latest account-billing failure and the intentionally disabled Actions workflows do not supersede those requirements. This note neither changes their gates nor claims pipeline acceptance.
