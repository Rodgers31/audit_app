# Remaining source acceptance — 3 November 2026

Reviewed base: `8f08d85a1b059b83d8b8a3823f5f06fd33eb4e39`, tree
`429c94692890811fcab68668c5ee1ecd19226c5e`. This is a bounded local engineering
checkpoint for #802, #801 and #848. All three acceptance criteria remain unmet.
No production admission, source write, hosted rerun, generation, upload,
provider delivery, worker, merge or deployment is performed by this lane.

## Repaired dispatch contract

A record reader returning `None`, `False`, `0`, an empty string or an empty
mapping previously became `completed / no_new_record_lineage`. The dispatcher
had measured no valid cohort. The independent review and root reproduction
executed that branch with injected reader results and inert telemetry; they do
not establish that an installed reader or a production job emitted those values.

`generation_capabilities.validate_record_ids` now requires a list or tuple of
at most 1,000 unique, exact integer IDs in `1..2147483647`. Both financial and
report dispatch validate before interpreting an empty result or invoking the
generation hook. Invalid results produce the existing failed source-read outcome
with zero effects because the hook was not invoked. Explicit empty lists/tuples
remain successful no-ops. Valid cohorts retain their order and are frozen as a
tuple. This neither changes adapter availability nor grants source authority.

The regression covers all four financial and five report dispatch paths:
144 invalid-cohort cases failed before the fix while 45 valid/empty controls
passed. The repaired complete local selection passes 331 cases in each of
normal Python and `python -O`, including existing semantic-change and replay
controls. These are network-denied fixture/double checks, with no PostgreSQL,
current production or genuine source-to-database acceptance claim. The two
independent executable reviews and final replay receipts are in the external
evidence directory below; exact source/log/JUnit hashes accompany them.

## Adapter inventory and authority still required

The registry has 18 domains, five report adapters and four financial adapters.
The runtime inventory is retained as `INVENTORY.json` at the reviewed base;
the capability table is unchanged by this repair. Every supported record still
requires exact successful live-job lineage, current source authority, retained
original bytes/receipts and compatible identity/scope. Numerical claims also
require verified measure-specific cells from those same source bytes.

| Domain | Report adapter | Financial adapter | Accepted contract boundary; remaining source acceptance |
| --- | --- | --- | --- |
| counties_budget | Yes | Yes | Existing CoB county actual-spending/report contract; no new cohort or rollout claimed here. |
| national_budget | Yes | Yes | CoB annual sector revised-gross/actual cells, full publisher day and exact current job; other measures/subperiods refuse. Historical job3579 qualified ten rows/twenty cells; this lane did not refresh its current authority. |
| pending_bills | Yes | Yes | CoB county year-end Grand Total stock with qualifications; national BROP stocks and aging bands are outside this financial adapter. Accepted #800/#849 cohorts are not repeated. |
| revenue_by_source | Yes | Yes | Qualified annual achieved-collection article cells require a full report publication day. Current FY2025/26 dashboard/catalogue evidence cannot qualify financial drafts. |
| audits | Yes | No | Narrow OAG combined-volume catalogue availability, separate executive/assembly series; `catalogued_on` does not become `published_on`. No audit financial adapter. Acquisition/replay remains unaccepted. |

Thirteen domains explicitly refuse both adapter types. These are missing
notification contracts, not a declaration that the underlying numerical API
data is false or that all fields must be absent.

| Domain | Registry reason | Contract needed before any new adapter |
| --- | --- | --- |
| economic_indicators | `report_lineage_unavailable` | Exact native release/record/current successful job lineage. |
| population | `report_date_authority_unavailable` | Retained full publisher release day with population/period scope. |
| county_officials | `report_contract_unavailable` | Reviewed personnel/report announcement identity, scope and authority. |
| national_debt | `report_date_authority_unavailable` | Retained full release-day authority distinct from instrument/stock dates. |
| debt_timeline | `report_lineage_unavailable` | Exact report release and committed observation/job lineage. |
| fiscal_summary | `report_lineage_unavailable` | Retained report/period/measure lineage, beyond projections and references. |
| learning_hub | `report_contract_unavailable` | A reviewed notification contract for static educational content. |
| stalled_projects | `report_date_authority_unavailable` | Full publisher-day authority beyond edition/month/table evidence. |
| national_gdp | `report_date_authority_unavailable` | Reviewed retained release day and exact native job/period. |
| imf_weo | `report_lineage_unavailable` | Exact report/vintage/job lineage preserving actual/forecast distinctions. |
| county_borrowing | `report_date_authority_unavailable` | Defensible issued instrument identity and dated actual stock; #801. |
| cra | `recommendation_date_authority_unavailable` | Retained full recommendation release-day and scope authority. |
| opendata | `source_extracted_not_publication_qualified` | Genuine workbook publication authority; its null day cannot be replaced by a month or retrieval time. |

These remain held. A registered ingester, successful seed counter, catalogue
entry or fixture labelled `source_mode=live` is insufficient. No generic
fallback adapter, automatic source admission or source date is introduced.

## OAG acquisition/replay frontier

The exact existing packet is
[`2026-11-01-oag-catalogue-acceptance/manifest.json`](../2026-11-01-oag-catalogue-acceptance/manifest.json):
four reviewed FY2022/23 and FY2023/24 executive/assembly volumes. The rule remains
[`ADR0003`](../../adr/0003-oag-combined-catalogue-availability.md).

The supplied historical release record documents genuine failed acquisition
[run41325028482](https://github.com/Rodgers31/audit_app/actions/runs/41325028482),
job3585: an official PDF URL returned HTTP200 HTML, zero processed/created/updated
and no native report records. Its second hosted replay was withheld. The earlier
broad job3581 completed with errors and also supplied no native authority.
The subsequent Blue Book335-retirement warning belongs to the separate nightly
reconciliation lane; it is not recovery evidence for the four-PDF packet.

Remaining proof requires legitimate original HTTP200 PDF acquisition matching
each pinned artifact, current exact RSS catalogue/cover scope, successful native
job/report records and scope-specific current heads. A separately authorized
replay must keep semantic findings/amounts unchanged and create no duplicate
drafts. Cached bytes alone cannot bootstrap original HTTP authority. This lane
ran no additional acquisition, hosted check or production query. The existing
packet is a selection contract, not an authorization or an execution receipt.

## KRA and Nandi bounded research

Eight official HTML GETs were retained with TLS verification, no redirects or
retries, and a one-MiB cap per page. All returned200, totalling939,175 body bytes.
This is research, not a native producer execution or financial admission.

The current [KRA FY2025/26 wrapper](https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026)
still embeds the external dashboard. This lane acquired no dashboard bundle or
new financial source. The existing source comparison fixture records conflicting
exact dashboard/PDF values and no report publication day; a catalogue date or
unrelated press-release date cannot resolve either issue. The present first
[press-listing page](https://www.kra.go.ke/news-center/press-release) was also
retained; its unrelated dated entries are not annual-report authority.

The [Nandi service catalogue](https://nandi.go.ke/features-categories/services-and-vision/)
exposes more recent Q1/Q2 FY2025/26 links than the general downloads page. The
Q2 wrapper names that subperiod and shows create/update23April2026. The
[pending-bills wrapper](https://nandi.go.ke/download/pending-bills-action-plan-2025-2026/)
still titles its sheet FY2024/25, with create8August2025/update16April2026.
The [FY2026/27 ADP wrapper](https://nandi.go.ke/download/nandi-county-annual-development-plan-cadp-fy-2026-2027/)
shows create10September2025; its plan-year title cannot certify a later actual
stock date. The checked CBROP wrapper identifies2024. Wrapper metadata is not
financial reporting-date evidence. No additional PDF was downloaded.

This finite sample qualified no complete Nandi30June2026 stock return; it is
not an exhaustive archive search or proof no such return exists. The retained
historical1July2025 sheet stays distinct. No old, partial, executive-only or
assembly-missing return may fill the common CoB June2026 total. A future source
needs its own native date/population/measure/coverage contract, retained original
receipts, conflict handling and source→job→DB→API→UI reconciliation. #848 remains
open; partial reported sums remain partial.

## Borrowing evidence and owner inputs

The two unchanged reviewed editions have zero qualified instruments. Their
separate source reporting/scope-review dates are2025-06-30/2026-10-25 for the
Treasury guarantee register and2024-06-30/2026-10-25 for the OAG Kisii finding.
Neither establishes a defensible instrument-stock mapping. Existing facility
accounts remain a separate unimplemented measure proposal under
[`county_borrowing-handoff.md`](../../admin/batch86/county_borrowing-handoff.md)
and [`ADR0001`](../../adr/0001-county-debt-instrument-observations.md).

No new borrowing PDF search, instrument mapping, source edition or balance was
introduced here. Balances stay unavailable rather than zero. Progress requires
official evidence of county/issuer/explicit contract reference, actual issuance,
stock date, currency/unit/basis and outstanding amount with page/table lineage,
or explicit owner agreement on a separately reviewed facility-account measure.
Guarantees/proposals, lending assets, pending bills and repayment arrears cannot
be substituted for borrowing stock. #801 remains open.

The next owner/coordinator input is the compatible nightly/transport repair
identity before integrated acceptance and a separately scoped decision on any
future genuine acquisition/rollout. This PR requests neither a hosted rerun nor
activation. The parent exclusively owns release, production validation/pin and
saved Meta checks. Financial generation, native/automatic source admission,
publishing, uploads and workers remain held; production OFF-state was not
re-observed by this lane. Accepted #831/#800/#849 scope is preserved.

## Evidence location and limits

Worktree: `/Users/roger/.codex/worktrees/source-acceptance-20261103/audit_app`;
branch `codex/source-acceptance-20261103`. Owned source files are the capability
registry module, generation dispatcher and the new cohort regression. No audits
parser, issuer transport, global HTTP client, financial source interpreter or
workflow was edited.

External evidence:
`/Users/roger/.codex/visualizations/2026/11/03/01a1a1aa-6eaa-7170-9bb2-f4519053ccd0/source-acceptance-20261103/`.
`OWNERSHIP.md`, `INVENTORY.json`, `public-inventory/receipt.json`, root red/green
raw output/JUnit/source manifests and both review directories preserve their
original producers. Initial harness import failures are retained separately:
in-memory SQLite pool incompatibility, missing JWT under full conftest and
missing sibling helper import paths. No install was performed. The successful
selection uses the existing Python3.13 runtime with `--noconftest`, declared
test helper paths and OS-enforced network denial. It does not substitute for
the full application gate, PostgreSQL integration or deployed acceptance.
