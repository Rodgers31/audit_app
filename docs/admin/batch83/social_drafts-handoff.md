# B83 social drafts handoff

Base: `7c7b309158480e61206a453e7d844fcf5075b3b9`. Branch: `codex/b83-social-drafts`.

This delivery qualifies the existing CoB committed-evidence draft path and adds
operator visibility. The neutral report producer already existed in accepted
PR716/issue719; this delivery does not claim to have introduced it. Only
`counties_budget` has an eligible adapter. Capability/refusal coverage now includes
all fifteen legacy native domains and the CRA/OpenData/county-borrowing opt-ins. Further eligible
source adapters need accepted source contracts; this PR does not fabricate them.

## Behavior

- Each normally finished native job records separate financial/report generation
  skip or pending receipts on its existing transaction. Disabled generation opens
  no additional reader or social schema. Old jobs lacking receipts remain unknown.
- Post-commit generation retains exact known baseline/unchanged/draft/refusal
  counters and allowlisted refusal counts. Known evidence refusals roll back that
  record and continue the cohort. Database/unknown errors remain errors.
- An exception during or after commit never certifies zero effects. Totals become
  null with `execution_unverified=true`; `confirmed` is the independently completed
  prior progress, not an estimate of the current record. Confirmed refusal reasons
  remain bound to `confirmed.refused`; they never certify unknown totals. No automatic retry follows.
- Telemetry writes flush, execute deferred constraints, refresh and compare the
  intended complete JSON and preserved job fields. Suppressed/changed receipts
  roll back the telemetry transaction and log receipt unavailability. Previously
  committed facts/cursors/drafts remain committed. The pending receipt or absent
  receipt tells operators execution is unverified.
- Financial and neutral CoB readers now both require retained full publisher-date
  authority. Bare document date metadata is insufficient. Existing old rows without
  that authority are refused; no source row or immutable event is rewritten.
- Authenticated private/no-store capability and read-only preview endpoints expose
  exact per-record eligibility, baseline/no-change and refusal reasons. Preview
  writes no source cursor, event, draft, audit or command receipt, and does not enable
  controls. It uses existing committed readers, at most25 unique bounded IDs, a30s
  monotonic acceptance budget and two bounded cursor/event projection queries.
  It rechecks the deadline after session acquisition, and preview transaction
  statement/lock limits shrink to the remaining budget without relaxing inherited
  limits. Source readers retain their existing per-statement bounds; this is not
  a hard cancellation of session acquisition or an in-flight source call. It reads no credentials or network sources.
- Preview refuses multiple anchors for one report/fact series and tells the operator
  to select one. Template placeholders are refused before claiming eligibility.
  Responses must match the requested record cohort exactly. Detection remains the
  separate audited idempotent command, rechecking evidence and serializing changes.
- The Social Automation page adds preview; job detail displays both outcomes,
  missing receipts, refused reasons and unknown versus confirmed progress.

The existing detector/version/release identity, baseline and explicit reasoned
backfill, immutable evidence, source correction/supersession, human review and
approval/queue/worker admission contracts are retained. Retrieval, ingestion ID,
artifact digest/layout changes or unchanged facts do not establish a new report.
No changes were made to generation/policy/publication/upload defaults, worker
startup, source selection, native ownership/acknowledgement, financial writers,
dependency locks or production configuration. The only workflow addition forwards
`SOCIAL_GENERATION_HOOK_ENABLED` and `SOCIAL_REPORT_GENERATION_ENABLED` from existing
repository variables, each defaulting to literal `false`; no variable, source plan,
schedule, action, dispatch admission or accepted nightly SHA is changed.

## Supported-source and acceptance matrix

“Unsupported” below is the current draft adapter capability, not an assertion
that an ingester failed, that a publisher has no report, or that financial data is
empty. The listed reason is a primary missing contract, not an exhaustive audit.

| Native domain | Financial drafts | Neutral report drafts | Current prerequisite/refusal |
| --- | --- | --- | --- |
| counties_budget | Supported, qualified actual spending only | Supported, exact county/report/period | Official available retained PDF, exact successful live job lineage, qualified actual figure, bound full publisher date, current report authority; each record may still refuse |
| audits | Unsupported | Unsupported | Retained full publisher date/report authority |
| economic_indicators | Unsupported | Unsupported | Exact report/job lineage |
| population | Unsupported | Unsupported | Retained full publisher date/report authority |
| county_officials | Unsupported | Unsupported | Reviewed public report scope/date contract |
| national_debt | Unsupported | Unsupported | Retained full publisher date/report authority |
| national_budget | Unsupported | Unsupported | BudgetLine lineage/receipts exist; retained full-date producer/report contract missing |
| pending_bills | Unsupported | Unsupported | Retained full publisher date/report authority; no sibling aging assumption |
| debt_timeline | Unsupported | Unsupported | Exact report/job lineage |
| fiscal_summary | Unsupported | Unsupported | Exact report/job lineage |
| revenue_by_source | Unsupported | Unsupported | Publisher date remains absent in native source metadata |
| learning_hub | Unsupported | Unsupported | Reviewed public report scope/date contract |
| stalled_projects | Unsupported | Unsupported | Retained full publisher date/report authority |
| national_gdp | Unsupported | Unsupported | Date metadata alone does not establish a bound full-date report contract |
| imf_weo | Unsupported | Unsupported | Exact report/job lineage |
| county_borrowing (opt-in) | Unsupported | Unsupported | Retained full publisher date, exact report/job lineage and current report authority are absent; pinned report period alone is insufficient |
| cra (opt-in) | Unsupported | Unsupported | Recommendation evidence has no retained full publisher date authority |
| opendata (opt-in) | Refused | Refused | `source_extracted_not_publication_qualified`; workbook publication date is null; retrieval/report month cannot substitute |

The registry is `backend/seeding/generation_capabilities.py`. It does not expand
scheduled `--all`, promote extractions or add a parser/crawler. Other-domain source
qualification and root/operator rollout remain dependencies under existing social
and source acceptance work; KNBS follow-ups744/745 remain relevant. Original
parents476/545/699 and source/operator gates remain open. Non-CoB draft adapter
engineering is explicitly tracked by [#802](https://github.com/Rodgers31/audit_app/issues/802).
The combined source deliveries retain separate missing-evidence boundaries in
[#800](https://github.com/Rodgers31/audit_app/issues/800) (assembly pending-bill aging)
and [#801](https://github.com/Rodgers31/audit_app/issues/801) (actual county debt stock).
This delivery does not claim those source contracts or full nightly acceptance are complete.

## Verification and limits

Evidence directory:
`/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/BATCH_83_BUILD/social_drafts`.

- Baseline: four behavioral tests failed on unchanged frozen application code for
  dropped safe reason, missing unsupported-source result, absent refusal breakdown,
  and missing preview route. Raw `baseline-red.log` retains assertions.
- Independent Spec:29 cases normally/optimized. Standards:52 Python cases
  normally/optimized,27 hostile frontend controls,21 current PG cases and five
  independent PG trigger controls. They found and rechecked refusal
  counting, template eligibility, cohort identity, commit uncertainty and timeout
  shape defects. Original failing controls and subsequent passes are retained.
- Current-head PostgreSQL17:21 cases passed normally and optimized. It uses the unchanged Alembic head `a756b20a0001` in an
  owned loopback fixture. Actual offline PDF/parser/writer/retained-date/figure
  qualification, preview/baseline/change/replay/concurrent dedup, explicit HTTP
  backfill/idempotency, current source refusals, three after-commit exception
  classes, telemetry mutation and native API→CLI→writer/ownership paths execute.
- The separate historical `a708b15a0001` neutral-report cohort passed15 cases;
  it includes synthetic policy/worker controls. This is historical local protocol
  coverage, not current provider activation. Results overlap and are not summed.
- Existing committed-reader contracts:41 cases passed against the same owned current
  schema, replacing only their historical fixture transport with an explicit owned
  current-schema connection. Original assertions run unchanged apart from the new
  retained-date fixture. This cohort overlaps current-reader controls.
- Selected backend regression:241 cases normally and optimized on prepared Python3.13 runtime. The initial
  broader run had239 passes/two child-import setup failures because the shared
  interpreter lacked PyJWT after child tests cleared PYTHONPATH. A small owned
  runtime reuses the same read-only packages plus cached PyJWT2.15.1; both child
  paths then execute. Source snapshots and normal/optimized logs are retained.
- Frontend:128 affected Jest cases; matching-lock TypeScript check. Actual CUA
  Chrome inert fixture verified result states, OpenData refusal, explicit backfill,
  duplicate-ID disable, job links, visible labels/focus and unknown progress.
  This is not a full accessibility or mobile certification.

Controlled fixture jobs use `source_mode=live` to exercise the committed guard;
no official source or provider request occurred. No fresh official PDF was
qualified by this session. No numerical public claim, production ingestion,
provider authorization, storage/capacity/billing or nightly success is certified.
The coordinator owns the first full nightly acceptance on25October2026.

## B84 review corrections

Evidence: `BATCH_84_REVIEW/797` beside the historical B83 evidence directory above.
The original B83 receipts are preserved. Four package-mode review findings are
valid (the refusal finding understated repeated sites); the mutation assertion
finding is invalid for the frozen lock. React Query5.90.21 / query-core5.90.20
calls the mutation function with variables and context: the unchanged visibility
suite passed9 tests before correction. Its second-argument assertion remains.

The corrected readers use their launch mode's model graph, without `sys.path`
aliases or a second `Base`. The package path traverses inherited service imports,
including the eagerly imported auto-seeder; those dependency imports are matched
without starting a task or making network/database requests. Actual current-schema
financial and report reader/preview controls execute in isolated subprocesses for
both package and top-level launch modes. Unrelated legacy service branches have
not been qualified as generally package-compatible.

The body-only operational, deadline and refusal-custody findings were reproduced
and fixed. Fresh-session/non-PostgreSQL source failures are operational failures;
known evidence refusals remain per-record refusals. Preview expires before touching
the database after an over-budget session acquisition. Confirmed refusal counts
survive later commit uncertainty through dispatch validation, persistence, the safe
projector and frontend decoding; hostile/mismatched counts are rejected.

Review validation on retained Python3.13:143 selected generation/import/native
cases and207 inherited financial-reader/ownership cases passed normally and optimized.
Current Alembic `a756b20a0001` / PostgreSQL17:25 cases passed normally and optimized,
including the unchanged21-case cohort and four new launch/uncertainty/budget cases.
The existing41 committed-source tests ran normally and optimized on that owned
current schema with their fixture transport explicitly rebound. The final24-case
review cohort also passed normally and optimized, including both operational codes. Frontend49 selected cases and the matching-lock
TypeScript check passed. Chrome's owned inert fixture confirmed the scoped refusal
list while totals stay unknown and the explicitly unsupported county-borrowing
preview. Only one synthetic preview POST occurred; no draft/publish/upload request
or production connection was made. Browser evidence is a local contract check,
not a production layout or accessibility certification.

Initial setup mistakes (missing parent fixtures/PYTHONPATH, Alembic working directory,
and a CursorResult conversion in the new test) are retained separately; they are not
application failures or passing evidence. The corrected runs above executed their
assertions. Parent coordination owns independent final reviews, push/replies and
combined-source validation. Publishing, uploads, native activation and generation
remain off; no deployment, live refresh, source request or paid resource is included.

## Rollout, migration and rollback

No new migration or grant is required. Existing social/report migrations must be
present before enabling draft detection. No production migration was applied.

Root-only future proposal, **unapplied**, after source/operator acceptance:

```yaml
SOCIAL_GENERATION_HOOK_ENABLED: ${{ vars.SOCIAL_GENERATION_HOOK_ENABLED || 'false' }}
SOCIAL_REPORT_GENERATION_ENABLED: ${{ vars.SOCIAL_REPORT_GENERATION_ENABLED || 'false' }}
```

Both defaults remain false. CoB new-row qualification has its separate default-off
`SEED_COB_VERIFIED_QUALIFICATION_ENABLED`. Audited GenerationControls additionally
requires drafts enabled and source `cob`; no first backfill is chosen here.
Publishing, policy automation, automatic approval/scheduling/publication, uploads
and native workers remain off. Seed workflow/live variables/admitted SHA are root
owned and unchanged.

Rollback is code rollback or operator disabling these draft ceilings/controls.
Retain existing evidence, cursors, events, revisions and receipts; do not delete
baselines to force generation or retry uncertain publication effects. Inspect
existing drafts before an explicit idempotent detect retry. No downgrade or
historical backfill is implicit.
