# CoB producer qualification follow-up (local candidate)

This managed checkout is `/Users/roger/.codex/worktrees/b15-cob-qualification/audit_app`,
branch `codex/b15-cob-qualification`, based on ETL706 delivery
`dda109ca70859a8c7686e01411262f12d8e0e67c`. It is a follow-up to the original
ETL handoff preserved below, not a claim that this candidate was already in706.
No push, PR, merge, production configuration or activation was performed here.

The selected CoB actual-spending producer now captures a genuine explicitly
labelled full publisher date from bounded PDF pages, preserves its exact retained
byte/date/cell proof, and can qualify **new** records only under the separate
strict default-off `SEED_COB_VERIFIED_QUALIFICATION_ENABLED` operator switch.
Existing withheld rows/manual holds never promote. Unchanged existingTrue rows
stayTrue with the switch off; changed values/source identity/artifacts instead
withhold with an explicit reason. Exact requested-ingestion qualification keeps
all historical provenance and permits legitimate repeated/new source runs.
Prospective stored publisher-date evidence is rechecked against its own receipt.
See `docs/social-publishing/COB_GENERATION_QUALIFICATION.md` for scope and limitations.

Combined-candidate integration explicitly depends on generation704 head
`2f3b36e2749a48dbe7d93f001081ddc756a61412`. The PostgreSQL tests load that
peer's social package and complete migration chain without modifying peer files.
They use actual small valid PDFs, pdfplumber's real CoB parser, retained simulated
HTTP response bytes, the actual writer and committed readers, and the actual704
hook/semantic-event/pending-review service. These simulated acquisitions are not
real publisher or production acceptance. No generation code is copied into this
branch; the coordinator must combine704+706+this increment before release.

Evidence root:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B15/cob-producer-evidence`.
`bound-normal-f3eeae3cee6441c1911e3ab5e17dbda7/receipt.json` and
`bound-optimized-e181f851b1e44aa4b6b2708b008d48aa/receipt.json` bind complete
own+704 tracked/untracked backend source and fixture inventories before/after
execution, safe child environment/argv, raw output/JUnit and45 unique passes with
zero skipped/error/failure cases in each mode. These are the same45 cases, not90
unique tests. Runtime is Python3.14 with the existing read-only borrowed cached
dependency runtime and owned PostgreSQL17; Python3.12/full minimum parity is not
claimed. Fixture `b15-cobq-UUID` uses cached image/no pull, tmpfs storage and
loopback55424, and is removed and port-rebound after each module. Recorder confirms
no retained fixture container/process group.

The exact accepted-writer Git blob overlay was seen red: real PDF/parser/writer
rows stayed unpublished, so the integration could not baseline. The exact real
two-ingestion path was seen red on the old reader's all-history qualification,
then passed after the requested-ingestion projection. Root review's supported
null source metadata regression was seen red at the new snapshot comprehension,
then fixed by reusing `_source_metadata_for_update`. Earlier harness mistakes
and incomplete diagnostic cohorts remain labelled in `HISTORICAL_RUNS.json`.
Independent Standards found the inherited Nairobi/Nairobi City County binder
disagreement: the actual normal canonical-name producer was seen red, then the
one established alias was aligned with the shared figure qualifier. A different
county remains refused. Root's independent pre-alias Spec replay passed13
PostgreSQL cases. Post-alias independent Standards passed the same18 external
SQLite controls normally and optimized. Their scopes remain separate from the
final45-case bound pair. Review reports and local commit identity are recorded
in the external delivery report.

No local activation or real source request occurred. Publishing/uploads remain
off. Unsupported/month-only/date-less reports stay unavailable; no dates are
inferred and no other source/measure adapter is invented. This fixes selected
source coding, not the remaining native analytics/policy/provider/live gates.

# Original B15 ETL delivery — scoped implementation, not full original-plan closure

Draft PR: https://github.com/Rodgers31/audit_app/pull/706. Checkout `/Users/roger/.codex/worktrees/b15-etl/audit_app`; branch `codex/b15-etl`. Accepted base `06896185005d822c4b29888138b984510dd1fdbd`; exact implementation head `8680685af63bfa8667445409c39726b869bc2d2f`. The final documentation-only delivery head is recorded after commit in the external `DELIVERY_FINAL_V1.json` and shared `lane/etl-status.md` (a document cannot embed its own Git commit hash).

## Implemented

- Treasury native reconciliation now raises a bounded failure before its writer if the trust guard cannot complete. CLI rollback, FAILED job, command failure, and normal ownership release are exercised through the actual API/dispatch/adapter/native CLI/parser/writer chain. This protects both scheduled/native and dedicated-dispatch callers of the registered fiscal handler; the shared `check_fiscal_summary` implementation and other request-side alert consumers are unchanged. Clean rows still pass; individually quarantined rows remain excluded.
- `seeding/source_observations.py` exposes `read_county_budget_observation(factory, record_id=..., ingestion_id=...)`. It opens a fresh PostgreSQL REPEATABLE READ/READ ONLY snapshot, uses the shared `qualify_rows`, binds exact record/job/document/receipt/actual-spending evidence, preserves exact decimal zero and refuses unpublishable, fixture, quarantined, stale-session, wrong-URL, malformed or future evidence. The v1 output matches generation PR704's SourceObservation/FactEvidence contract. Source key is `budget_lines:{id}:actual_spent`; evidence version and ingestion identifier are the durable ingestion ID. Generation owns atomic semantic event UUID/version/dedup, including A→B→A; this producer creates no event or audit.
- `read_county_budget_record_ids` selects exact persisted integer ingestion lineage via JSONB containment, sorted IDs and LIMIT1001. It refuses overflow beyond1000 instead of truncating. Empty measured lineage for a validated completed live job is reported distinctly; no guessed/latest-job correlation or `items_updated` heuristic is used.
- Existing CLI now optionally invokes `social.generation.integration.maybe_generate_committed` **after** financial transaction/session closure. Canonical `SOCIAL_GENERATION_HOOK_ENABLED` is exact `true` only; absent/default `false` avoids the helper/social import. Only successful live non-dry county-budget runs enter the optional bridge. No scheduler/worker/grant was introduced.
- A30s existing POSIX main-thread domain alarm bounds post-commit generation; new reader/telemetry SQL caps are5s statement/2s lock, preserving stricter inherited limits. The peer hook adds cooperative deadline/transaction limits. POSIX alarms cannot promise immediate interruption of a C extension that never yields, and the direct peer hook has cooperative rather than universal hard bounds.
- Committed financial ingestion and generation outcomes stay separate. Typed partial counts remain intact; timeouts, invalid results or exceptions after invocation preserve `execution_unverified:true` with null counters. No automatic retry occurs. Separate job metadata is bounded, and authenticated API projection/frontend parsing expose safe state/counts in the existing ingestion Detail Metadata panel without raw reasons, arbitrary strings or provider diagnostics. Telemetry persistence failures log loudly; they do not relabel the financial commit as rolled back.

## Validation and preserved failures

Evidence directory: `/Users/roger/.codex/visualizations/2026/10/16/01a14634-d1bb-7401-a153-75212b85d7fe/etl-evidence`.

- Treasury accepted-code regression:4 failed/1 passed (`treasury-red-v2.log/xml`); the first SQLite-in-memory harness import failure is retained separately and is not the observed defect. The four direct handler cases reproduce writer entry on broken reconciliation in normal/dry modes. Native fixed-chain tests then pass.
- Independent Spec/Standards reviews found and reproduced unpublishable promotion, same-host wrong document citation, future chronology, active-writer rollback, stale cached-session reuse, completed-with-refused verdicts, and falsely known zero progress after late failures. Retained author regression runs include `review-regressions-red-v1`7 failed/29 passed, `reader-sessions-red-v1`2 failed, `completed-refusal-red-v1`1 failed, and `late-uncertainty-red-v1`2 failed/6 passed. Review generators/source/output bindings are preserved unchanged through v1–v4. Setup/port/fixture chronology failures remain labeled as failures, never passing controls.
- The accepted-CLI in-memory overlay (exact BASE Git blob, not a claim of a full baseline checkout) produces3 failures for absent callback wiring and2 unchanged disabled/dry controls; retained in `spec-review-v3/old-cli-overlay*`.
- Final author selection239 passed/0 skipped:88 changed plus151 inherited cases, Python3.13.9. Includes actual native CoB parser/writer→post-commit callback, failed/dry/default-off/readiness outcomes, exact1000/1001 bound, source evidence, preexisting shutdown signals, OAG previews, CLI budgets, CRA parser and PDF page lifecycle. These are sanitized bounded fixtures, not publisher or production qualification. `run_receipts_v2.py` adds complete tracked backend input binding (including JSON/PDF/SQL fixtures) to the retained earlier v1 code-oriented inventory; outcome/test selection is unchanged. Final complete-input normal/optimized receipts carry actual commands, environment, source inputs, raw/JUnit hashes and testcase identities. Overlapping cohorts must not be added together.
- Independent final Spec `spec-review-v4.md`:6 adversarial probes;88 changed cases pass normal and optimized Python3.13.9 on PostgreSQL17.6, complete Alembic chain through `a545b14a0001`, zero skips/failures/errors. Final Standards `standards-review-v4.md`: normal/O41 adapter cases,64 bridge/selector controls,11 actual peer-hook contract cases with inert ports,23 safe-projection cases,46 selected tests, active SQLite transaction and actual alarm controls; additional actual TS parser20 cases and12 Jest cases. Reports include full source/generator/output binding; no unresolved finding for this increment.
- The native alarm test commits an owned generation marker, then sleeps beyond a real SIGALRM (test-only30→1s). Marker and financial success persist, generation counters stay unknown/null, and no retry is performed. This is executable partial-effect evidence, not a fabricated audit or real social event.
- Cached Linux/Python3.12.15 image:46 focused guard/operator cases pass in both normal and optimized mode (`python312-final-{normal,optimized}.json`). No network, installs or live credentials. This is minimum-runtime coverage of those controls, not the full minimum-dependency suite.
- Frontend92 tests pass, zero pending/failures, including the actual existing Detail component rendering unknown generation metadata and redacting attacker strings. `frontend-final-v1-receipt.json` binds the complete tracked frontend input set and Jest output.
- Full `tsc --noEmit --incremental false` is **not green**. Exact accepted-base frontend archive and candidate produce byte-identical single TS2322 error at `components/map/StyledGeography.tsx:36` with the same installed dependencies (`baseline-tsc-v1.*`, `tsc-final-v3*`). No new ETL type error is claimed, nor is complete type acceptance. An initial external path-mapping setup failure is also retained. Critical flake8 is unavailable in both existing local and cached Linux runtimes; no dependency was installed to replace it. Hosted checks remain unavailable/off.
- Peer PR704 separately ran3 combined actual adapter/selector/dispatcher→hook/HTTP/event/draft controls on its owned migrated PostgreSQL. Its final `committed-link-v1` receipt explicitly notes that subsequent bridge uncertainty/projection bytes differ; it is combined-candidate evidence, not final merged-tree acceptance. This lane's final exact native timeout tests cover the later boundary. Coordinator must replay the integrated final tree.

## Original remaining code versus external/live gates

This is a coherent scoped increment, **not completion of all ETL/generation source coding or the full original plan**.

Remaining code/evidence-production prerequisites:

1. Current CoB writer does not emit a genuine publisher `publication_date` or explicit `publishable` eligibility. The adapter refuses those existing records; this lane does not infer an exact day from a fiscal year/report month or promote facts automatically. Genuine date/eligibility production and its authority need source-specific integration before ordinary source runs can produce eligible generated drafts.
2. Only verified CoB `actual_spent` has this producer port. Other Treasury/OAG/KNBS/CRA measures need their own exact evidence producer contracts, if selected for generation. Their existing native ETL mappings are preserved; no substitute semantics are asserted. Allocations are not mislabeled as actual expenditure.
3. The consumer/event/draft/audit/automatic hook resides in draft PR704. Default-off financial reconciliation can merge independently, but enabled generation requires that reviewed consumer/schema/control dependency plus final combined replay and actual role/capacity qualification. No new role grants are assumed or supplied.

External/source prerequisite: freshly retained unauthenticated official OpenData responses remain404(root),401(catalog),401(collections),404(old Socrata). Both401 bodies state `SB_0006: Subscription is canceled, the item is not accessible`. `official-research-v2/receipt.json` binds exact URLs/response bytes/hashes/generator. The historical CKAN/Socrata assumptions in old planning/skill text are not a current dataset contract. No named dataset/schema/units/terms/persistence contract was accepted, no bypass/substitute was used, and native/dispatch OpenData remains unavailable under #621/#602.

Live/operating gates #554/#583 remain: actual intended-host source/PDF/operator runs, every-writer/restart custody, source qualification, readiness/cancellation/restart behavior on the intended runtime and live release acceptance. Those are coordinator-owned. The original retained **935-page** CoB artifact requirement was read in `docs/operations/2026-10-07-cob-pdf-memory.md` and `docs/verification/2026-10-08-r2-storage-acceptance.md`: SHA256 `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`,1,129 tables,468 records,378 observations and1,404 public qualification fields. Prior hosted memory/storage acceptance is historical evidence; no fresh complete935-page replay/HTTP/R2/financial persistence occurred here. Parser/PDF bytes and prior accepted CRA/timeout/shutdown fixes were not rebuilt. Keep all parent issues open.

## Shared files, migrations, defaults and cleanup

Shared edits: `backend/seeding/cli.py` (conditional post-commit bridge), `backend/routers/admin_operations.py` (safe outcome allowlist), `frontend/lib/admin/ingestion.ts` (matching strict parser), existing operations adversarial test (one rendered metadata case). New source/bridge/projection modules and owned tests listed below. No `main.py`, social files, models/contracts/service, bootstrap role contract, migrations, package/lock, workflows or other lane files changed. No migration reservation needed; candidate graph remains accepted head `a545b14a0001`.

All new automatic invocation defaults OFF; global/account publishing, uploads, dispatch activation and automatic seeding were not enabled. No hosted resource, paid API/AI/TTS, credential/grant operation, model CLI, Actions dispatch, bot review request, production DB write, upload, source publication, merge or deployment occurred. GitHub Actions permission readback is false; PR is draft with no closing references. Both remote inline comments and review bodies were fetched and empty at initial delivery; no review request/check success is inferred.

Owned resources: ephemeral cached PostgreSQL `b15-etl-UUID` containers on55396, tmpfs storage, no persistent volumes, removed with exact name checks and free-port rebind; Python3.12/lint containers are `--rm` and absent. No web server/browser or new scheduler was started. A temporary dependency-reuse symlink under this checkout only was removed; no primary checkout files/dependencies were edited, installed, reset or stashed. External accepted-base typecheck archive remains retained evidence without its dependency link. Reviewers used separate owned artifacts. The primary dirty checkout and all peer containers/ports remained untouched.

## Implementation SHA256 inventory

- `backend/routers/admin_operations.py` — `7c891548b7940baf243d37157b33af351205b4f6ab5612ba0d436253b225fb60`
- `backend/seeding/cli.py` — `de6a1c10ca428fd24d0efe6cf7500d71629a16de800f83f1e617d7e5ad31058e`
- `backend/seeding/domains/fiscal_summary/__init__.py` — `a8f965c52a494214f733ceefbec85d06ebf0e00905e8e8b93c4d8b218199ca6f`
- `backend/seeding/generation_dispatch.py` — `b69f1278191cf2755e2d2239dbe1ba9882d56c27853fd234985bea7ec087baf5`
- `backend/seeding/source_observations.py` — `ddc4d6a2ed903f7799e9af9fdf74926c247254c5ea87f2d7d937494bb1cd8237`
- `backend/services/generation_outcome.py` — `f1bb885df9e4e337cfb735f5bc25ec7d0d1d3b1308c4d82c04b0609187ec5569`
- `backend/tests/b15_etl_fixture.py` — `c0eff597aa7e26d3416ed93fdd97ea14cda827751ba888e24ffaea49844732ad`
- `backend/tests/test_b15_etl_native.py` — `86775fee87623c63a8410565fb6b8089aea924452613ce993b0b5e9261c46a1d`
- `backend/tests/test_b15_etl_reconciliation.py` — `dd4976764829a12cbdfc2066f00f997bc3342a776063d87150a2f85cfef93194`
- `backend/tests/test_b15_generation_dispatch.py` — `8cb2e8ea2ac03601604f9528043ead61ded2c9acb38eb0323af836289643a123`
- `backend/tests/test_b15_source_observations.py` — `67f976d48de179e7f202ddbbdcf2cb4cf95e3f004769f8f08ff38c99f3bf3778`
- `frontend/__tests__/admin/operations/b15-generation-outcome.test.ts` — `505fe0937b7e528b76af6e8c38036a09b1e7226e67b02dc4c5a261742a872454`
- `frontend/__tests__/admin/operations/operations-adversarial.test.tsx` — `2af7bd6a9d9d33ece81a5aaca3fa3ce4c308ce54111c2e34abcd091d680c4046`
- `frontend/lib/admin/ingestion.ts` — `86eec17ad94796f61dbbd8eb1cc365e70968ce6db07c9951bce6302e281a76c7`
