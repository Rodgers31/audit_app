# Batch 7 coordinator acceptance — 2026-10-09

All four author chats completed normally and stopped at draft PRs. The coordinator reviewed their full handoffs, originating issues, frozen spec, complete Copilot review bodies and inline threads, then repaired findings and verified the combined implementation. This brief records local code acceptance; deployment and ETL activation have separate gates.

| Author session | PR | Accepted work | Remaining work |
| --- | --- | --- | --- |
| Batch 7 — legacy Supabase helper repair | [#573](https://github.com/Rodgers31/audit_app/pull/573) | Header merging, auth override refusal and exact role acknowledgment validation; active Users and authentication compatibility preserved | #570 profile-read boundary and #571 diagnostic bounds remain open |
| Batch 7 — dependency advisory remediation | [#574](https://github.com/Rodgers31/audit_app/pull/574) | Production classification, actual Sharp retention, strict browser resource boundary and isolated runtime regressions | #494 retains 38 full-tree advisories; production audit is zero |
| Batch 7 — ETL dedicated worker backend | [#575](https://github.com/Rodgers31/audit_app/pull/575) | Atomic durable command/audit acceptance, idempotency, opt-in dedicated worker, leases/fencing and receipts; OAG → audits mapping | #572 independent native-CLI exclusion blocks activation; #554 remains open for that gate and additional mappings |
| Batch 7 — ETL controls and command receipts | [#576](https://github.com/Rodgers31/audit_app/pull/576) | Confirmed worker controls, bounded history/detail, strict responses and actor/lifetime safety; actual combined browser acceptance | Calendar remains planning evidence; receipts do not certify financial freshness |

The author's clean worktrees are respectively `batch7-provider-helper`, `batch7-dependencies`, `batch7-etl-worker` and `batch7-etl-ui` beneath `/Users/roger/.codex/worktrees/`, on their `codex/batch7-*` branches. Bulk logs remain in the owned external review directory. Author chats are idle; the coordinator performed the post-review repairs.

## Findings and repairs

Four inline findings and review-body concerns were evaluated individually:

- Dependency URL finding was understated: the old actual route callback falsely accepted twelve package/version/protocol/port/query/credential/path variations. Complete enumerated HTTPS URLs and the installed ONNX Web version now define the boundary; fifteen callback controls and additional independent hostile inputs pass. Real Chromium still performs WASM inference and fallback ranking without unexpected transport.
- The dependency review body correctly identified missing test-command/CI wiring. `npm run test:dependency-boundaries` now executes both browser transport and installed-runtime/isolation controls. It creates an owned production-only installation, preserves the build installation, and is a required step in the three existing frontend workflow definitions. Actions remains disabled; definition wiring does not mean hosted execution.
- Disabled keyed dispatch was a valid defect. The feature guard now applies before any database work to every request. Actual PostgreSQL and unavailable-storage controls show no command/audit/job/lease mutation while disabled; enabled same-key recovery remains available.
- SQLite compatibility was version-dependent: the old metadata passed on SQLAlchemy 2.0.46 but failed at the declared supported minimum 2.0.23. Seven new columns use dialect-adapting `Uuid`; all 32 shared SQLite tables and UUID round-trips pass on both versions, while PostgreSQL retains native UUID behavior.
- The UI refusal finding was half-right. A definite initial 401/403 clears its key before lifetime invalidation; a recovery refusal retains the prior ambiguous key because it cannot prove the original command was absent. The original initial-refusal tests and naive overbroad-clear variant both have retained red receipts; the correct twelve-case rendered matrix and twenty-eight synthetic-fixture browser journeys pass.
- The worker review body's session concern did not reproduce in actual native adapter/CLI real/dry-run controls under UTC and Africa/Nairobi. No unsupported additional session fix is claimed.
- The helper review body's broad lint concern remains accurately tracked as #569. Scoped changed-code lint passes; an unchanged producer closure triggers the broad critical lint diagnostic. This is a tooling-gate finding, not a demonstrated runtime PDF defect.

Coordinator review discovered [#577](https://github.com/Rodgers31/audit_app/issues/577) after checking all open and closed issues. The old destructive runtime test followed a copied installation link: its five child controls passed while deleting eighteen disposable source decoder files. An explicit owned deep clone now resolves links, preserves executable modes and rejects cycles/special files/occupied destinations. The retained outer regression verifies source bytes and actual Sharp decoding survive. Fresh standard-command replays pass twenty-four controls on macOS and pinned emulated Linux amd64. This specific test defect is repaired; #494 remains open.

Actual visual review also found a stale blanket calendar notice claiming no worker or accepted job existed even while dedicated dispatch was ready. Backend health wording, UI notice and disabled tooltips now describe the calendar's own limits. Actual ready and post-acceptance browser checks verify that dedicated receipts and calendar evidence agree. This repair belongs to existing #554/#568 rather than a duplicate ticket.

## Combined acceptance

Exact base: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`. Final product freeze: local integration commit `cd9704d5de5af9833d38c408b60baedc8dfe7671`; tree `ae444fc4d3608461b6196e378d753510f87aa37c`. [Source identity](batch7-coordinator-evidence/source-identity.json) freezes thirty-seven product/core files, all four retained fixture files, inert public configuration and Next build `c9cQFH6VWaek0J8v8GJsT`. Receipt hashes are in [the compact manifest](batch7-coordinator-evidence/receipts.json). Subsequent delivery changes retain these exact bytes and add evidence only.

| Executed check | Outcome |
| --- | --- |
| Final combined frontend coverage | 147 suites; 2,077 passed, one existing optional financial skip |
| Selected combined admin backend | 438 passed |
| Dedicated worker/process/PostgreSQL/migration repair replay | 302 passed, one retained strict expected failure for #572 |
| Supported-minimum/current SQLite metadata and UUID controls | Pass on SQLAlchemy 2.0.23 and 2.0.46 |
| Final build, full frontend lint and standalone TypeScript | Exit 0 |
| Fresh dependency boundary command | 15 URL + 9 runtime/isolation controls pass on macOS and emulated Linux amd64 |
| Actual combined Chromium UI/API/PostgreSQL/native-worker matrix | 11 passed; no unexpected transport |
| Desktop/mobile receipt and ready screenshots | Visually inspected; calendar copy scoped; mobile keyboard/viewport controls pass |

The actual eleven journeys cover default-off rejection with no writes, confirmed real native completion and matching actor audit, native dry-run rollback, lost-acknowledgment same-key recovery after lease expiry, stale generation rejection, actual history/filter/pagination/detail/back links, failure sanitization, interruption after an inert committed effect with durable domain exclusion retained, initial 401 and 403 renewal, and mobile keyboard confirmation/completion. JWT decoding and profile lookup, real dispatch routes, actual isolated PostgreSQL migration/persistence and the separate native CLI are used. Identity/provider endpoints and the registered domain handler are inert; financial source fetching/publication and product lifespan are outside this fixture.

The first browser run had nine passes and two diagnosed harness failures: a duplicate receipt locator and treating temporarily unavailable generation `null` as a restarted worker. Both raw failures and corrected generator/source identities are retained. Earlier missing configuration/parent-fixture setup failures are also retained separately; no product fix or extra issue is claimed for them.

## Issue accounting and next priorities

Acceptance completes #567, #568 and the newly found #577. #554, #494 and parent #545 remain open. Existing deduplicated follow-ups #569–#572 are retained. Operational #525/#488/#490 and the social/hosting roadmap #476/#481 retain their deployed telemetry, authorization/key custody, private storage, upstream and egress gates.

The next four independent lanes are: #572 native/worker shared exclusion first; #570/#571 together in the legacy helper; #569 producer lint/closure verification; and #494 compatible residual advisory remediation. Additional ETL mappings should follow the exclusion fix with their own domain/publication acceptance. Dispatch stays default-off until the activation gate is independently accepted.

GitHub Actions is disabled, required hosted security/quality checks are unexecuted, and local acceptance does not replace those gates. The previously authorized owner merge bypass is available if the normal exact-head merge is rejected. No fake checks, repository-rule changes or extra paid/bot review are part of delivery. Production activation, live provider/user/email/storage actions, production migrations and financial publication were not performed. The dirty primary checkout remains read-only. The retained [cleanup receipt](batch7-coordinator-evidence/cleanup.json) verifies owned API/Next termination, all ten worker groups absent, the isolated PostgreSQL container removed, and ports 8163/3163/55483 closed. The separate dependency preview is stopped and its disposable Linux replay container was removed. Final merged-tree identity is recorded in the coordinator delivery packet.
