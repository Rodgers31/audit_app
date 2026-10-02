# Stored-record recovery and fresh decision delta — 2 October 2026

Recovery from retired-audit cleanup now refuses if any new audit references document 1836, including an ID outside the approved retirement set. The check runs under the existing locks before restoring county metadata or inserting audits. Previously recovery checked only occupied target IDs; a newly inserted audit on 1836 allowed it to restore fixtures against changed source coverage. This is a reproduced local tooling defect under #319, not an observed production recovery.

The existing `tools/prepare_legacy_evidence_cleanup.py` remains the sole cleanup renderer. Forward cleanup is unchanged; both directions still end in ROLLBACK and retain source 1836. `tools/verify_sourced_record_cleanup.py` includes the regression, a valid different-source preservation control, actual local post-code metadata readback, and generating-tool hash/readback in its receipt. No production executor or document-deletion path was added.

The baseline renderer at `280353055ac5f6a049cf759c3ac38f3608f2492b` accepted recovery with a new audit ID 900001 on source 1836. The regression harness stopped after 22 prior successful checks with `Unsafe success; expected: Document 1836 post-cleanup coverage changed`. The final renderer refused that recovery atomically; all 33 PostgreSQL checks passed. The first attempted red run failed during PostgreSQL startup and is excluded from defect evidence. The new coverage check also preserves unrelated-source audits during valid recovery. An independent removed-guard control reproduced the unsafe restoration.

Fresh local verification:

| Execution | Result | Evidence in the shared Round16 directory |
| --- | --- | --- |
| Cleanup/code-order/recovery rehearsal, PostgreSQL 17.11 | 33 checks passed | `ROUND16_SESSION_5_RECOVERY_FINAL.json` / `.log` |
| Exact publisher forward/recovery rehearsal | 13 checks passed | `ROUND16_SESSION_5_PUBLISHER_REHEARSAL.json` |
| Renderer/publisher pytest selection | 29 passed, no skips | `ROUND16_SESSION_5_REGRESSION.log` |
| County identity/API/route pytest selection | 112 passed, no skips | `ROUND16_SESSION_5_IDENTITY.log` |
| Independent recovery verification | 28 checks and 17 direct render probes | `ROUND16_SESSION_5_REVIEW_RECOVERY_ADVERSARIAL_FINAL.json` |

Both pytest runs resolved the synthetic application target to 127.0.0.1:5475/round16_session5, disabled dotenv/Pydantic env files, seeder/warmup/lifespan, and unstubbed provider HTTP, and reported zero application-engine connection attempts. PostgreSQL rehearsals used separately generated disposable databases, dated complete before-images, and synthetic related tables/FKs. They do not establish a full production restore, production schema parity, ingestion, cache adoption or rendered/public acceptance. The regression executes in the PostgreSQL rehearsal tool; it is not a source-text pytest assertion.

S03 supplied fresh read-only shared captures at **2026-10-02T15:18:19.369746Z** and **15:24:51.942334Z**. They are separate transactions, not a consistent combined snapshot. This session made no production reads or writes. The first capture SHA256 is `cc1552f923ce3399627cf959df084a91a718fd1397a06eb10df7dcb66094b3c3`; the supplement SHA256 is `08ef2f8eb6ddab9541a4a346f992e262d862dbc109e472cb9fe629b159135dfb`. The derived decisions are in `ROUND16_SESSION_5_CAPTURE_DELTA_V2.json`, with exact reference IDs and generator/input hashes.

| Target | Fresh observation | Decision |
| --- | --- | --- |
| 1840 | Treasury publisher; no references across 13 source FK columns | Publisher-only CBK correction remains pending; do not delete or infer April 2025 edition contents |
| 2383 | OCOB publisher; loan 426 is its only captured reference | Publisher-only Treasury correction remains pending; preserve title, URL, ID and reference |
| Entity 3 Nairobi | FY2024/25 and FY2025/26 code `001` | Two official display-code cells remain `001`→`047`; route `001` stays Nairobi |
| Entity 4 Mombasa | Same periods code `047` | Two official display-code cells remain `047`→`001`; route `047` stays Mombasa |
| Population 79 | Complete accepted World Bank 2019 row; total 51,202,827 | Already satisfied; no correction or recovery. Only confidence/date transport formatting differs from the accepted image |
| 1707 / 1718 | No captured source FK references | No deletion authorized or rendered; zero references alone is not retirement evidence |
| 1836 | Audit IDs 870–894; no inbound audit FKs in the captured catalogue | Counts/identity projections cannot establish full current fixture matches. Existing cleanup retains the document |
| 1823 | Indicators 86/87, GDP 17/18, population 64 | Preserve shared source and unrelated facts |
| 2541 | 582 audit and 582 extraction references | Preserve shared source; S04 owns its correction |
| County metadata | 47 project arrays, 47 economic profiles, 3 missing-funds arrays, 8 audit summaries | Preserve projects; counts cannot replace exact before-images or prove current value legitimacy |

S03's first code projection read root metadata keys and returned null. Its supplement supplies the real nested FY paths and confirms all four stale cells. V2 explicitly supersedes only that earlier unresolved code decision; it does not fill missing complete rows from inherited captures.

The remaining capture gaps are concrete: complete source rows 1707/1718/1836/1840/2383 (the fresh projection omits `content_type`, `country_id`, `created_at`, `file_path`); all 47 current county identity/full-metadata images; and full current audit rows 870–894 with complete source coverage and logical dependency checks. Cleanup must be recaptured again from actual post-code/post-ingestion state. Fresh publisher-byte authority/hash checks, full consistent backup and successful isolated restore, coordinated writers, exact action/recovery approval, and public acceptance remain root-owned prerequisites. No executable manifest was regenerated from partial capture or simulated production after-state.

**Dated receipt correction:** the September 30 packet's authorization/hash bank and 30-check rehearsal describe renderer SHA256 `ed3453b4e18045d46667bf29bde7987f9daa7d57231f93e8036f33b67476eef0`. Their recovery-readiness interpretation is superseded for the untested changed-source-coverage case. The current renderer SHA256 is `a3d5c5e6994c8bd9e2eeb4dedb2d5a3405efcf62b62e3a9392755f2465d25215`. Re-rendering both identical old manifests showed identical forward SQL and only the three-line recovery refusal delta (`ROUND16_SESSION_5_RENDERER_DELTA.json`); this is tool change, not tree/data drift. Existing receipts remain dated and untouched. New production recovery SQL needs actual refreshed state and review, not approval inherited from the old packet.

Caller search found only the renderer CLI, the local PostgreSQL rehearsal and renderer unit tests in repository code. Every newly rendered recovery passes through the shared guard. Previously generated SQL is static and does not acquire it automatically; regenerate during exact-plan review. Duplicate search of the six assigned full issue snapshots and renderer history found the existing identity/source/reference recovery work under #319/#322, but no recorded coverage-drift regression. Record this fixed discovery under #319; root decides whether a separate issue is useful.

No assigned issue is wholly closable: #273/#274/#306 still require stored corrections and public acceptance; #319 requires actual approved cleanup; #322 and #230 retain their linked source/production/human acceptance. Population 79's completed criterion should stay completed. Actions remains OFF.
