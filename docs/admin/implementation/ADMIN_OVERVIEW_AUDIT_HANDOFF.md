# Admin overview, audit and navigation implementation handoff

Issue [#548](https://github.com/Rodgers31/audit_app/issues/548), parent [#545](https://github.com/Rodgers31/audit_app/issues/545). Authorized batch 6, 2026-10-08. This is local implementation acceptance; it does not certify deployed operations.

## Checkout and provenance

- Worktree: `/Users/roger/.codex/worktrees/admin-overview-audit/audit_app`.
- Branch: `codex/admin-overview-audit-completion`.
- Pinned base: `dbfa7c100731fd2aa1ee4cc7b872a3ab600eaeee`.
- Initial implementation head: `ee735c3d7459fea4e736deda2cdb7d7f8bef8408`; code after Spec repairs: `372d6e2`. Later review/handoff commits are on the same branch; the final brief records the final head and draft PR.
- The task had no attached artifacts initially. Codex `create_worktree` created and attached this checkout. The dirty primary checkout was never edited, switched, reset, stashed or installed into.
- Python 3.13.9 from the primary venv used read-only with this worktree's absolute `PYTHONPATH`, `PYTHON_DOTENV_DISABLED=1` and an empty process environment. No production dotenv loaded.
- Frontend lock SHA-1 `4324209d701c3874da8aa516a2d56f43f85a9d2e` matches `/Users/roger/.codex/worktrees/social-batch3-integration/audit_app/frontend/package-lock.json`. Its installed runtime is reused through this lane's ignored `frontend/node_modules` symlink: Node 22.19.0, Next 15.5.27, React 19.2.4, Jest 29.7.0, Playwright 1.58.2. No installs, lock or manifest changes.

## Behavior and acceptance matrix

| Surface/boundary | Implemented and executed | Remaining acceptance |
| --- | --- | --- |
| Overview ingestion | Runtime validates exact status/domain totals, finite safe counters; shows seven-day scope, errors, fetched time, volume and encoded domain/failure/job drill-downs. Raw error bodies omitted from overview. | Operations owns diagnostic detail, job semantics and provider counters; #554/#556/#557. |
| Overview ETL | Calendar due count says “sources due by calendar”; legacy `healthy` and additive `plan_status=available` say “Schedule calculated”; unavailable calculation is actionable and unknown calculation remains unverified; worker execution explicitly unverified. Reported timestamp separated from fetch time. | No worker/scheduler operating receipt invented. The documented #548 Operations health contract is consumed; producer/worker acceptance remains Operations-owned. |
| Overview users | With coordinated Users PR #559, labels the verified Auth population “Auth identities”, including identities without profiles; admin roles come from linked profiles. Rejects malformed/impossible counters. | Depends on #559's producer semantics; provider enumeration is bounded and is not an atomic identity census. |
| Overview social | Existing `/admin/social/system/status` reports publishing opt-in, delivery targets across all states, and fresh/stale/unavailable worker evidence; heartbeat plus scan required for active/idle. | Social status fixture is inert; actual social service/worker startup is #549's acceptance. |
| Overview audit/failure evidence | Loading and request errors distinguish unavailable evidence. No-record result says recording is best-effort. Manual refresh, cancellation and bounded polling of failures/social status retained. | A missing row cannot prove no mutation; operational audit failures remain logger evidence. |
| Audit API | Existing `require_admin`; no write route. Private/no-store + Vary Authorization for success, auth, invalid filters and storage/serialization outage. Absent table is sanitized 503, not zero activity. | Global malformed provider role-shape handling is #550; unchanged auth core requires coordinator integration. Method-not-allowed responses expose no audit data. Production DB ACL/retention acceptance not run. |
| Audit filters/pagination | Actor/action/target filters and inclusive API `since`/`until`; bounded days 0–36500, page 1–10000 and size 1–100. Descending timestamp then ID. Snapshot ID and fixed UTC time plus PostgreSQL visibility snapshot prevent new/backdated/late-committing root-writer rows from shifting pages. | PostgreSQL snapshot bookmarks expire after 15 minutes and require Refresh. Supported storage assumptions below. UI exposes bounded day windows, not arbitrary API dates. |
| Audit UI | Labelled submit-together filters, target-ID input, URL/history/back restoration, clear/refresh (including malformed bookmark normalization and actual refetch), atomic snapshot fields and snapshot transfer on paging, empty-page Prev recovery. Malformed 200 data fails as unavailable. Payload buttons expose expansion state; JSON rendered as text after policy. Invalid/future row times labelled explicitly. | Real browser run is local Chromium with inert auth/API transport; deployed and other browser acceptance not claimed. |
| Audit recording | Actual roles/delete/reset/ETL callers exercised. Public signature, None return and independent session/commit retained. Failure logging never attaches exception/SQL parameters/PII; failures cannot roll back caller action. | No reliable global completeness count. Helper records caller acknowledgment, not downstream execution. |
| Navigation | All current route families and social compose/accounts links covered. Most-specific boundary match, `aria-current`, named nav, visible focus, 44px minimum height, horizontal mobile keyboard focus scrolling. | Users/ingestion/social detail page workflows belong to their lanes; links are not acceptance of those pages. |
| Private browser data | Owned page reads require a current administrator and actor; actor-scoped keys, no-store, no extra retries and zero inactive cache retention. Layout cancels/removes departing actor queries without cancelling the next actor; access loss removes admin data. Inactive Refresh cannot issue private reads. | Shared middleware, Axios and auth provider remain read-only. Shared #550 repair is coordinator-owned. |

The existing PageShell, typography, pill navigation and card styling were preserved. The required 12ui skill was read; these are repairs within the approved shell and reuse its cards. No paid design generation or redesign was run.

## Audit payload/caller contract

`record_admin_action(db, *, actor, action, target_type=None, target_id=None, payload=None) -> None` retains its independent `SessionLocal()` transaction and caller timing. The caller's `db` is not committed/rolled back by the helper. No transaction ownership changed in user/ETL routers.

Policy applies before new writes, on legacy API reads, and independently in the browser:

| Current caller/action | Retained evidence |
| --- | --- |
| `admin_users.update_user_roles` / `users.update_roles` | `old`/`new` bounded role arrays; current supported `admin`/`citizen` values; unsupported values receive a redaction marker. |
| `admin_users.delete_user` / `users.delete` | Bounded syntactically checked deleted email; valid bounded creation timestamp. |
| `admin_users.send_reset` / `users.send_reset` | Bounded syntactically checked email; redirect presence with the entire redirect value redacted, including path/query/fragment/credentials. |
| `etl_admin.trigger_etl_run` / `etl.trigger` | Positive int32 job ID and strict boolean dry-run flag. This proves acknowledged queue creation only. |

All other action payload fields are omitted with a marker. Future action/role additions must coordinate backend and browser policy changes rather than silently exposing arbitrary values. Actor/target identity/action metadata remain private admin evidence. Social publishing uses its separate activity/history mechanism and is not claimed as complete coverage of this table.

Repository-wide `rg -n record_admin_action --glob '*.py'` found exactly these four mutation callers plus imports/docs/model/migration references. Every current writer reaches the shared guard. There are no independently edited user/ETL/social routers in this lane.

## Pagination/storage assumptions

The concurrency regression executed on disposable PostgreSQL **17.11**: one transaction allocated ID1 and stayed open, ID2 committed, page one captured total1, then ID1 committed. ID-only paging originally changed total to2; the repaired visibility predicate keeps total1 and page2 empty. JSONB redaction, UTC response serialization and absent POST were also executed on PostgreSQL.

PostgreSQL 13+ `pg_current_snapshot` / `pg_visible_in_snapshot` are used with bounded bound parameters. Their documented transaction semantics are described in the [official PostgreSQL reference](https://www.postgresql.org/docs/17/functions-info.html). Current helper sessions write top-level transactions. Because the table exposes a 32-bit `xmin`, a server-captured XID epoch at/after 2^32 fails closed as private unavailable evidence instead of silently interpreting it as a 64-bit transaction. Client malformed/unsupported snapshot metadata is a private 422. Epoch-aware support requires a follow-up storage design; production epoch/ACLs are unverified.

The snapshot relies on the existing append-only convention. Privileged raw SQL UPDATE/DELETE, subtransaction writers outside the helper, vacuum freeze changing historical row metadata, table rewrite/restore and migration behavior are not certified by these tests. No schema/ACL migration or production storage mutation occurred. SQLite exercises API/storage failures and the rendered fixture; its ID/time snapshot does not certify arbitrary external lower-ID inserts. The PostgreSQL test covers the supported root-writer commit race.

## Executed verification and red/green evidence

Commands/results are retained in [ADMIN_OVERVIEW_AUDIT_RECEIPTS.md](ADMIN_OVERVIEW_AUDIT_RECEIPTS.md). Initial executed baseline: 13 existing ETL/admin tests passed, two SQLAlchemy deprecation warnings. The retained pre-fix API suite had 11 failures/1 pass at pinned base; the rendered UI suite had seven failures. Further adversarial regressions were observed red before each repair: impossible/missing-row/snapshot parser failures (3); PostgreSQL late-commit race (1); timezone/email cases (4); Unicode visibility digits (1); visibility schema cases (7).

Final author checks at implementation head: 34 backend tests passed (including three actual PostgreSQL tests and existing 13 baseline tests), 34 frontend tests passed after Spec repairs; five Chromium scenarios passed on the final sequential replay, as recorded in receipts. Lane ESLint, complete TypeScript and Next production build passed. Browser controls ran actual pages with real audit/ingestion/ETL/user-stat router logic, real HS256 admin authorization against inert identities and a synthetic loopback Supabase transport; social status was a static fixture. They did not replace rendered controls with source assertions. Browser denied non-loopback requests. Two SQLAlchemy deprecation warnings, Next lint deprecation notice and expected missing public fixture-route 404s were observed; none was a claimed production receipt.

## Independent reviews

- Standards: PASS at `372d6e2`, zero hard violations and zero actionable smells. Full pinned-base diff and final handoff/receipts reviewed; all 13 recorded log hashes matched. No independent test rerun claimed.
- Spec: two author-fixable P2 findings at `ee735c3` (malformed bookmark recovery; additive Operations health interpretation). Five observed-red cases plus two actual-refetch red cases were fixed at `372d6e2`; independent follow-up PASS at `372d6e2`, zero remaining author-fixable findings. Reviewer independently reran both frontend suites (34 passed) and legacy/additive contract and bookmark probes; reviewed five-pass browser logs without rerunning browser servers.
- Adversarial: PASS at `372d6e2`, zero new findings. Final follow-up independently passed 27 atomic URL probes, 32 health contract probes and all34 frontend tests with no cache; unchanged backend and Chromium were not rerun in that follow-up. Earlier PASS within executed boundaries after independent replay. Final independent backend lane-only run: 21 passed, two warnings; actual PostgreSQL race and JSONB boundaries included. In-memory TypeScript executed 30 visibility/filter checks, 33 hostile numeric cases, 24 worker-state combinations, payload/aggregate/duplicate-row guards. All confirmed findings repaired and replayed. Production assumptions remain explicit above.

## Defects and cross-lane integration

- [#553](https://github.com/Rodgers31/audit_app/issues/553): audit recovery payload/SQL exception privacy and bounded private reads, implemented here after all-state deduplication.
- [#558](https://github.com/Rodgers31/audit_app/issues/558): impossible dates, incomplete row evidence, timestamp overflow and visibility schema guard consistency, implemented here after all-state deduplication.
- [#550](https://github.com/Rodgers31/audit_app/issues/550): shared auth provider role shapes; owned by coordinator/shared-core exception. This lane does not certify that fix.
- [#551](https://github.com/Rodgers31/audit_app/issues/551): user/provider mutation and count/search acceptance, Users lane.
- [#554](https://github.com/Rodgers31/audit_app/issues/554): ETL trigger acknowledges a pending row without a consumer; actual caller test verifies pending row/audit only, never execution.
- [#556](https://github.com/Rodgers31/audit_app/issues/556): calendar calculations masquerading as worker health; consumer here labels the existing contract honestly. Operations owns producer repair.
- [#557](https://github.com/Rodgers31/audit_app/issues/557): ingestion monitoring/diagnostic boundaries, Operations lane. Overview omits raw diagnostic text.

Coordinated consumer contracts preserve field names while adopting #559's Auth enumeration semantics. This overview wording depends on that producer repair. User stats retain four numeric fields; the calendar summary retains `running_today`, `skipping_today`, `total_sources`, `sources_to_run` and efficiency text. Overview requires the complete six supported sources, unique known planned source names and valid nonfuture timestamps. ETL health retains status and timestamp, adds plan_status=available|unavailable with scheduler/worker/freshness unverified; overview supports both legacy and additive health contracts. Failed list retains exact count/page/page_size/has_more and five or fewer failed rows; social status retains publishing flag, worker state/heartbeat/scan and queue counts. Audit response adds snapshot ID/time/visibility; both owned UI consumers were updated together.

## Coordinator review repairs

PR #562 review and cross-lane integration independently reproduced three private
dependency 5xx response leaks; all now expose the fixed unavailable body while
retaining their status and private headers. The audit helper documentation now
describes the fixed-message logging policy. Existing XID bounds already reject
epochs at/above 2^32: six new executable controls passed before repairs, including
server-captured 503 and supplied-client 422 before any audit-row query. No
epoch-aware production-storage support is claimed or introduced.

New rendered/parser regressions independently exposed incorrect Auth census
copy, incomplete/unknown/duplicate calendar sources, impossible/future calendar
timestamps, cross-administrator cache reuse and inactive Refresh. The corrected
suite against immutable original head had 17 failures/one valid control pass;
the retained backend review suite had three failures/six passing epoch controls.
One initial audit-row selector expected a full email but the existing UI displays
its local part; that harness expectation was corrected before replaying the
actual actor-transition failure. These fixtures use inert HTTP data and jsdom.

After repairs: the entire owned frontend suite passes 52 tests in three suites;
backend audit/review plus historical ETL compatibility passes 40 tests, with two
existing SQLAlchemy warnings. Complete TypeScript and scoped ESLint pass. These
review repairs did not rerun PostgreSQL, Chromium or a production build; the
coordinator must execute the combined tree with #559/#560/#561. Historical actual
caller tests still exercise this branch's original Users/ETL routers and require
coordinated adaptation/replay when those producers are integrated. No pushes,
external review replies, new bot requests, live services or storage mutations
were performed by the independent reviewer. Raw replay commands/outputs are in
the coordinator's BATCH_6_REVIEW/spec artifact.

## Closeout boundaries

No merge, issue closure, production deployment/migration, publishing, real user deletion/email/provider/storage operation, production environment change or paid/bot review request. Operational parents #481/#488/#490/#525 and dependency issue #494 remain open pending their own evidence. Local tests cannot close them.

Owned PostgreSQL container `batch6-admin-overview-audit-pg` (loopback55473, disposable cached postgres17 image) was stopped and automatically removed after tests/reviews. Fixture/API8153 and Next3153 terminated with Playwright. Final container listing was empty and no listeners remained on3153/8153/55473. Draft PR attachment and final documentation head are recorded in the final brief. No implementation work remains interrupted. Temporary setup/test path mistakes and a concurrent generated-file check conflict were corrected and affected commands replayed sequentially; only completed green results count.
