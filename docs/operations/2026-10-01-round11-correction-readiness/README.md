# Round 11 exact correction and freshness readiness — 1 October 2026

This packet prepares review of remaining production acceptance for #319/#306/#379/#380/#273/#274/#231/#298/#322. **No production action is authorized or executed.** Actions stays disabled. The original acceptance issues remain open.

Prepared on `codex/round11-production-correction-readiness`, pinned commit `355c057a6138ed47212a5aab865f4bdf26a02177`, tree `57d55dfdb1c01b04f92297edd02ff6a78a8e4cbf`. Initial branch/HEAD/tree matched and porcelain was clean. All repository work used the assigned checkout; the dirty primary was preserved.

[decision-ledger.json](decision-ledger.json) gives each action's owner, exact targets, before/after contract, existing tool, refusal, recovery, acceptance and continuing decision. [approval-and-recapture.md](approval-and-recapture.md) makes the future review request concrete. [backup-and-restore.md](backup-and-restore.md) specifies the full restore gate. [bank-index.json](bank-index.json) binds the dated inputs and tool versions to file SHA256s and distinguishes canonical plan digests. [verification-receipt.json](verification-receipt.json) records this session's executed local controls.

## Exact remaining decisions

| Action | Reviewable change | Continuing gate |
| --- | --- | --- |
| S4-OAG / #379 | Audits 5545/5679/5716 and extractions 6023/6158/6196: three finding-text corrections and three audit payload hashes, source 2541 unchanged | Fresh exact reflected plan, source bytes/replay, full backup/restore, owner approval, public text acceptance |
| S4-CPI / #380 | 67 lowercase cpi and 86 uppercase CPI January 2025: 143.08→142.68; 87 uppercase CPI December 2024: 142.47→141.66; coherent monthly February 2019=100 source/evidence/unit/publication | Exact KNBS PDFs, source/table/row/context plan and digest, allocated/reused evidence IDs, owner approval, publication and next-writer checks |
| S4-PUBLISHERS / #273/#274/#319 | Only publisher 1840 Treasury→CBK and2383 OCOB→Treasury | Complete fresh source-FK catalogue/reference IDs; two-column-only delta; exact SQL/recovery approval |
| S4-CODES / #306/#319 | Four metadata paths: entity 4 Mombasa 047→001 and entity3 Nairobi 001→047, FY2024/25 andFY2025/26 | Full identity/metadata recapture; exact four-cell SQL/recovery approval |
| S4-CLEANUP / #319 | Exact retired economic_profile47, missing_funds_cases3, audit_summary8; audits 870–894 | **Actual post-code recapture**, reviewed drift and newly rendered forward/recovery SQL approval |
| S4-KRA / #298 | Preserve dashboard/PDF versions; incompatible residual/partition withholding | No exact stored write approved from this bank. Obtain complete bounded source/delta/recovery before proposing ingestion |
| S4-FRESHNESS / #231 | Existing signed seed→validation→API invalidation→frontend revalidation→render chain | Owner platform configuration, billing/access, separate final Actions approval and actual end-to-end acceptance |
| S4-UMBRELLA / #322 | Track remaining linked source/data/public acceptance | Optional c415a10d2026 schema/source adoption is separate; predecessor remains supported |
| S4-HISTORY / #347/#378 | Recover original identities/source/actor/authorization; actual pipeline acceptance | Tuple/count clues do not authorize restoration; latest billing block ran no application steps |

Public route IDs are compatibility identifiers: Mombasa 047 andNairobi 001 remain unchanged even as official `code` fields remain001/047. No financial-record swap is proposed.

Population79 is the accepted World Bank2019 observation, 51,202,827, with **no write or recovery**. Preserve all 47 current source-backed project arrays and companion metadata; none of the 21 old arrays matches the current bank. Preservation does not certify disputed project amounts. Sources1823/2541 must never be globally relabelled or retired. Retain1707/1718/1822/1836/1840/2383/2430 and every shared reference.

The September30 stored-record capture was observed `2026-10-01T03:18:32.198331Z` (September30,10:18 p.m. Chicago). It records1840 with zero observed FK references,2383 with loan 426 only, and2430 already CBK with loans 381/383/384/439. Original issue counts of five/48 are historical. The inherited authorization packet's file SHA256 is `7466a7e44860fb555a1094c4a5b8b48dcad0d4014920e2db71fcea63f0f2e75e`; its status is review-only.

## Serialized dependency order

1. Release owner verifies deployed prevention/tool commit and disabled Actions, approves a competing-writer freeze and obtains full backup plus isolated restore proof.
2. Source owners refresh hash/page/version evidence and capture complete exact READ ONLY plans. Owner authorization names each fresh plan, digest, execution artifact and recovery receipt. Preparation/merge approval grants no production write.
3. Reconcile Session3's OAG source/preservation matrix and perform only separately approved OAG/CPI corrections, serialized. Broader national2392 proposals remain excluded.
4. Recapture complete references after those changes, review/apply publisher-only correction if approved, then the exact four county-code cells.
5. **Recapture actual post-code state** with every later unrelated metadata field. Regenerate cleanup using the existing renderer. Obtain a new exact cleanup manifest/forward/recovery authorization. A projected after-codes manifest is never proof that the code write happened.
6. Consider KRA publication only after its independent full bounded source/delta/recovery review. Whole national-debt fixture replay is excluded.
7. Coordinate Session3 catch-up only after source/preservation/history/configuration gates and the owner's final Actions authorization. Require successful seed and full validation, then signed API invalidation, exact frontend path acknowledgement and observed rendering without another deploy.

Each action also requires postcommit READ ONLY comparison against concrete before/after images. Recovery follows reverse actual dependency order: cleanup into approved post-code state, four code paths, publishers, then other corrections in reverse execution order. Refuse intervening drift. A lost commit acknowledgement is resolved by reading the database and intent/resolved snapshots; receipt existence is not completion.

The new Session3 handoff is a required coordinator integration input at `ROUND11_SESSION_3_HANDOFF_2026-10-01.md` beside the assignment. Its manifest is owned by Session3 and must not be rewritten here. Until that handoff is integrated, no catch-up authorization is implied.

## Evidence and limits

Fresh work here: actual issue bodies/latest comments via read-only gh; repository Actions disabled and CI/Docker/seed manually disabled, zero running/queued runs; offline bank hash and invariant controls; existing renderer and actual workflow-shell response tests. Dynamic Copilot entries remain listed active; repository permission is disabled and no paid review was requested.

Banked source/production/PDF/PG/browser receipts remain dated inherited evidence. No production DB or credential connection, new production snapshot, public/source re-fetch, secret/configuration edit, deployment, signed request, seed, migration, cleanup or full database restore occurred here. The packet uses the accepted source bank rather than repeating large eight-PDF/PG rehearsals. No source-supported code defect required a new repair path.

Current code supersedes the old CPI proposal's narrative: public readers now use the source-bound gate (`backend/routers/economic.py:588`); unsupported CPI supplement is retired. The old `fixture_prerequisite.proposed_after` is a recorded alternative, **not** today's chosen fixture write. Follow the chosen retirement and current cpi-execution runbook. Banked observations are not fresh deployment confirmation.

The older cpi-execution statement that population 79 still cites1823 is also superseded by the later complete source bank. Population79 has source_document_id NULL;1823's remaining population reference is row64,entity 73, alongside GDP 17/18 and CPI86/87. Preserve those shared dependencies; no global label or retirement is authorized.

#298's official embedded dashboard relationship is accepted evidence, despite the host name. Dashboard/PDF hashes, figures, null publication dates and accounting bases remain distinct. No preferred revision, inferred Customs allocation, residual balancing or fixture-on-source-failure publication is proposed.

#347 still needs original full identities/lineage and actor/time/authorization. January 2024=6.3 is not source-verified January inflation from the reviewed table (that table says6.9 forJanuary and6.3 forFebruary). Do not fabricate history or reset baseline11. #378's administrative zero-step failure is not a code regression; actual earlier validation/source/freshness acceptance remains outstanding.

The optional county schema revision `c415a10d2026` follows `ea1645a4c0b5`. Static caller inspection found `record_county_debt_observation` only at its definition and test caller; no active source-ingest adoption was found in the backend. The compatibility reader checks both relations (`backend/services/county_debt.py:262`): wholly absent tables retain legacy behavior and partial adoption raises. These are inspected code/caller facts; full runtime compatibility proof is inherited Round10 evidence linked in [#322's operational comment](https://github.com/Rodgers31/audit_app/issues/322#issuecomment-5942486225).

Focused tests executed here: **24 passed, no skips** (12 cleanup renderer;12 actual refresh shell controls, including malformed successes and valid ordered control). Environment was allowlisted;dotenv/Pydantic env files disabled;runtime SQLite and engine URL read back;web seeder/warmup disabled;Redis empty;app startup/shutdown hooks cleared;test outbound HTTP guard active. This is SQLite renderer validation and loopback HTTP shell behavior, not PostgreSQL production parity or a browser run. Banked cleanup30PG/publisher 13PG/OAG/CPI/refresh-browser proofs are inherited, not rerun.

The first launcher attempt failed before tests because in-memory SQLite rejected configured pool options. It was corrected to an owned synthetic SQLite file while keeping the fixture's SQLite-memory contract. No application patch was needed and the failed setup is not a product regression.
