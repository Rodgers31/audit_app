# Seven-table qualification contract (Refs #137)

Implemented against main `f9685067ca56fc3ef01d162c6ab4b3a716642b91`, in the isolated `codex/remaining-provenance-contract` checkout. This lane adds reader qualification; it does not adopt production observations, perform historical backfills, establish durable production storage, or close #137.

## Stored interface

`backend/services/figure_qualification.py` owns `ObservationIdentity`, `ReceiptReference`, `EvidenceReceipt`, `ObservationEvidence`, `FigureQualification`, pure `evaluate_qualification`, seven `row_identities` adapters, batch `qualify_rows`, and `qualify_ratio`.

Rows keep their existing quantities and model columns. `meta.source_evidence` or a `provenance` entry's `source_evidence` is a list of version 1 observations. Each carries an exact identity (measure, entity ID, geography, period, unit, basis, dimensions), an Extraction ID/digest reference, raw and normalized values/units, source locator, explicit transformation, checks, and observation reconciliation. Budget dimensions distinguish category, subcategory and line type; loan dimensions distinguish lender and debt category. Amounts and terms are separate measures.

The existing Extraction stores metadata under `extracted_json.response_receipt`, with extractor `http-response-v1` or `pdf-receipt-v1`. It records request URL, response status/type, acquisition time, parser version, SHA256, byte size, storage key and actual retained-object read-back check. Source bytes remain in the ingestion artifact store. A different source document may be referenced explicitly for a denominator.

The receipt also contains a source parser observation manifest: independently parsed identity, raw value/unit and locator. A normalized row, its raw-value assertion, its checked booleans, a URL, a hash or an Extraction ID cannot verify itself. The reader compares the row to the manifest, then validates the explicit transformation. Rounded transformations must match the parser's manifest transformation, including `ROUND_HALF_UP` or `ROUND_HALF_EVEN`. Supported dimensional scales are KES, millions/billions KES and percent/coefficient. Currency conversions without independently checked FX operands remain qualified.

Source parser entity IDs may be NULL because publisher bytes have no database IDs. Geography and the rest of the identity must still match. Terminal county-name suffixes and Nairobi City/Nairobi are normalized for this source comparison only. Loan source periods use explicit measurement month or reporting date, never a bookkeeping issue date as stronger evidence. Source/document country association is checked. Economic CPI and retired inflation guards are evaluated through a batch-loaded context; KRA residual/share withholding is preserved.

Acquisition and registered publisher hosts must match for stronger qualification. Cross-host web embeds remain qualified with `embedded_publisher_chain_not_checked`; retained bytes from an external dashboard alone do not establish its publisher linkage. This preserves the accepted KRA observation while withholding stronger promotion pending an independently retained page-to-dashboard chain. API/PDF publisher association mismatches remain conflicting.

## Response semantics

Every measure qualification includes `status`, `reason`, `source_kind`, `identity`, `source_document_id`, `source_url`, `publisher`, `receipt_id`, `digest`, `locator`, `document_bytes_checked`, and `value_checked`.

- `qualified`: usable historical citation or incomplete stronger evidence; no value verification claim.
- `verified`: matching retained source/parser observation, association, raw transformation, explicit checks and successful receipt.
- `unavailable`: explicit NULL, invalid value, missing source or absent published measure.
- `conflicting`: contradictory identity, digest, values or existing publication refusal.
- `modelled` / `projected`: supported explicit origin/basis. Round monetary values and empty provenance do not establish model origin.

The older verification field remains compatible: `publishable` corresponds to qualified; `unverified` corresponds to unavailable. Existing coherent GDP refusals and reasons remain effective. `record_id` identifies an exact observation; `measure` selects an economic series. Both missing economic and poverty branches now return a stated no-row result rather than Unknown table.

Derived debt and execution ratios require independently qualified operands, matching entity/geography/period/units, and correct arithmetic. A verified amount does not verify a rate, term, partition, per-capita ratio, or separate macroeconomic headline. The national debt summary exposes operand qualifications; its legacy IMF headline is explicitly outside this seven-table receipt contract.

## Modified serializers and current frontend consumers

| Table / serializer | Qualification location | Current consumer |
|---|---|---|
| All seven `/provenance/verify/{table}` | `qualifications[measure]` | `frontend/app/sources/page.tsx` is the source registry; no existing direct verifier fetch was found. Session 4 can link an exact `record_id`. |
| GDP `/economic/gdp`, `/economic/county/{id}`, `/economic/summary` | row `qualifications`; profile `latest_gcp.qualifications`; summary `qualifications.gdp` | No existing direct GDP route consumer found by repository search. County GDP appears through `/counties/{id}` and the national debt denominator. |
| Economic `/economic/indicators`, county profile, summary | row `qualifications`; profile indicator qualifications; summary series qualifications | Macro figures rendered through `/budget/enhanced` by `frontend/components/budget/EconomicContextStrip.tsx` and `frontend/app/budget/BudgetPageClient.tsx`. |
| Poverty `/economic/poverty`, county profile, summary | row `qualifications`; `latest_poverty.qualifications`; summary `qualifications.poverty` | No existing direct poverty route consumer found by repository search. |
| Budget county list/detail/comprehensive | list/detail `figure_qualifications.budget_lines[row_id]`; comprehensive `budget.figure_qualifications[row_id]` | `frontend/lib/api/counties.ts`, `frontend/lib/react-query/useCounties.ts`, county Explorer/compare and `frontend/app/counties/[id]/CountyDetailClient.tsx` / `tabs/BudgetTab.tsx`. |
| County `/counties/{id}/budget` and `/financial` | top budget row map; `financial_summary.figure_qualifications`, reused by financial response | `frontend/lib/api/budget.ts` and county hooks. Source quantities, absence and accounting contract retained. |
| Budget `/entities/{id}`, `/entities/{id}/periods/{period_id}/budget_lines` | recent/item `qualifications` | Generic entity interface; no existing direct budget-lines frontend fetch found. |
| Budget `/budget/enhanced` execution rows | `execution_by_sector[].qualifications` including `execution_rate` | `frontend/components/budget/ExecutionAuditLens.tsx`, `BudgetPageClient.tsx`. |
| Loans `/debt/loans`, `/debt/top-loans` | each loan's `qualifications` | `frontend/lib/api/debt.ts`, `frontend/lib/react-query/useDebt.ts`, `frontend/components/dashboard/NationalLoansCard.tsx`, `frontend/app/debt/DebtPageClient.tsx`. |
| Loans/GDP `/debt/national` | `data.figure_qualifications.loans` and `.gdp_data`; derived headline refusal | National debt overview hook, dashboard debt/hero cards, debt page. Aggregate quantities retained; no generic whole-response verified badge. |
| Debt `/debt/timeline` | each year `qualifications` including independent `gdp_ratio` | `frontend/lib/api/debt.ts`, `useDebt.ts`, `NationalDebtCard.tsx`, `HeroSection.tsx`, `DebtExplainerModal.tsx`, debt page. Session 4 must remove frontend round-number model authority. |
| Revenue `/budget/enhanced` | `revenue_by_source[].sources[].qualifications` | `frontend/components/budget/RevenueMix.tsx`, budget page. Unsupported residual and shares stay NULL. |
| Economic `/budget/enhanced` | `economic_context.qualifications` grouped by series | `EconomicContextStrip.tsx`, budget page. Existing source/period values retained. |

Consumer discovery used `rg` across frontend TS/TSX for actual endpoint strings, hooks and payload field names. This mapping identifies modified serializer outputs; it does not claim frontend integration or browser acceptance has happened.

## Execution receipts and limits

- Initial actual-handler missing-branch regression: 2 failures, both HTTP 400. New handlers return HTTP 200 with `no_rows`.
- New handler/adversarial suite (105 executed cases): seven tables, retained matched zero, missing/invalid identity/value/bytes, archived qualified histories, projections, NULL, source associations, terms, API/PDF distinction, external web embeds, exact county selector and actual chart/verify equivalence. Currency/rate dimensional confusion and extreme ratio precision cannot promote or crash the evaluator.
- Seven forged aligned-row attacks: disabling source manifest binding produced 7 failures; restoring binding produced 7 passes. Commands/results retained in `/tmp/session1-manifest-red.log` during this session.
- Constant-query measurement for 100 national GDP associations: three queries (documents, countries, referenced receipt metadata); no per-row lookup. General adapter uses at most five shared metadata queries. Public readers call no artifact-store or publisher network API.
- Final targeted batch: 543 passed, 143 skipped (optional PostgreSQL parameter cases), with only existing deprecation warnings. The batch includes existing CPI, cash, KRA, pending bills, retired inflation, county quantities and GDP identity regressions. PostgreSQL parameter skips are explicit when the optional isolated PostgreSQL test URL is unconfigured; no production DB is queried.

Remaining gates: independently review the combined producers/readers, exercise real retained parser/writer/read round trips after consolidation, run frontend and browser acceptance, select/accept durable production receipt storage, and satisfy the separate history/hosted criteria. No production-store durability or publisher re-fetch on a public request is claimed.

## Scoped frontend integration bridge

The row serializers `/debt/loans` and `/debt/top-loans` expose `id` and `record_id`, both the persisted Loan ID, for an exact verification link. Aggregate responses acquire no synthetic record ID.

The comprehensive county response adds `economic_profile.latest_gcp` and `economic_profile.latest_poverty`. Each is NULL when no county-scoped fact exists; otherwise it contains the selected persisted row's ID/record ID, entity ID, observation year, source document ID, exact reported numeric fields and their `qualifications`. GCP additionally carries quarter and currency. Selection uses the same year/quarter ordering as `/economic/counties/{entity_id}/profile`, with one bounded latest-row read per table followed by batch receipt metadata reads. Existing comprehensive values and source periods remain unchanged. Entity metadata, national observations and older verified receipts never supply the evidence for a displayed county fact.

Actual handler controls cover real loan IDs, zero balances and NULL rates, exact county periods/identity, zero GDP/poverty, NULL poverty/Gini, absent county facts despite national and metadata values, and a newer unverified/NULL county fact beside an older verified fact. Eleven integration controls plus the original qualification suite and county/economic regression gates: **296 passed**, with three existing deprecation warnings. Frontend/browser acceptance remains a separate lane.
