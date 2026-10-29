# Independent Spec review — combined four-PR release

**Pass within the executed scope on frozen candidate4. No unresolved finding.** Execution on3 carries to4 through identical product/UI and executed-suite bytes;4 changes only an author test fixture. Two direct-helper findings in candidate1 were reproduced, retained as desired regressions and closed on candidate3. This is a scoped executable Spec verdict; it does not claim the full backend suite is green or authorize deployment, publishing or worker activation.

## Frozen identity

Final `combined-release-candidate-4`, manifest `combined-release-manifest-4.json`, SHA256 **`7a90b35eef28e40825392676344a4ffd2f6ed70f7eece1ef51419ae82cbad8e1`**, **5,730 tracked files**, zero mismatches (`manifest4-verification.json`). Executed candidate3 was likewise verified against `58f9922b53dd73b98b9988abe660cdcf94aba2af6efdb323b73b231b6c7fe9bb` (`manifest3-verification.json`). Candidate1 was also verified against `1657041ae2e421531db0be44ec1088dc2398e3754d20077d8872f7ea2c6467de` before its execution.

Exactly four files differ between1 and3: destination.py, social_copy.py, their report-destination regression test and the national-writer test’s FY-label assertion. All813 frontend manifest entries are identical, justifying the explicit UI safeguard carry described below. No candidate bytes were edited by this reviewer.

The sole3→4 change is `backend/tests/social/test_universal_copy_postgres.py`: import the existing `restricted` fixture, use it for the national-report test and unpack its four-tuple. All product/UI and the selected executed test files are identical. The owned PG had already been removed when4 arrived; this author test was therefore not rerun, consistent with the parent’s “if PG still present” condition. The independent final actual national-report HTTP/backfill/current-witness path below already used that fixture and passed. No source/witness gate changes occur in4.

## Results and negative controls

**351 unique normal-mode cases pass, including277 independent cases and74 repository cases.** Eleven of those independent boundary cases also pass under `python -O` (repeated checks, not eleven additional unique cases).

| Executed selection | Unique passes | Receipt |
|---|---:|---|
| Candidate3 numeric/replay/universal/direct boundaries + repository report/financial destination/source-selection controls | 262 | `final-unit.log` |
| Candidate3 actual guarded-PG HTTP chain and recorded-version policy gates | 13 | `final-pg.log` |
| Candidate3 public pending-bills HTTP/cache/selection suite, including four independent cases | 36 | `final-public.log` |
| Candidate3 actual final backend-saved payloads rendered by actual queue decoder/preview | 6 | `final-ui-captured.log` |
| UI actor/revision/error/overrides, BudgetTab focus/absence/retry and receipt safeguards, carried on identical frontend bytes1→3 | 34 | `ui-cross-stack.log` (three passing suites; unrelated six fixture path assertions are accounted below) |
| Candidate3 direct boundary controls under Python optimization | 11 repeated | `final-boundaries-optimized.log` |

Six actual owned PostgreSQL flows execute **source-records HTTP selection → read-only preview → explicit reasoned detection/backfill → immutable saved revision → actual detail/evidence HTTP DTO → UI decoder and QueuePostPreview**: national report, county report, retained KRA catalogue entry, national-budget financial, KRA financial, and county pending-bills financial. Inputs come from real repository producers/writers with sealed synthetic/retained evidence, not submitted arbitrary observations. The county financial batch uses the actual25-record page. Selection/preview leave cursor/event/post/command-receipt counts unchanged. Same-key command replay returns the saved receipt; a fresh key does not duplicate current drafts. Every saved draft remains pending review; current generated-revision verification passes with the owned digest ports installed.

All six final DTO payloads are retained in `backend-chain.json` and pass the actual frontend decoder/preview unchanged. New reports/catalogue link to their qualified original document/entry; national financial-v4 links to the source used by its figures. County financial-v3 keeps the actual Entity slug, selected date and `#pending-bills` anchor. Text and link appear only after explicit preview activation; preview performs no mutation. The catalogue retains unknown publication day and human-review wording.

Independent stale-selection attacks modify the qualified record’s reporting year, source-document URL or extraction evidence after selection; all refuse detection with `SOURCE_NOT_ELIGIBLE` and create no post. Disabled generation and unauthenticated commands refuse. Every owned HTTP chain checks publishing/auto-approve/auto-schedule/auto-publish false, worker unavailable and zero publications/targets. No worker process is started.

Recorded V1/V2/V3 report tests use actual current qualified county evidence and real immutable revisions. Matching text/link/scope passes the source/materiality/link gates and reaches the deliberate `ACCOUNT_NOT_ALLOWLISTED` delivery hold. An opposite-version scope refuses `SOURCE_SCOPE_CHANGED`; substituting an old canonical link into a V3 document, or a publisher link into a V1/V2 document, refuses `GENERATED_COPY_EDITED`. These are focused candidate-gate controls using in-memory alternative scope/document objects; they do not forge or claim acceptance of immutable policy snapshots or bypass the delivery hold.

The numeric oracle rechecks128 scale/rounding/carry/low-precision cases. **27 accepted records were captured by executing backend commit `47a1490318ab2897c74ce9704bff68597ac9b677`**, then replayed on3: exact text, metadata, fingerprints, and applicable accepted-default destinations/scopes match. Explicit legacy financial copies are text/metadata replay controls; the old unversioned destination helper is not used to invent links for historical financial revisions. Generic six-category/source coverage and classifications/units remain attributed individually. Public-reader controls verify exact historical date, absence, zero, conflicting-source refusal, source notes from the selected rows and county/date cache isolation.

## Closed findings

**S1 — P3, direct destination input-shape inconsistency.** On1, `draft_destination(None, source.model_copy(...))` returned `javascript:alert(1)` from unvalidated report/fact document URLs and accepted schema_version99. This was an internal direct-call contract failure; the HTTP generation/source-authority path remained guarded. `test_direct_boundaries.py` contains exact reproductions; `direct-boundaries-red.log` retains the three observed reds. Candidate3 validates the Python-mode SourceObservation at destination entry; all three refuse.

**S2 — P3, direct renderer version/family inconsistency.** On1, `render_social` silently rendered for invented/None/financial-v4 versions and supported-but-wrong-source families. Desired cases are in the same test file; `direct-boundaries-red.log` and `cross-family-red.log` retain seven reds. Candidate3 explicitly checks a strict string version and the source-compatible version family, including rejecting financial sources in this renderer. All eleven combined boundary cases pass normally and optimized.

## Environment, retained failed attempts and limits

All project execution used owned capped offline Docker. Python runtime `admin-redesign-python-runtime:local`, SHA256 `571e327e2fbe507713d267f6f15050d585a5bbb53b8ec2e3afc73db2996d6d2d`; Node24.22.1 `admin-redesign-node-tools:local`, SHA256 `199a2e300b058b48b009358105fa1749007be613917893abc008d9d50ae991f3`, locked dependency volume read-only. Runners CPU1/memory2GiB/PID256. PG17 CPU0.5/memory512MiB/PID128, offline internal55412, guarded database `b83_social_test`, Alembic `a756b20a0001`. PG runners share only its isolated namespace. The existing restricted fixture installs temporary roles/digest views in this owned DB; it starts no worker and never enables publishing.

Retained setup/fixture failures are not presented as green: initial migration raced PG readiness (`migration-startup-red.log`); a no-port rehearsal correctly refused five native revisions for missing worker-authority witnesses (`backend-chain-missing-port-red.log`, also one overly specific default-off expectation); the first25-record capture searched only the20-row queue page (`backend-chain-page-fixture-red.log`); six already-rendered UI payloads initially failed my API-path assertion because Axios adds `/api/v1` in its base URL (`ui-path-fixture-red.log`); and policy setup initially had a baseline without a prior SourceEvent (`policy-prior-event-fixture-red.log`). Only owned fixture setup/expectations changed; final3 reruns pass as counted above. Product red/green findings are separately recorded above.

This reviewer did not repeat the author’s full frontend build, broad full-backend baseline comparison or timed46-county cohort and does not absorb those into this verdict. The author separately reports the same60 failures/33 errors on93 exact accepted-baseline IDs; that comparison was not executed by this reviewer. No source/witness gate was relaxed here. No providers, hosted tests, paid services, real sources or production were accessed. No product commits or deployment changes were made. The owned `combined-release-spec-pg` container was removed and both synthetic credential env files deleted after execution; root/other reviewer databases and user worktrees were untouched.
