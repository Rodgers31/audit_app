# Sourced zero values: implementation receipt

Implementation commit: `e1564ece19af2d6f1e9f867974e5c2e725c58adf` on `codex/preserve-sourced-zero-values`, based on `a7faedb509b63e8ac68557bf90456cb6f2828629`. Issues: #352, #358, #346.

## Behavior

- County, national, and batch money-flow now retain a numeric zero from `SUM(Audit.amount)` when a finding passes the existing publication criterion. No rows, null amounts, and an uncited zero remain unavailable. The Flagged stage, its `data_unavailable` flag, and `total_waste_estimate` agree. See `backend/routers/money_flow.py:340`, `:535`, `:686`.
- The federal response uses `findings_with_amount > 0` to decide whether its finding sum is available. A stored or parsed zero counts as a recorded amount. Absent and malformed amounts still yield a null sum and `no_amounts_recorded` when nothing is withheld. The OAG's own `total_amount_questioned` stays null with `not_extracted`; the finding sum is still identified as a partial, coverage-stated measure. See `backend/main.py:5361` and `:5533`.
- Debt timeline serialization retains explicit zero GDP and GDP ratio values. Its adjacent `reconciliation.primary_value_kes` also retains a stored zero total. Null GDP and GDP ratio remain null. See `backend/main.py:9069` and `:9120`.

## Red and green evidence

All commands ran from the assigned managed checkout, with `PYTHON_DOTENV_DISABLED=1`, `DATABASE_URL=sqlite:////tmp/auditgava-sourced-zero-fixture.sqlite`, empty `REDIS_URL`, `TESTING=true`, `AUTO_SEEDER_ENABLED=false`, and `AUTO_WARMUP_ENABLED=false`, using `/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python`. The HTTP tests use the shared isolated in-memory SQLite session and synthetic `example.invalid` source documents. They did not access a production database or fetch an external document.

1. Before the fix, `python -m pytest backend/tests/test_sourced_zero_api_values.py -q` produced **5 failed, 16 passed**. The failures were sourced zero at county, national, and batch money-flow; all-zero federal findings; and zero debt GDP/GDP ratio. In each case the response supplied `null` where the fixture expected `0`.
2. Before changing the adjacent reconciliation expression, `python -m pytest backend/tests/test_sourced_zero_api_values.py::test_debt_timeline_reconciliation_keeps_recorded_zero_total -q` produced **1 failed**: timeline `total` was `0`, but `reconciliation.primary_value_kes` was `null`.
3. After the fix, the focused command below produced **97 passed, 3 dependency deprecation warnings in 1.46s**:

   ```sh
   python -m pytest \
     backend/tests/test_sourced_zero_api_values.py \
     backend/tests/test_money_flow.py \
     backend/tests/test_money_flow_stage_provenance.py \
     backend/tests/test_money_flow_publisher_attribution.py \
     backend/tests/test_federal_audits_top_findings.py \
     backend/tests/test_federal_empty_state.py \
     backend/tests/test_audit_questioned_amount.py \
     backend/tests/test_debt_timeline_source_is_the_cited_row.py -q
   ```

The new matrix covers absent, null, zero, positive, mixed, malformed and uncited inputs. Zero cases also repeat cached requests. `git diff --check` and `git show --check --oneline e1564ec` passed.

## Boundaries and acceptance

The tests establish API behavior for local synthetic records, not that any live published row contains zero. No live rows, source PDFs, production configuration, or deployment were checked or changed. The coordinator should verify the combined branch, deploy it, then inspect any affected public record against its report before closing the issues. Source eligibility remains the existing URL/page criterion; the fixture's `example.invalid` URL deliberately makes no claim of real-world document verification.

Frontend inspection found null-safe zero rendering at `frontend/components/dashboard/AuditReportsSection.tsx:409`, `NationalDebtCard.tsx:163` and `:362`, and `HeroSection.tsx:131`; the audit partial label supplies `KES` in `frontend/lib/i18n/messages.ts:281`. No frontend edit was needed. This checkout has no `frontend/node_modules`, so frontend tests were not executed here.

## Additional finding for coordinator triage

**Federal finding link can be absent despite a document URL (code-level candidate; live occurrence unmeasured).** A synthetic finding with a nonempty `SourceDocument.url`, valid `page_ref`, and provenance containing only `amount_involved` passes `publishable_audit_criterion()` (the new federal tests establish publication for that fixture), while `backend/main.py:5381` builds the response's `source_url` only from `provenance[0].source_url`. That field is absent in this fixture, so the API cannot give the reader the document link even though its database source is present. Impact: an otherwise published finding may lack a usable citation link. #137 tracks the wider provenance chain; #359 addresses county citation presentation specifically. The coordinator should reproduce the HTTP field and check for existing federal coverage before filing or assigning a fix, preserving the projected-query performance work.
