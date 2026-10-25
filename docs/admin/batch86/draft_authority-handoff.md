# B86 native draft authority — issue 802

Base `a459834e31280b1e81b0604d16d687bc9ad7fffe`; branch `codex/b86-draft_authority`.
Related #802, #476, #545, #699. Issue 802 remains open: this delivers concrete native
neutral-report paths for three priority nightly domains, with real-source and
operating limitations below. It does not complete notifications for all domains.

## Delivered behavior

`seeding/native_report_authority.py` captures a runtime-only, mutation-detecting
capability from retained official bytes. PDF inputs are read independently from
the actual first three pages, never supplied cached page text. Supported PDF
scope is an annual national CoB report or an explicit OAG auditee/year-ended
heading, with exactly one full `Publication date:`/`Published on:` day. Month-only,
signature, reporting-period, upload and retrieval dates do not qualify. Annual
period end must precede or equal publication. KRA supports the independently
reviewed achieved annual-results lead and labelled article day; a bare FY mention,
quarterly/monthly result, forecast or target cannot establish annual scope.

The native national-budget fetcher/writer, KRA release/overlay/parser/writer, and
actual audits domain retain these contracts. The sealed capability is removed
before normal JSON row provenance is persisted. Native writers bind an existing
Extraction receipt to SourceDocument identity, Kenya, exact running job, report
series, retained artifact and source identity snapshot; they do not commit for
the caller. Suppressed/altered bindings, missing-proof invalidation, deferred
constraints, and receipt/job readback fail visibly. Rollback retains prior
committed authority. Older receipt records remain available for evidence.

Postcommit readers require fresh read-only PostgreSQL snapshots, exact completed
non-dry live-job lineage, valid chronology, intact receipt/binding and unchanged
current source identity. National/KRA each have one annual series; a newer
completed live/partial native job invalidates older job authority, including a
new job without qualifying report authority. Rolling OAG jobs supersede only the
same auditee's newer qualified series, so an unrelated auditee does not invalidate
an unchanged report. The checks cover admitted native report contracts, not a
claim to inventory every report on the publisher's site. Native final completion
and draft admission use bounded transaction locks; receipt/source readers retain
statement/lock budgets and the existing 30-second acceptance budget.

Neutral adapters are connected to capability, committed-ID selection, preview,
admin detect and the default-off CLI postcommit seam. Native report IDs are
Extraction IDs in `ingestion_jobs.metadata.native_report_records[domain]`;
county-budget IDs remain BudgetLine IDs. `DetectCommand.domain` defaults to
`counties_budget` for existing callers. KRA has its own `kra` allowlist token,
not a Treasury identity. Its canonical application destination is `/budget`,
which contains revenue sources; there is no invented `/revenue` route.

The existing detector owns silent first baselines, explicit reasoned backfill,
semantic changes, replay/concurrent deduplication, release chronology and
supersession. Retrieval/job IDs or layout/digest-only refreshes do not announce
a new report; an artifact refresh can still invalidate an older reviewed draft.
Financial A→B→A behavior remains in the existing financial detector; these native
neutral adapters emit no monetary facts. They retain the separate known-refusal,
partial and uncertain-commit telemetry, with null unknown totals and independently
confirmed prior progress. No automatic retry is added. Both package and top-level
launches use one model graph; the shared receipt import correction adds no alias.

## Source and activation matrix

"Implemented" describes code capability, not eligibility of every record or
production adoption. All new neutral sources remain live-unaccepted and the
existing generation ceilings/runtime controls were not enabled.

| Domain | Financial | Neutral report | Real source / remaining contract |
|---|---|---|---|
| counties_budget | Existing qualified actual figures | Existing | Retained CoB contract unchanged; per-record gates remain |
| national_budget | Unsupported | Implemented native PDF producer/reader/draft | Current official FY2025/26 PDF retained and refused: first three pages have no supported full publisher-day label |
| revenue_by_source | Unsupported | Implemented native KRA producer/reader/draft | Official FY2024/25 article qualifies date/scope; current FY2025/26 dashboard page is refused by this article contract |
| audits | Unsupported | Implemented native PDF producer/reader/draft | Explicit annual auditee plus full publisher-labelled day required; independent synthetic producer tests pass; no genuine OAG edition qualified here |
| pending_bills | Unsupported | Unsupported | Retained full publisher-day/document-wide scope missing; 800 owns fetcher/writer, no overlapping edit or duplicate store |
| economic_indicators | Unsupported | Unsupported | Exact report/job lineage |
| population | Unsupported | Unsupported | Retained full publisher-date/report scope |
| county_officials | Unsupported | Unsupported | Reviewed public report/date/scope contract |
| national_debt | Unsupported | Unsupported | Retained full publisher-date/report scope |
| debt_timeline | Unsupported | Unsupported | Exact report/job lineage |
| fiscal_summary | Unsupported | Unsupported | Exact report/job lineage |
| learning_hub | Unsupported | Unsupported | Reviewed public report/date/scope contract |
| stalled_projects | Unsupported | Unsupported | Retained full publisher-date/report scope |
| national_gdp | Unsupported | Unsupported | Bound full-date report authority; bare date metadata insufficient |
| imf_weo | Unsupported | Unsupported | Exact report/job lineage |
| county_borrowing | Unsupported | Unsupported | Full publisher date/report/job authority; positive stock alone cannot qualify |
| cra | Unsupported | Unsupported | Recommendation scope lacks retained full-day authority |
| opendata | Refused | Refused | `source_extracted_not_publication_qualified`; workbook publication date remains null |

The unsupported rows retain the accepted B83 inventory and registry refusal
contracts; this session did not independently crawl every publisher. Their
remaining native authority/financial-adapter engineering stays under #802.
The new adapters do not relabel unqualified financial observations as availability.

### Actual source receipts

Bounded official-source requests used certificate validation, finite byte/time
budgets and no retries/redirects. Full bodies/PDFs stay outside Git.

- [Official KRA FY2024/25 release](https://www.kra.go.ke/news-center/press-release/2235-kra-grows-revenue-by-6-8-despite-tough-economic-environment-4):
  full publisher day **2025-07-10**, period FY2024/25. Final retained HTML SHA256
  `c9fe7b05529c42a0b1181c7dc4465905419ff6cc57275e42be7f912481c28267`,
  119,603 bytes. Repeated HTML hashes changed with page scaffolding; report
  date/scope remained the same. No new-release claim follows from that change.
- [Current KRA annual page](https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026):
  HTTP200, SHA256 `97820f4a3943241500b2f0d053fa7662ab2c1e83f6b8095aef60cc4522841b48`,
  91,512 bytes; no accepted article-day/annual-lead authority. No substituted date.
- [Official CoB current national PDF](https://cob.go.ke/download/national-government-budget-implementation-review-report-fy-2025-2026/?wpdmdl=16454):
  HTTP200, SHA256 `f99ec2997f13400d2fc1fb340154c9b91640591c6d1351415fc075b259a7c4b1`,
  15,609,728 bytes. Cover inspection found no supported publication label. Dates
  1 July2025/30 June2026 are reporting-period dates, not publication authority.

KRA FY2024/25 is a genuinely qualified source artifact; it is not evidence that
current nightly selection, successful live jobs or generation have adopted it.
The newer dashboard must not be bypassed by treating an older article as current.

## Executed verification

Evidence root (local):
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH_86_BUILD/draft_authority`.

- Unchanged-base valid CoB/KRA controls passed and two extension assertions failed
  (`baseline-red.log`), then passed. Independent findings retain their original
  executable red controls and author/reviewer green reruns.
- Final owned PostgreSQL17/current Alembic `a756b20a0001` cohort: **119 passed**
  normally and optimized. Includes native valid/hostile controls, current CoB
  cohorts and the inherited 41 committed-reader cases with only their historical
  fixture transport rebound to the explicitly owned current database. Logs:
  `final-pg-{normal,optimized}.log`; exact rebind `current_reader_plugin.py`.
- Selected affected backend regression: **166 passed** (`regression-corrected.log`).
  Initial broad attempt had 153 passes, a now-updated capability expectation,
  and setup errors from an excluded parent fixture/Docker-inside-Docker; that
  run is retained and is not passing evidence.
- Frontend: **50 passed**, matching-lock TypeScript passed. No production build
  is claimed. Shared node_modules was read-only, mounted through an owned test
  symlink; no install or peer-cache mutation.
- Independent Spec: **8 passed** normally/optimized, including actual national,
  KRA and audit producer-to-PG-to-preview/draft paths; exact positive source
  grammar/hostile scope and pure-package controls. `spec-review/FINAL.json`.
- Independent Standards: **57 offline + 7 PG** cases normally/optimized;
  six reproduced findings corrected: annual chronology/scope, stale artifact,
  package graph, safe reason custody, wrong country, suppressed invalidation.
  Per-auditee supersession also executed. `standards-review/FINAL.json`.
- Actual CUA Chrome used the production SocialAutomation/GenerationPreview
  components and actual FastAPI/admin/PG paths, inert local auth/job/transport,
  replaying **unedited retained official KRA bytes** with the recorded hash.
  Baseline created zero drafts; preview unchanged/explicit backfill, then a
  reasoned local detect created exactly one pending-review post. Readback:
  **zero publications, zero targets**, no approvals/scheduling/uploads.
  OpenData stayed unsupported; duplicate preview IDs disabled the action.
  `browser/inputs.json`, `http.jsonl`, `effects.json`, `draft-created.png`.
  A Docker-host→macOS loopback fixture transport failure was repaired before
  these cases; it was not an application defect or a passing UI case.

Counts overlap and are not added. Test `source_mode=live` jobs are explicitly
local fixtures, not successful production/native-job acceptance. The Chrome
check is scoped functional/accessibility-label evidence, not full WCAG/mobile
certification. No hosted mandatory checks were enabled or dispatched.

## Migration, access, rollout and rollback

No model, migration, lockfile, grant, source plan or workflow is changed. Existing
source/receipt/social migrations are required; current-head tests exercised the
unchanged migration graph. Native authority reads need the existing ingestion/admin
source role. No broader restricted publication-worker access is granted or
qualified; future worker/source acceptance remains root-owned and held.

Both `SOCIAL_GENERATION_HOOK_ENABLED` and `SOCIAL_REPORT_GENERATION_ENABLED` keep
literal default false. Audited GenerationControls must separately permit drafts,
exact source token (`cob`, `kra`, `oag`) and reviewed account targets. First baseline
is silent; first backfill requires an explicit admin reason/idempotent command.
This session sets no production control, backfill or source opt-in. Auto approval,
scheduling/publication, publishing, uploads and native/supervisor workers remain
off under the existing controls. Tonight's admitted SHA/schedule is untouched.

Future root/operator acceptance must qualify current editions and exact native
successful live-job/source receipts, review source/account selection/access and
resource bounds, and observe a draft-only rollout. Current CoB day authority,
latest KRA dashboard authority, genuine OAG publication-date qualification and
other unsupported producers remain dependencies. No new source/provider service,
credential, paid review, preview, plan or production write was introduced.

Rollback is code rollback and/or disabling the existing draft ceilings/controls.
Keep retained receipts/cursors/events/revisions/command receipts. Do not delete
baselines, mutate historical proof or automatically retry uncertain commits.
Inspect existing drafts before an explicit audited retry. No downgrade migration,
backup/key/retention change or tonight's ingestion change is part of rollback.

Fresh read-only Copilot personal controls and repo rules show automatic/draft/new
push review off/no repo automatic review rule; Vercel Preview Branch Tracking is
off. Required approval/five checks remain a root release gate. The author PR stays
DRAFT, with no ready/merge/deploy or bot review request.
