# Batch 10 delivery and investigation review — 2026-10-10

All five author sessions published their commits. The initial three PRs represented three implemented repairs. The other two sessions completed and pushed investigations, but did not identify a supported product repair. This documentation PR publishes both investigation handoffs for review. It closes neither #494 nor #601 and changes no application, dependency manifest/lock, workflow or original browser assertion.

The original author statements that no repair PR was appropriate remain historical delivery facts. The coordinator is now making their completed evidence and recommendations reviewable at the user's request. The missing dependency author's former local checkout is absent; its pushed objects and evidence were recovered into an owned review checkout. No unpushed product fix was found.

| Session | Published author commit | Review disposition |
| --- | --- | --- |
| #589 startup readiness | `7395a7acebaa38b3b641249ac31fddcc1aab249e` | PR #604; combine with #595 because both modify `backend/main.py` and its behavior. |
| #595 IMF actual-year behavior | `6ec8870d08fd800363530dc6f26d2f3d429bcba0` | Preserve both author commits in #604; #605 becomes superseded after verified publication. |
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

1. Complete review of #604 and #606, including #608's verified receipt fix. Neither acceptance nor issue closure is inferred from an open draft PR.
2. #603: make durable retained non-budget writer claims take precedence over bootstrap's one-hour scheduling boundary. Prove actual interrupted-writer exclusion and safe normal successors; #589 readiness does not resolve this inherited defect.
3. #602: implement bounded real OpenData and CRA native entrypoints before wiring their admin mappings. CRA is Commission on Revenue Allocation; KRA revenue data cannot substitute. #554 stays partially open for these prerequisites and deployed operator acceptance.
4. Coordinate #607 and #601 under one navigation owner, retaining their distinct failure phases and original browser assertions. Obtain a causal red/green reproduction for each actual symptom.
5. #494: choose a scoped compatible residual-root/style migration strategy with explicit template ownership, valid fresh package graphs and real platform/native/model/build/page acceptance.

Other prior gates remain routed to #583 (production writer fencing/reconciliation/migrations/activation), #545 (entire-admin completion and intended-host acceptance), #525 (telemetry/exporter custody), #488 (Meta authorization), #490 (private storage/maintenance), #481/#476 (hosting/operating evidence), and #599 (old zero-job Actions record). No duplicate unresolved issues are needed for repaired historical fixture/verifier defects.

## Reusable lessons

Retain causal failures separately from detector-only controls and setup failures. Record executable architecture rather than infer it from image labels. Validate receipt primitives with exact types and bind the expected recorder/entry, complete execution metadata and actual JUnit outcomes under normal and optimized execution. Treat final archives/manifests as consumed fixture inputs and rerun after publication. Probe actual cold native imports and preserve narrowly justified historical failure compatibility. For package remediation, distinguish native imports, CPU inference, generated embeddings and real browser/CSS behavior; keep unit auth inputs separate from build fixtures. Lane-local lesson files retain the detailed evidence.
