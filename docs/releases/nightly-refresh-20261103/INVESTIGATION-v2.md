# Nightly refresh investigation and completion repair

Prepared 3 November 2026, America/Chicago. Base `8f08d85a1b059b83d8b8a3823f5f06fd33eb4e39`, tree `429c94692890811fcab68668c5ee1ecd19226c5e`; branch `codex/nightly-audit-refresh-20261103` in its managed isolated checkout. The primary and release checkouts were not edited.

## Actual incident

Both [scheduled 41376655325](https://github.com/Rodgers31/audit_app/actions/runs/41376655325) and [41564784862](https://github.com/Rodgers31/audit_app/actions/runs/41564784862) failed their terminal ingestion-results check because fiscal summary used `no_live_overlay_applied` and national pending bills used `brop_unavailable`. Treasury requests logged certificate-expired transport failures. County pending-bills work and other domains could commit independently. Database integrity validation checked existing rows and passed; cache/page refresh was blocked by the failed seed job. This is not evidence of a complete source refresh.

Audits separately returned `completed_with_errors`: document 2392 proposed 335 retirements and two revisions. The old workflow treated that as WARN and the domain marked the overall source LIVE when sibling PDFs succeeded. It was not the direct terminal failure in either run. The earliest occurrence established by the retained incident inventory is 2 November UTC (1 November Chicago); the next scheduled run repeated it on identical PDF and row-proposal hashes. This does not establish the first occurrence across all earlier history. Treasury incident [868](https://github.com/Rodgers31/audit_app/issues/868) was already open on 1 November UTC; [888](https://github.com/Rodgers31/audit_app/issues/888) records the failed/blocked job chain.

The earlier green manual audits run 41312227919 had eight acquisition/discovery errors and received HTML for this national PDF; it never parsed document 2392. The green national-budget-only run 41311313399 covered a different domain. Selected county catalogue acceptance, DB integrity, startup checks and release builds cannot substitute for full PDF/domain acceptance.

## Exact retained-byte reproduction

The retained official [FY2024/25 national PDF](https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf) is 13,428,198 bytes, MD5 `7e6a6850102a3cadcba38e1f7af9cae3`, SHA-256 `d8c72b4fbda2c920f30f79b3e0554f9965165735d220a810e6ae3994e2dbf899`. An owned copy came from the existing local PDF cache; there was no live source request.

Running the archived parser from `1bd397f398450245da83abc2e24502ab16ffb063` (parent of #327) and the reviewed current parser over the same page text reproduces both complete row digests exactly:

| Comparison | Reproduced result |
|---|---|
| Historical rows | 813; digest `0c0fc620b3f9a50383f900b008d0478cffd117c8754aabb17357501f8f515366` |
| Current candidate | 1,867; digest `031454f9471868ddd822a289220710a10b670040e4c2b9c35ef1d2e380fd4857` |
| Absent historical keys | All 335 proposed retirements match exactly |
| Revisions | IDs 39 and 265: both before and after payloads match exactly |
| Added candidate keys | 1,389 |

Those are row digests, not PDF digests. Parser drift is sufficient to explain the whole stored-versus-proposed difference without a publisher reissue. The original historical acquisition artifact was not independently retrieved; this is exact counterfactual reproduction on retained official bytes, not a claim to have recovered that past runtime.

Of the retired rows, 329 are historical table entries: 304 carry only a title and 25 carry text belonging to another paragraph. The old three-digit grammar missed national paragraphs after 999 and emitted numbered historical-list rows as current findings. On PDF pages 448–449 the archived parser emits table items 1–24; the current walk emits paragraphs 1402–1404. Six other rows (136, 142, 239, 350, 441, 447) are “no material issues” statements the old clean-statement grammar missed. The two revisions restore text that the old appendix rule truncated (PDF pages 39 and 227–228). The current parser already contains these repairs; this PR does not invent another parser revision or approve the reconciliation.

The bounded forensic reader calls the current `read_pages`, closes completed page caches, uses one low-priority process and a 120 CPU-second cap, and peaked near 151 MB RSS. With OCR disabled it retained one rejected page; body findings still reproduce both nightly row digests exactly. This proves the parser-difference diagnosis, not complete PDF/OCR acceptance. All 335 retirements, two revisions and 1,389 additions remain unapproved.

## Engineering change

The actual workflow now requires complete current outcomes for audits, fiscal summary and pending bills. Missing, malformed, partial, held or contradictory completion metadata fails. Other domains retain their established PARTIAL/WARN policy; intended previews are checked separately from live refreshes.

Audits verifies parser identity, exact retained extraction count and current source/version stamp, then validates a nonempty consistent loader inventory inside the same extraction/load savepoint. Failure rolls back that document and retains its failed-attempt/proposal evidence. Per-document accepted/skipped/not-requested outcomes reconcile to the domain/job totals. Errors and deferrals report PARTIAL; no accepted document reports REFUSED rather than claiming a fixture was served. The workflow prints bounded held-document counts and source/candidate identities.

Pending bills retains separate national/county outcomes. A successful county cohort cannot hide BROP fallback; parsed records skipped by the real publication-qualified writer do not count as accepted. A failed embedded BROP fetch always replaces an earlier LIVE mark with the present fallback and retains its diagnostic. This does not create a compatible source for an officially unreported county or qualify a national total from county figures.

Fiscal completion requires confirmed writer counts, exact accepted fiscal-year identities, live budget/revenue/framework components, and empty missing/unreadable/unconfirmed inventories. Fetch, parse, quarantine, validation and write failures cannot retain a LIVE completion verdict. Existing amount, period, provenance and publication validators remain in force.

The registry's normal and bounded audit paths share the new parser/loader checks; retries and resumed/deferred work return through the same domain handler. Native CLI/admin entry points use those registered domain handlers. Direct parser/writer calls remain lower-level operations and do not certify a complete nightly. The workflow consumes only jobs above its existing run-ID floor and the selected plan. No admission pin, review allowlist, TLS trust policy, HTTP client, worker, source registry or automatic generation policy is changed.

## Validation and provenance

The final explicit selection passes **276 distinct tests per mode**, normal and optimized Python 3.13, with zero failures, errors, skips or unexpected successes. Raw output and JUnit identities agree. Optimized execution propagates `PYTHONOPTIMIZE=1` to the actual workflow child. These are local SQLite/inert-source checks, not deployed Python 3.12/PostgreSQL or hosted acceptance.

Two independent executable reviews pass: the gate review executes 173 helper controls and 12 actual workflow cases per mode; the domain review executes source/count/period/publication/rollback controls plus the 49-case regression module. Selections overlap and are not added to the 276 count. Every reproduced finding was classified valid, pinned red, repaired and replayed. Positive full-proof fiscal and idempotent audit controls pass.

Original setup failures, false-green reproductions and producer bytes remain retained. The v1 report publisher refused its own tuple-versus-JSON-list readback; its unchanged packet is explicitly superseded by this v2 publication, with no change to executed test outcomes. A forensic v2 child succeeded while an unrelated test changed, so its recorder correctly refused source binding; the fresh v3 replay is source-stable. Earlier optimized review children that remained normal-mode are explicitly historical; final review measures both parent and child optimization levels. Local API fallback tests explicitly bind the actual root ETL package because `backend/etl` shadows it in the native checkout; import-failed runs are retained separately. No historical report or receipt is overwritten.

Canonical lane evidence is under `/Users/roger/.codex/visualizations/2026/11/03/01a1a1aa-4937-7241-97b9-9bc3b183628c/nightly-audit-refresh/`: `published-{normal,optimized}-9.{json,log,xml}`, `blue-book-full-bounded-v3.{json,log}`, immutable replay producers and inputs, `review-gate/FINAL_REVIEW.{md,json}`, and `review-domains/period-fixed-1/FINAL_REVIEW.{md,json}`. `FINAL-v2.json` and `EVIDENCE_MANIFEST-v2.json` bind their bytes and this report. Parent incident evidence is read-only in the separately retained 131-artifact `nightly-explanation` packet.

## Remaining acceptance and owner input

1. The official transport owner must qualify Treasury recovery with normal TLS verification and its source acquisition evidence. This lane does not repair an expired public certificate by bypassing verification.
2. An independent source/content reviewer must assess the exact bound Blue Book proposal, including historical-list attribution, clean statements, restored appendix text, additions and document/OCR completeness. No executable approval for document 2392 is added here. Published findings remain protected by the existing review boundary.
3. The coordinator owns any later reviewed deployment, admission-pin change and ordinary full scheduled acceptance. No extra hosted dispatch/rerun or live DB write is authorized by these fixtures or this diagnosis. A green full scheduled receipt must separately establish every required source and the cache/page-refresh outcome.
4. Serving-runtime/PostgreSQL checks remain a declared release-dependent limit while the parent release lock is held. Any newly surfaced unversioned/unsupported single-report extraction must be qualified, not exempted merely to obtain green.

Publishing, uploads, workers, financial generation and native/automatic source admission are not activated. This lane performed no production DB/provider action, live seeding, hosted rerun, merge, deployment, paid review or resource creation.

Report producer SHA-256: `d92264da91585d5dd937dee33d4572f3d522a65fc665530189fb219288584c96`.
