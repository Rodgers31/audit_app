# Native audit editions and financial source acceptance

Scoped work for [#802](https://github.com/Rodgers31/audit_app/issues/802), against deployed base `e1a0d6be0aa990064ab50b622c0e04570e84dd52`. This is local engineering and retained-source acceptance. No production ingestion, admission, backfill, merge, deployment or publishing operation is included. #802 remains open.

## Audit diagnosis and repair

Production audit job3518 has nine combined county executive/assembly documents. Its document outcomes explicitly refuse `native_report_date_or_scope_unavailable`; it has no native audit report bindings. The bounded official OAG listing check supplies neither a full publication day nor the missing single-auditee contract. These are correct refusals. Retrieval dates, upload directories, signatures and tabling dates cannot replace a publisher-labelled publication date. Audits remain report-only, without numeric finding announcements.

A separate executable producer→per-document commit→CLI finalization reproduction found a selection defect. When one job discovered two qualified fiscal editions for the same auditee, iteration order determined its series head and both editions remained dispatchable. An older baseline could then conflict with the newer edition.

The native writer now selects one chronology-consistent edition per auditee independently of discovery order. It retains the full immutable receipt inventory. The reader returns only the selected heads and verifies each head against its actual receipt scope. Same-release conflicting bodies and crossed chronology refuse. Reusing the same URL for an older body rolls back instead of replacing the chosen source binding. Distinct auditees remain independent. Existing cross-job conservative authority refusal and withdrawal behavior remain intact.

The permanent producer/CLI tests were observed **6 failed / 4 passed before the repair**, then **10 passed**. They execute actual retained PDF capture, authority, persistence, commit/finalization and dispatch with owned HTTP/finding-extractor ports. These PDFs and clocks are synthetic; they do not establish production acceptance of the nine combined volumes.

## KRA financial authority

The original dated FY2024/25 KRA annual article has styled paragraphs and labelled sections that the narrow collection-sentence binder did not recognize. The existing numeric parser already found the figures, but the financial authority binder supplied no matching cells. The two desired source-shaped acceptance tests failed against the old binder while 18 negative controls passed.

The additional grammar recognizes the reviewed annual sections, complete head claims, permitted explanatory paragraphs, bounded alignment CSS and visible inline emphasis. It binds the annual collection token only when it equals the numeric parser's existing result. Targets, VAT half-year amounts and adjustment vouchers never become the annual collection. The declared one-decimal financial transformation is preserved.

Unknown visible prose, section headings/lists, nested containers, CSS, scope qualifications or duplicate claims cannot inherit annual financial authority. Complete paragraph validation replaces a scope-word blacklist: unrecognized qualifications such as another fiscal year, a month, Q1 or H1 refuse even after a valid opening sentence. Whitespace and comments remain harmless. The new 49-case permanent file includes all five heads, committed financial refusals, and a source-shaped baseline→new-job unchanged→synthetic one-head correction→zero-duplicate replay. The synthetic correction creates one pending-review draft with no delivery targets/publications; it is not a claimed KRA revision.

The separately retained original article also passes the actual producer→PostgreSQL→qualification→native-reader baseline/reacquisition controls. That is genuine historical source acceptance with local transport/acquisition/job clocks. It is not current FY2025/26 production adoption. Current production KRA job3530 is catalogue-only, has no financial publication day, and remains ineligible for financial drafts.

## National budget financial acceptance

Production live job3517 retains the annual report and publisher date, but its ten numeric rows remain unpublishable with identity qualification refusals. Later fixture job3547 does not supersede the qualified live report contract. Investigation traced the financial hold to the existing default-off cached-parse path: an unsealed parse result cannot bind financial entity identity. No identity check or cached-result promotion was weakened.

An actual complete 15,609,728-byte annual PDF and its exact publisher page were retained from official CoB URLs. The existing fresh parser, HTTP client, receipt machinery, native writer and migrated PostgreSQL qualification pipeline accepted **ten rows / twenty financial cells**. Initial dispatch committed **ten silent baselines**. A distinct job reused retained PDF bytes with a fresh publisher capture and fresh parse, then returned **ten unchanged / zero drafts / zero refusals**. No source values were changed to create that result.

This test executed two complete fresh parses in 97.002 seconds. A stale candidate's 2GiB attempt was interrupted at its cap and receives no test credit. The accepted local execution used one CPU, a 4GiB memory limit and 256 PID limit; sampled peak was 3.557GiB. This does not certify operation within Render's existing 512MiB allocation or close the ingestion memory/cost gates. No hosted allocation was changed.

## Shared entry paths

Audit authority changes sit in `persist_native_report`, used by the actual audit document producer, and `native_report_observations`, shared by automatic dispatch, previews and explicit detection. National, pending-bills and revenue report writers use the same native writer but retain their prior non-audit selection behavior. Withdrawal continues through the unchanged invalidation path.

KRA cell authority sits in `bind_press_cells`, called by the native `_read_release` path, before `_apply_kra_live`, parsing and persistence. Automatic ingestion, rediscovery/reacquisition, replay and manual detection therefore share the same retained evidence and committed-reader checks. Neither the social layer nor a test-only alternate crawler supplies authority.

## Retained primary inputs and replay limits

| Input | SHA256 | Meaning |
| --- | --- | --- |
| [KRA original article](https://www.kra.go.ke/news-center/press-release/2235-kra-grows-revenue-by-6-8-despite-tough-economic-environment-4) | `ad35dcb5175af4dd26a8707dede239a879c8af0c885f325d3b6cf1cdbc47dce3` | 119603 bytes; labelled 10 July 2025; FY2024/25 |
| [CoB annual PDF](https://cob.go.ke/download/national-government-budget-implementation-review-report-fy-2025-2026/?wpdmdl=16454) | `f99ec2997f13400d2fc1fb340154c9b91640591c6d1351415fc075b259a7c4b1` | Complete EOF; FY2025/26 |
| [Exact CoB publisher page](https://cob.go.ke/download/national-government-budget-implementation-review-report-fy-2025-2026/) | `6f5d2afc27cbd98250453490e7e2ced6d7d17e663e4bf28d4d166538aafb2e9d` | 93880 bytes; publisher day 4 September 2026 |

Full newly acquired publisher articles/PDFs remain in the local evidence packet, outside the public repository. Permanent KRA tests reconstruct selected paragraphs from the existing retained-text fixture; they do not silently download inputs. The supplementary genuine-input scripts require those exact separately retained bytes and owned current-schema PostgreSQL. Hashes, source URLs, commands, manifests, results and independent reviews accompany this report; a passing source-shaped test must not be relabelled as a genuine source acquisition or production rollout.

## Remaining scope

Qualified national-budget production financial adoption still needs its own bounded source/operator rollout. Current KRA catalogue evidence remains report-only until a genuinely dated financial source is accepted. Combined OAG volumes still need an explicit defensible scope/date contract. Other unsupported domain contracts, #801 borrowing evidence and the separate launch gates remain open. Keep publishing, uploads, all workers, admin consumption and financial generation off.

## Final verification and operating state

Frozen candidate3 has 6037 files and manifest SHA256 `dbbe7eb21d4b35c90165ee11ca7ae1749cc71e4e48c95bee67368f46aeebd82a`. Final documentation/evidence additions do not change the reviewed runtime or tests.

- The root selection covers **481 unique cases per mode**: 455 passed in the main run and 26 historical capability cases initially skipped for a missing separate PostgreSQL fixture. Those exact 26 were then executed unchanged against their assigned owned offline database, all passing normally and with actual Python `-O`. No selected case remains unexecuted. Overlapping targeted runs are not added to this count.
- Independent Audit Spec review passed 87 distinct cases normally and with `-O`. Its exact eleven dependencies are unchanged in candidate3; the [carry record](native-source-acceptance-20261030/spec-carry.md) retains the original executions rather than relabelling them as reruns.
- Independent Standards review executed 79 candidate3 cases per mode, including all 49 permanent KRA cases, original HTML, financial default-off/catalogue controls and visible adjacent-scope attacks. Separate national readers pass in both modes. The real full-PDF producer acceptance is carried through unchanged dependencies, with its resource limits and local-clock scope retained above.

At 21:33:27 UTC the read-only production check found deployed `e1a0d6b`, all 30 inspected installed hashes matching, publishing false globally and for both actual accounts, media false, financial/native/studio/supervision flags unset, and no background worker/consumer. Five existing posts remain; delivery targets, publications, media assets, uploads and attempts are all zero. The exact 14 repository-variable baseline is unchanged and the financial variable is absent. No paid review/model, hosted validation run, new service, plan or allocation was added. The PR stays draft to avoid an automatic paid bot review; automatic frontend builds are held during the push and restored afterward.

[Validation receipt](native-source-acceptance-20261030/validation-receipt.json), [reviewed source hashes](native-source-acceptance-20261030/reviewed-source-sha256.json), [Audit review](native-source-acceptance-20261030/spec-review.md), [Standards review](native-source-acceptance-20261030/standards-review.md) and source-input identities are committed beside this report. The full local packet retains earlier failed harness attempts and observed REDs without crediting setup failures as product refusals.
