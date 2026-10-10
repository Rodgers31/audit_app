# Batch 10 delivery and investigation review — 2026-10-10

All five author sessions published their commits. The initial three PRs represented three implemented repairs. The other two sessions completed and pushed investigations, but did not identify a supported product repair. This documentation PR publishes both investigation handoffs for review. It closes neither #494 nor #601 and changes no application, dependency manifest/lock, workflow or original browser assertion.

The original author statements that no repair PR was appropriate remain historical delivery facts. The coordinator is now making their completed evidence and recommendations reviewable at the user's request. The missing dependency author's former local checkout is absent; its pushed objects and evidence were recovered into an owned review checkout. No unpushed product fix was found.

| Session | Published author commit | Review disposition |
| --- | --- | --- |
| #589 startup readiness | `7395a7acebaa38b3b641249ac31fddcc1aab249e` | Consolidated in PR #604 with #595 because both modify `backend/main.py` and its behavior. |
| #595 IMF actual-year behavior | `6ec8870d08fd800363530dc6f26d2f3d429bcba0` | Both author commits preserved in #604; #605 closed as superseded after verified publication, without merging. |
| #554 bounded ETL mappings | `86aa4c3a7a29383ed256273bd0097cfc81b3336d` | Keep PR #606 separate: worker/dispatch/native exclusion/models/migration. Activation remains off. |
| #494 dependencies | `b9b03339f93fd67da6566ea58fe93c2e8ea9961e` | This documentation PR; compatibility/remediation acceptance remains pending. |
| #601 county scroll | `44e2b0a2fb0bc9fcd7ae2153bd9f6101760fac47` | This documentation PR; causal reproduction and repair remain pending. |

Both investigation commits are ancestors of the documentation consolidation. The initial consolidation is `2f8568d9211a8ca97eda835b67f93ff8051f0939`, tree `b6a038f6bfba19c06ce53e019296575bedf983f9`, based on accepted `f6c31e271297eece52f34102dc40a1e2ed7069a8`. Its original 157 added paths are scoped documentation/evidence; this note is a subsequent coordinator addition.

## What the investigations established

Dependency handoff: [BATCH_10_DEPENDENCIES_HANDOFF.md](BATCH_10_DEPENDENCIES_HANDOFF.md). Production audits recorded zero findings; full macOS/Linux propagation counts were 26/27 from two residual advisory roots. Tested upgrades did not eliminate both roots with accepted compatibility. Configuration-only Tailwind migration failed the real CSS compiler; official migration compiled but required changes to 107 templates, overlapping navigation ownership. Optional WASM graph validation also failed despite the required versions being published. These are boundaries of the tested paths, not proof that future supported remediation is impossible. No risk exception or dependency change is delivered here.

Scroll handoff: [BATCH_10_SCROLL_HANDOFF.md](BATCH_10_SCROLL_HANDOFF.md). Historical native-auto restoration stopped at Y100; later green probes and a forced-manual Y0 detector failure did not establish its cause. The actual 100-repeat replay had 99 passes and one pagination URL mismatch before scrolling, separately tracked as #607. The full original browser inventory was 323 cases: 312 passed and 11 existing fixmes. Early runs used Node24; the corrected final replay used Node22 Linux x64 under emulation. Runtime corrections and original records are retained. No browser assertions or navigation behavior are changed here.

## Fresh coordinator verification

Independent investigation review executed the final published author corpus: dependency portable verification covered 68 historical records/482 members, 14 bundle tests and eight recorder tests passed under optimized Python; scroll portable verification covered the original 323-case inventory and 32 archive tests passed. Independent hashes verified all three dependency archives (1,463 members), final author receipts/generators/logs, six final reviewer reports and the corrected retained x64 executable identity. This verifies the archived investigations; it is not a new native/browser baseline or deployed acceptance run.

Independent product review on initial combined startup/IMF source `6fa01eb2ab938fbdf2e198080928796f65f558f9` passed 176 behavior controls, including real owned PostgreSQL writer/startup cases and all three IMF callers. Standards review found no product defect, but reproduced a malformed-current-receipt acceptance defect in the IMF verifier and filed #608. That repair and its final source replay belong to #604; the earlier scoped pass does not certify later verifier bytes.

The ETL review independently replayed all 152 new mapping/process/migration/receipt/package controls twice: Python3.13.9/SQLAlchemy2.0.54 and supported minimum Python3.12.14/SQLAlchemy2.0.23. Both ran with zero skips, failures or errors. Exact owned PostgreSQL resources were cleaned up; tracked inputs remained unchanged. Broader final product-review results belong to the corresponding PR briefs.

GitHub Actions remain disabled. Historical hosted acceptance is bound to its original commit and is not current acceptance for these candidates. Production/database/provider operations and dispatch activation are separate gates.

## Issue audit and next work

The initial all-state census contained 607 issue-or-PR rows across seven pages: 299 actual issues (16 open), excluding 308 PR entries. Five author finals, handoffs, local lessons and relevant prior Batch9 acceptance were reviewed for concrete missed follow-ups. Existing #602, #603 and #607 already cover the discovered blockers. The coordinator subsequently opened #608 for the newly reproduced IMF verifier defect; issue totals above remain timestamped historical counts.

1. Complete human review of #604, #606 and this documentation PR #609, including the verified #608/#610 receipt fixes. Neither merge nor issue closure is inferred from an open draft PR.
2. #603: make durable retained non-budget writer claims take precedence over bootstrap's one-hour scheduling boundary. Prove actual interrupted-writer exclusion and safe normal successors; #589 readiness does not resolve this inherited defect.
3. #602: implement bounded real OpenData and CRA native entrypoints before wiring their admin mappings. CRA is Commission on Revenue Allocation; KRA revenue data cannot substitute. #554 stays partially open for these prerequisites and deployed operator acceptance.
4. Coordinate #607 and #601 under one navigation owner, retaining their distinct failure phases and original browser assertions. Obtain a causal red/green reproduction for each actual symptom.
5. #494: choose a scoped compatible residual-root/style migration strategy with explicit template ownership, valid fresh package graphs and real platform/native/model/build/page acceptance.
6. #611: implement durable epoch-aware audit pagination storage. Preserve the existing fail-closed guard until real PostgreSQL late-commit/wrap/freeze/rewrite/restore and role/browser acceptance establishes supported replacement semantics. This is a previously documented follow-up whose dedicated GitHub issue was missing; it is now tracked under #545.

Other prior gates remain routed to #583 (production writer fencing/reconciliation/migrations/activation), #545 (entire-admin completion and intended-host acceptance), #525 (telemetry/exporter custody), #488 (Meta authorization), #490 (private storage/maintenance), #481/#476 (hosting/operating evidence), and #599 (old zero-job Actions record). No duplicate unresolved issues are needed for repaired historical fixture/verifier defects.

## Final coordinator review and publication

The five author deliveries are covered by three draft review PRs:
[startup/IMF #604](https://github.com/Rodgers31/audit_app/pull/604),
[bounded ETL #606](https://github.com/Rodgers31/audit_app/pull/606), and
[investigations #609](https://github.com/Rodgers31/audit_app/pull/609).
The former [IMF #605](https://github.com/Rodgers31/audit_app/pull/605) is closed as
superseded, not merged. Its branch and original delivery are preserved. The two
investigation sessions were not missing unpushed product changes: their published
evidence established limitations and next work, without a supported repair.

Final #604 source is `ad4a9f76f944514c414465643a72f2cee0b1bc19`, tree
`e82775f2bf7f900027797d3f7c20da468edff052`. Both original author heads are
ancestors. The final offline financial/readiness-receipt cohort passed 864 tests
on each supported runtime, with six unchanged PostgreSQL-prerequisite skips each;
the real 17 startup controls passed separately on both runtimes at `fd681f5`,
whose main/bootstrap product bytes are identical to the final head. Independent
final adversarial review passed 121 controls and rejected 222 malformed CLI
receipts plus 34 direct-call variants. #608 is repaired but stays open for review
and merge. Original historical receipt/generator identities remain unchanged.

Final #606 evidence repair is `bebfba0813ccaf39327d5d6f37be10769caee699`, tree
`b726ed79fd3e5a3580ae769f4749b2b9cb798d7b`. All six ETL product files are
byte-identical to the reviewed original author head. #610 records the actual
historical-fixture integration failure and malformed JUnit/provenance acceptance.
The repaired final packet passed 100 controls on each supported runtime, zero
skips/failures/errors. Its deterministic archive preserves all 1,160 original
declared source files; 1,158 were measured in the original executions and two
were later publication-only files. Active validation explicitly means historical
packet integrity and reports `current_checkout_acceptance=false`; it does not
relabel old executions as fresh acceptance. Original and intermediate
publications, real red controls and the recorder-only setup error are retained.

Fresh combined-candidate acceptance used actual merged source
`6a5dd1886a0ef343398ac6efe80e67cba55fc9b0`, tree
`f97f602a56c171527056340cf68ff9882a0c46fc`, containing both final backend and
mapping commits. The earlier integration receipt retains its two failures and
ten passes. The repaired integration passed 284 ETL/startup/PG/migration/receipt
controls on each of Python3.13.9/SQLAlchemy2.0.54 and
Python3.12.14/SQLAlchemy2.0.23, with zero skips/errors/failures. Separate actual
offline IMF runs passed 121 controls on each runtime, and their final current
receipts verified under normal and optimized Python against the unchanged
historical corpus. All 3,423 tracked integration inputs remained stable. Exact
owned ETL container/volume absence, readiness cleanup and free loopback ports
55520/55522 were checked. Overlapping cohort counts are not added together.

Final command/raw/JUnit/source/generator/runtime/readback records and independent
Standards/Spec reports are external under:

`/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_10_REVIEW/`

Newly confirmed findings are tracked by [#608](https://github.com/Rodgers31/audit_app/issues/608),
[#610](https://github.com/Rodgers31/audit_app/issues/610) and
[#611](https://github.com/Rodgers31/audit_app/issues/611). The last is the missed
prior audit pagination capability: actual inert helper/route controls confirmed
the current guard refuses nonzero server epochs before row reads, including old
bookmarks. No production epoch was queried or production outage asserted. The
separate inherited blockers #602/#603/#607 were already tracked and were not
duplicated. #494/#601 remain unresolved. No PR was merged or issue closed in this
review; #605's superseding closure is the only PR closure.

The primary checkout's 20 pre-existing tracked modifications were compared with
their launch hashes and remained byte-identical. This does not claim that its
entire untracked/status inventory stayed identical. Review work used isolated
managed checkouts and append-only external evidence. Actions remain disabled;
no fresh hosted/deployed acceptance, production database/provider operation or
dispatch activation is claimed.

The reusable receipt-provenance skill was updated narrowly for the #608/#610
lessons: exact primitive types, original producer versus later publication,
unique actual JUnit identities, complete consumed execution metadata and a
retained source corpus for historical integrity. The skill validator passed;
prior bytes, final hash and readback are preserved in the coordinator evidence.

## Reusable lessons

Retain causal failures separately from detector-only controls and setup failures. Record executable architecture rather than infer it from image labels. Validate receipt primitives with exact types and bind the expected recorder/entry, complete execution metadata and actual JUnit outcomes under normal and optimized execution. Treat final archives/manifests as consumed fixture inputs and rerun after publication. Probe actual cold native imports and preserve narrowly justified historical failure compatibility. For package remediation, distinguish native imports, CPU inference, generated embeddings and real browser/CSS behavior; keep unit auth inputs separate from build fixtures. Lane-local lesson files retain the detailed evidence.
