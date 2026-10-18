# OpenData workbook implementation handoff (#621/#602)

The official KNBS workbook route is implemented in draft PR #743 on base `78c305abe3cfb5b3d3f0ed800275f2f7e7bfb303`, branch `codex/b17-opendata`. See [the source and persistence contract](B17_OPENDATA_WORKBOOK_CONTRACT.md). It retains the actual KNBS publisher, all source cells/footnotes, missing markers, raw numeric strings, provisional/revised/unspecified labels, edition differences and published reconciliation discrepancies. It writes a source-bound document/extraction only; public financial qualification remains held.

`SEED_OPENDATA_INGESTION_ENABLED` defaults false. Migration `e621b17a0001` follows `a705b15a0001` and requires a stopped worker. No production migration, deployment, grant change, provider operation, feature activation, hosted run or paid bot review was performed. No application dependency or service was added. Existing CRA/native ownership code remains unchanged; legacy reference scope holds fifteen domain keys on one backend and releases distinct receipts atomically, within pool2/nooverflow.

## Substantive #742 review

The stale main.py context binding is corrected in this draft after separate executable Standards and Spec reviews. [The complete review](B17_MAIN_FINANCIAL_CONTEXT_REVIEW.md) identifies exact previous candidate `44a6c8b31e734cdc6d3a4eafbdfff4aa195fbdc6`, rather than the earlier baseline named in the old inventory. Complete comparison covers184 definitions:183 unchanged, only `_app_lifespan` changed, plus11 module-level social configuration/import statements. All four raw financial sites and their financial callers/helpers remain unchanged.

Only main's AST pin and four review-pointer pairs change. Main source SHA256 remains `71a3c6e91a873e74e1b1331f389be99fbb7d2da4e6579882bb4689e55bcf35c1`; reviewed AST is `b9a5f0cdcf9bed49b53fd8a94389b6d2b95af1ec1fe7e4630d165ff4f6cf9b0a`. Detector/traversal/normalization, raw signatures, reasons, dispositions, tracking, other inventory entries, hostile controls and financial disclosures are preserved. The old pin still refuses. This review is not legal recertification or qualification of the wider financial backlog/editorial social fact text.

Independent current-runtime controls passed17 Standards and36 Spec cases per normal/optimized mode, with actual financial/lifecycle execution and hostile context/suppression mutations. After amendment, actual existing context controls passed13 per mode and Standards17 per mode. Both exact independent helpers then passed53 combined cases per mode on cached Python3.12.15/SQLAlchemy2.0.23 with network disabled. Counts overlap.

## Acceptance rerun on the amended source

Every successful cohort below has stable source inventories. Final source differs only by this documentation-only handoff amendment, separately reviewed. Owned PostgreSQL17.11 resources are cleaned up. Current runtime is Python3.13.9/SQLAlchemy2.0.46; minimum is cached Python3.12.15/SQLAlchemy2.0.23, with the optional C-extension parity qualification retained.

| Cohort | Actual result | Qualification |
| --- | --- | --- |
| Current workbook, CRA, migration, bootstrap, registry/head and context selection | 201 passed | Former main.py case INCLUDED; no deselection, failures, errors or skips |
| Current optimized workbook/head/registry/context and legacy backend death | 137 passed | Former main.py case INCLUDED; no failures, errors or skips |
| Current full financial-source guard, context, health/disclosure and fiscal publication/ratio/scoping | 1042 passed | No failures, errors or skips |
| Minimum workbook/native/dispatch/storage/migration/legacy/bootstrap plus full financial-source guard/context | 1064 normal +1064 optimized passed | No failures, errors or skips |
| Corrected current legacy loader/session/scheduler, CRA/OpenData contention and pool limits | 91 passed | Cached declared schedule1.2.0 in a separate no-pip task runtime; primary environments unchanged |
| Six mappings, normal retained-owner/rollback/correlation/deferred release/backend loss | 169 passed | Explicit owned template; financial handlers forbidden |
| Six mappings, initial optimized run | 168 passed, 1 failed | Early maintenance session census refused before the intended readback control |
| Six mappings, diagnostic optimized rerun | 169 passed | Original refusal did not recur; this does not establish a causal repair |

The original optimized failure remains an explicit acceptance qualification: another database session/background backend was observed by the unchanged maintenance guard between plan and apply, but its identity was not captured. The diagnostic rerun re-raised original guard decisions, produced no refusal observations and passed; its plugin has only post-run hash readback when no refusal occurs. Do not infer an autovacuum cause, a fixed race or unconditional whole-suite acceptance. #621/#602 remain open for parent integration and this remaining qualification.

Setup/recorder attempts are retained separately: an initial source-review invocation omitted PYTHONPATH; unstaged lint refused before running; one cohort's heavy-slot wait expired before launching pytest; and an initial legacy run lacked schedule in child processes because the fixture replaces PYTHONPATH (90 passed/1 failed, with negative scheduler paths unqualified). The corrected isolated runtime executes the actual scheduler, rather than weakening tests or adding a dependency to the application. Cached selected Flake8 E9/F63/F7/F82 across the complete PR Python diff and whitespace checks pass.

The earlier workbook evidence remains immutable, including original dry-run provenance and pool-exhaustion red/green proofs, original parser/storage/ownership independent reviews and earlier setup failures. Historical counts must not be added to the overlapping rerun totals.

## Remaining boundary

The #742 review requirement is satisfied on the tested draft branch; main has not received the reviewed binding until integration. Issues #621/#602/#742 remain open. No hosted verification or merge is authorized here. Parent integration acceptance and the unresolved session-census qualification remain distinct from this substantive context review. Production activation stays separately gated by #583/#554.

The new workbook route is one hash-pinned edition, not automatic future-report discovery. A changed edition refuses pending review. Only Table5.13 is retained as source/extraction; no new workbook figure is displayed in the UI. Existing `knbs → population` retains its fixed2019 census contract; national macro sources keep their World Bank/CBK attribution. No KNBS enhancement was implemented.

Append-only evidence: `FULL_PLAN_COMPLETION_B17/opendata/financial-context-review-742-20261018` contains whole-module derivation, exact commands/source/helper/runtime hashes, per-case XML, independent reviews, retained failures, Chrome source/UI/settings captures and `KNBS_COVERAGE.md`. The separate `workbook-implementation-20261018` and earlier research/prerequisite packets are historical and unchanged. Finalization binds committed/published draft head/tree, complete PR feedback census, prior packet verification and owned resource/port cleanup. The dirty primary checkout was not edited or committed.
