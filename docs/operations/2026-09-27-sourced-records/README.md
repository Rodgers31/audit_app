# Sourced population and officials — Session 2

Implementation is prepared for review in one draft PR. This directory is a **review-only, pre-release handoff**. No production seed, update, deletion, merge or deployment was performed. The snapshots contain retired, unsupported claims as before-images; they are not publishable evidence.

## Writer ownership and reproduced defects

Base: `dc58685bb72007a5654863bfbeee912cfd6b89e3`, freshly fetched `origin/main`.

- Web boot/full refresh and the periodic tick no longer dispatch population. Direct legacy calls refuse before fetching or opening a database session. The dedicated population domain owns World Bank national observations and the validated KNBS census county table. Unrelated web schedules remain exercised.
- Bootstrap no longer writes county or national population, governor names, economic profiles, or the synthetic county-budget documents formerly attached to populations. The partial-database/forced county loop preserves a sourced official and its provenance together. Ordinary `force=False` calls skip that loop once 47 counties exist; no ordinary complete-database governor overwrite was demonstrated. **The old national population overwrite was outside that county skip**, so an ordinary run could replace the World Bank 2019 total and document while retaining World Bank metadata and sex counts.
- The population domain no longer reads `population.json` or merges fixtures after a source failure. The wrong county fixture, its unused setting and its typed-in generator are retired. National updates replace evidence and values together, revoke inherited publication state, and refuse malformed observations. A failed or disabled source preserves existing records.
- `PopulationData.confidence=1.0` is the application's ingestion score for a directly retrieved, accepted publisher observation, matching the existing model default and the census loader's direct-source convention. It does **not** measure the uncertainty of the World Bank population estimate; the World Bank API supplies no uncertainty score. The writer sets it explicitly on both inserts and replacements after source and shape validation, so a prior row's score cannot survive under new provenance. The `/economic/population` endpoint filters on this field with a default threshold of 0.7; storing NULL would hide accepted World Bank observations there. Population estimate uncertainty remains unquantified in this field.
- The census loader resolves country-scoped county identities across existing and bootstrap-created slugs without changing any entity ID or slug. Previously a fresh bootstrap's `mandera-009` and its 46 peers were unresolved by a loader expecting `mandera-county`. The validated census update carries its current PDF hash, extraction and page; ambiguous county identities refuse the whole census.
- The unused insecure CBK debt fetcher and the legacy population scraper/aggregator path are removed. No extractor was added to the web image. Root and backend Docker contexts exclude nested secret decoys; the root context retains the public KNBS trust bundle. This proves packaging behavior, not prior exposure of real credentials.

The scheduled path is `.github/workflows/seed.yml` → seeding CLI → population domain. Web startup/periodic dispatch is explicitly excluded. The historical general `etl/database_loader.py` population branch is insert-only and source-linked; it is not used by this population domain or the web population refresh and was not rewritten here. The legacy parser remains available to other ETL consumers.

## Primary population evidence

[KNBS Volume I, Table 2.2](https://www.knbs.or.ke/wp-content/uploads/2023/09/2019-Kenya-population-and-Housing-Census-Volume-1-Population-By-County-And-Sub-County.pdf#page=17) reports Mandera **867,457 persons**: 434,976 male + 432,444 female + 37 intersex. It reports Kenya **47,564,296**. These are census counts, reference midnight 24/25 August 2019. The table is printed page 7 / PDF page 17, not printed page 17. The downloaded November 2019 publication was rendered and inspected; the existing geometric extractor reconciled all 47 county rows and the national total. `census-source-receipt.json` records the URL, SHA-256, units, period and page.

Production Mandera population row **26**, Entity **12**, already contains 867,457 with document **2435**, extraction **4345**, page reference `p. 17`, and the same sex components. No Mandera production correction is proposed.

Production population row **79** is a mixed observation, not just a wrong source label:

| Field | Stored read-only observation | Reviewed World Bank 2019 replacement |
|---|---|---|
| Entity / year | NULL / 2019 | unchanged |
| Total | 47,564,296 | 51,202,827 |
| Male | 25,485,390 | unchanged |
| Female | 25,717,437 | unchanged |
| Metadata source | World Bank Development Indicators (2019) | same publisher; add SP.POP.TOTL and source URL |
| Document | 1823, bootstrap CBK debt/KNBS economic-survey composite, no URL | NULL; the JSON series has no PDF/page citation |

The [total](https://api.worldbank.org/v2/country/KEN/indicator/SP.POP.TOTL?format=json&date=2019), [male](https://api.worldbank.org/v2/country/KEN/indicator/SP.POP.TOTL.MA.IN?format=json&date=2019) and [female](https://api.worldbank.org/v2/country/KEN/indicator/SP.POP.TOTL.FE.IN?format=json&date=2019) responses all declare `lastupdated=2026-07-13`. The female request timed out once; a bounded retry succeeded. All three raw responses and full before/after row images are in `population-79-proposal.json`. This proposal follows the actual World Bank observation, not a relabel inferred from magnitude. KNBS and World Bank remain separate source/period claims.

## Exact cleanup handoff (#319 and #306)

The reader used `BEGIN READ ONLY`, verified `transaction_read_only=on`, then required an INSERT inside a savepoint to fail with `ReadOnlySqlTransaction` before querying data. `production-readonly-receipt.json` records the newer bounded read, source documents, all 13 observed source-document FK columns and their row IDs. The earlier fresh cleanup snapshot matches every retired value in the prior reviewed manifest; the full before-images are retained here.

| Scope | Exact review boundary |
|---|---|
| Retired metadata | 47 economic profiles, 21 stalled-project arrays (25 project records), 3 missing-funds arrays, 8 audit summaries; IDs and full removed values in `cleanup-current-manifest.json` |
| Retired audits | IDs **870–894**, all exact previously reviewed fixture matches, document **1836** retained; no inbound audit FK observed |
| County codes | Entity **4 Mombasa**, FY2024/25 and FY2025/26 `047→001`; Entity **3 Nairobi**, same periods `001→047`; only these four JSON paths |
| Document 1840 | Retain: loan IDs **381, 382, 383, 384, 439** still cite it. Loan 382 survived #318. Session 1 must supply any post-refresh reference change. |
| Documents 1707 / 1718 | Zero observed database FK references across the 13 checked columns; candidates for separate review, **not deleted by these scripts** |
| Population 79 | Separate exact source repair proposal; excluded from bulk cleanup |

The four stored code cells do not establish crossed financial records. IDs, names, slugs, amounts and foreign keys remain unchanged. Public codes were already corrected in the preceding release.

Sequence for a future authorized cleanup:

1. Deploy the writer protections. Complete source-refresh dependencies coordinated by Session 5, including Session 1 document references and Session 3 project metadata. Session 5 currently reports no scheduled production writes while shared revalidation configuration is unresolved.
2. Freeze competing writers for the bounded transaction, take an external database backup, and prove its restore separately. The prior #318 backup/release authorization does not authorize this cleanup.
3. Recapture full rows, all 47 identities, exact code cells, source documents and references; review all drift. The current manifest is a pre-release snapshot, **not approval to execute after future writes**.
4. Apply the reviewed four-cell code proposal first if still necessary. `county-codes.sql` and `county-code-recovery.sql` both end in `ROLLBACK`. Recovery verifies the expected corrected cells and identity before restoring just those paths, preserving unrelated newer metadata.
5. Recapture the actual post-code metadata. `cleanup-after-codes-manifest.json` is only the projected result of exactly those four edits. Reuse the existing generator: `python tools/prepare_legacy_evidence_cleanup.py MANIFEST.json OUTPUT_DIR`. Its forward and recovery scripts end in `ROLLBACK`; no migration hook or automatic commit was added. A pre-code manifest correctly refuses the corrected metadata.
6. Obtain release-owner approval for the concrete final manifest/backup/recovery plan before any production commit. Verify returned IDs, full unrelated metadata, references and published source/period values; coordinate backend/frontend cache refresh with Session 5.

## Executed verification and limits

- Six root regressions failed on original bootstrap/web behavior and passed after the ownership changes. Independent tests executed the original population modules from main: all 33 ownership cases failed; current implementation passes, including positive World Bank/census/zero controls and malformed inputs. Fresh-bootstrap → census ingestion writes all 47 counties; a subsequent normal bootstrap skips county loading.
- A domain-status regression with a valid positive control refuses to call a run live when the national writer rejected its observations, even if the census succeeded.
- `tools/verify_population_docker_contexts.py` invokes Docker's actual ignore engine using secret-free scratch contexts. The original backend context shipped 20 decoys and the original root context omitted the public trust bundle. Current contexts each exclude all 27 decoys and retain their required public files. No full production image or real-secret context was built.
- `tools/verify_sourced_record_cleanup.py` executed **25 checks** on disposable PostgreSQL 17.11. Exact current cleanup/recovery and the four-code-cell → projected cleanup → recovery sequence passed. Default scripts rolled back. Metadata, document, audit-row, reference, identity and newer-value drift refused atomically. Full captured before-images were used with a synthetic schema and related FK/budget controls; this is **not a full production restore** or evidence that every production FK was rehearsed. `cleanup-rehearsal.json` pins inputs/harness/renderer hashes and reports database removal.
- The first core run from repository root had one test-harness working-directory error (`cache` could not import in its subprocess), plus two quarantine-count failures because three retired fallback sites were removed. The backend-directory rerun fixed the import issue; the ratchet is reduced from 28 to 25. Final core results are recorded in `verification.json`.

No issue is closed by these local checks. #293/#300/#305 need reviewed merge/deployment; #292/#319/#306 retain the explicitly separate stored-data acceptance above. No signing credentials were rotated and no emails were sent.
