# Meaningful native financial review drafts — #802

Base: `f33cdcfb3afbcb7d1634f39b4df7e0fe92d0025e`. This is engineering and
offline source qualification. #802 and the original-plan checklist #699 retain
their outstanding source and operational acceptance criteria.

## Contract

The new native financial lane consumes exact current-job BudgetLine,
RevenueBySource or Loan records. It requires both the existing measure-specific
qualification and the separately retained native report publication authority.
The financial cell and publisher report must identify the same source bytes;
KRA catalogue-only evidence has no publication day and cannot qualify money.
The consumer re-reads and locks current authority and the business row before
any baseline/event/draft mutation and again before generated-revision approval.
An old source snapshot, unsuccessful/partial/fixture job, explicit quarantine,
missing receipt or unqualified measure refuses. No production authority is
inferred from a synthetic fixture's `source_mode=live` label.

Financial comparison excludes retrieval/verification/job IDs, source document
IDs, checksums, locators, publisher/title presentation and decimal spelling.
The immutable event still retains all evidence. Values, units, scale,
classification, metric, entity, period and comparison basis remain meaningful.
Each supported native source establishes one silent initial financial cohort;
later new fact identities and existing-value corrections can each create one
pending human-review draft. A persistent source marker and per-series state
prevent reporting-period/publication-day regression, including a previously
unqualified head becoming qualified. Unknown non-null state schemas and
boolean/float marker substitutions refuse.

Legacy financial cursors are preserved. A historical NULL state can migrate
only using its immutable prior event or an exact match to its old fingerprint.
An old silent baseline with neither proof refuses; it is never deleted or
silently reset. Existing report fingerprints/observations retain their previous
serialization because absent financial bindings are omitted.

A metadata-only refresh creates no automatic draft. It can make an old exact
job witness stale. An explicit reasoned backfill may then create one current
review draft; the prior unsent pending draft is archived with revisions and
events retained. Replay/concurrent hooks use existing transactional source,
cursor/event and post constraints. Failed mutation transactions roll all social
effects back; committed per-record progress and uncertain commits retain the
existing separate telemetry contract.

## Native producer seams

* National annual sector evidence and county pending-bill stock evidence use
  their existing native fetchers, parsers, retained receipts and writers. When
  this financial lane is expressly enabled, a current non-dry job performs a
  fresh parse instead of granting new authority to serialized parse-cache JSON.
  This adds no download or social-side crawler.
* The prospective numeric gate batches existing qualification queries. It runs
  only under the new financial ceiling and never clears an explicit operator
  quarantine. It requires an AVAILABLE source and grants no publication day or
  announcement authority.
* Pending-bills provenance prospectively includes the exact writer context's
  job ID in its existing atomic savepoint. No historical job is relabelled.
  The Grand Total claim preserves the completeness caveat and any assembly,
  publisher-inconsistency or chapter-table warning as part of its scope.
* KRA annual article cells have a deliberately narrow grammar: the reviewed
  achieved annual lead, followed immediately by consecutive explicit achieved
  collection paragraphs. Headings, unknown narrative/nested sections, inline
  styling/hidden content, forecast/subperiod/prior-year qualifiers, multiple
  heads/amounts and malformed thousands grouping cannot grant cell authority.
  The existing best-effort numeric parser remains independent. Unknown genuine
  article layouts remain unsupported for financial drafts.
  Promoted article rows replace stale fixture measurement labels, including
  Customs departmental/agency-levy scope and domestic VAT/excise scope. The
  narrower domestic labels require explicit source wording and qualified cells;
  generic VAT/excise numeric rows retain generic labels and refuse financial drafts.

## Intended-source matrix

The actual nightly legacy set is the 15 entries in
`backend/seeding/registries.py::_BUILTIN_DOMAIN_PACKAGES`. `source_plan.py`
adds county_borrowing, CRA and OpenData only through their existing opt-ins.
An adapter capability does not certify a current eligible production record.

| Domain | Financial notification status / exact remaining boundary |
| --- | --- |
| counties_budget | Existing qualified actual-spending reader retained; semantic comparison repaired. Legacy per-record baseline/identity contract remains; this change does not claim a new county producer rollout. |
| national_budget | New annual sector revised-gross and actual-expenditure adapter. Original retained official PDF/post replay exercises the actual native parser/writer, migrated PG, preview, silent baseline and explicit admin review draft. Other measures/subperiods refuse. |
| revenue_by_source | New qualified annual-article collection adapter; source-shaped local producer tests cover corrections to the same row. Current genuine FY2025/26 catalogue has no full report-publication day; financial qualification is still refused. Dashboard numeric evidence does not inherit wrapper publication authority. Targets, percentages and residuals are outside this financial adapter. |
| pending_bills | New county year-end outstanding-stock adapter. Original retained official county PDF/post replay executes native producer/parser/writer, migrated PG and preview/baseline. National BROP stocks, missing/withheld amounts and aging bands are outside this adapter. #800 owns separate aging lifecycle/adoption. |
| audits | Neutral native report adapter remains. A source-bound exact finding/monetary-cell producer and retained genuine full publication-day authority are missing. `figure_qualification.row_identities` has no audits monetary contract. Finding text/amount arrays, report signatures and upload paths are not substitute authority. |
| economic_indicators | Existing numerical API evidence does not bind an exact successful committed report/job release; no notification adapter. |
| population | Numerical reporting years do not establish a retained full publisher release day; no notification adapter. |
| county_officials | Personnel registry has no reviewed financial/report notification contract; no fabricated monetary content. |
| national_debt | Instrument/stock numeric contracts are separate from full publisher release-day authority; no notification adapter. |
| debt_timeline | Series snapshots lack exact successful report/job lineage for this notification contract. |
| fiscal_summary | Native budget/BROP projections and numerical source references do not provide a complete retained report/job notification contract. |
| learning_hub | Static educational content has no native financial release contract. |
| stalled_projects | Existing CoB edition/month and table evidence do not establish full publisher-day notification authority. |
| national_gdp | Numerical/edition metadata alone does not supply the reviewed retained full-day and exact-job notification contract. |
| imf_weo | Actual/forecast/vintage observations are not a retained report release with exact committed notification lineage. |
| county_borrowing | #801 owns exact issuer/instrument/dated-stock proof. No borrowing adapter is inferred from registration or a facility aggregate. |
| cra | Recommendation scope still lacks retained full publisher-day authority; no financial notification adapter. |
| opendata | Native writer explicitly retains `workbook_publication_date=None` and source-extracted/non-publication-qualified status. A report month cannot fill the missing day. |

The unsupported rows are explicit refusals, not completed required coverage.
Null/withdrawn measures cannot be rendered as zero or as a qualified numerical
claim. Source-specific withdrawal/nonmonetary content requires its own reviewed
contract. This work does not claim every registered ingester can announce data.

## Rollout and overlap

`SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED` is a new literal default-off
ceiling for the prospective numeric gate and automatic native financial hook.
Existing generation controls/source/account selection still apply. Manual
inspection/backfill uses existing authenticated reasoned commands. New financial
categories cannot use unattended policy authority; human review remains required.
No production variable, source admission, workflow state, grant or schema is
changed. Publishing, uploads, automatic approval/scheduling/publication and
native/social workers remain under the existing OFF operating boundary.

#831 owns `native_report_authority.py`, which this patch does not edit. Its
API is consumed unchanged; integrate its query/invalidation repair first.
#841 also changes the national writer: preserve its pre-autoflush lock ordering
and coalesced invalidation when integrating this patch's numeric-gate call.
#800 overlaps only the added financial cache-bypass condition and prospective
job/numeric-gate calls in pending_bills fetcher/writer. The explicit seam/diff
handoff is in the shared B116/802 ledger; reconcile it with #800's lifecycle
changes. No sibling commits were silently adopted. #801 has no shared product
file changes in this lane.

The existing admin UI now uses actual capability responses for financial
inspection, explains physical record IDs, preserves audited reasons and shows
the exact financial record/report authority beside immutable values. It reuses
the existing accessible labelled controls and layout. Coordinated Chrome
qualification, combined merge/deploy acceptance, genuine production jobs,
source-specific backfill approval and any future financial-hook activation
remain coordinator/user gates.

## Evidence location

Owned source-bound receipts, immutable snapshots, raw logs/JUnit, actual
interpreter/optimization/image/dependency identities, both independent executable
review rounds and retained official bytes are outside Git at:

`/Users/roger/.codex/visualizations/2026/10/28/01a18474-91c3-70c0-b65f-0735ebbfe545/b116-802`

The external final TASK-HANDOFF and receipt index bind the final commit/tree and
PR. Earlier failed tests/setup runs and superseded candidate receipts remain
historical. Overlapping cohort counts are not additive. Cached Python3.12 and
Node24 qualification is local compatibility evidence, not a hosted or deployed
acceptance claim. All repository execution is confined to capped offline Docker
with read-only source/toolchain, unprivileged UID, private synthetic PostgreSQL,
no network/credentials/socket, dropped capabilities and no-new-privileges.
