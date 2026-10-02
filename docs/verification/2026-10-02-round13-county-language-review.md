# Round13 county cash language supplement — 2 October 2026

Pending competent human review under [#307](https://github.com/Rodgers31/audit_app/issues/307),
with the broader glossary queue in [#372](https://github.com/Rodgers31/audit_app/issues/372).
These draft Swahili strings have no competent human approval. Catalog/rendering
tests establish availability and behavior, not fluency or legal/accounting accuracy.

Source implementation: #440, worker434906766eabb61c982a9e1b99e8e83208c02033,
frontend/lib/i18n/messages.ts. Both OverviewTab and FinancialOverview consume
countyRevenueNotes. Existing cash/summary/zero strings remain in the
[earlier language packet](2026-10-01-round11-glossary-language-review.md).

| Catalog key | English | Plain English | Draft Swahili |
| --- | --- | --- | --- |
| county.revenue.total_unavailable | Total cash receipts unavailable. | The total money received is unavailable. | Jumla ya fedha zilizopokelewa haipatikani. |
| county.revenue.streams_conflict | Cash receipt streams do not reconcile to the printed total. | The amounts received do not add up to the total in the report. | Vipengele vya fedha zilizopokelewa havilingani na jumla iliyochapishwa. |
| county.revenue.subtotals_ambiguous | Cash receipt subtotals are ambiguous. | The report has conflicting subtotals for money received. | Jumla ndogo za fedha zilizopokelewa haziko wazi. |
| county.revenue.missing_cell | A required cash receipt cell is missing. | An amount needed to check the total is missing from the report. | Kisanduku kinachohitajika cha fedha zilizopokelewa hakina taarifa. |
| county.revenue.no_reconciled_table | No reconciled cash receipt table is available. | There is no table of money received with a total we can check. | Hakuna jedwali la fedha zilizopokelewa ambalo jumla zake zimethibitishwa. |
| county.revenue.refusal_source | {publisher}, PDF pages {pages} | {publisher}, pages {pages} in the PDF | {publisher}, kurasa za PDF {pages} |

Review constraints:

- Preserve unavailable versus measured zero. Missing/refused cash never means no money was received.
- Preserve receipt streams, subtotal ambiguity and missing amount as distinct reasons; no claim of fraud, theft, loss or OAG adverse opinion.
- Reconciled arithmetic is separate from independent audit verification.
- The total includes opening balance when the cash table is accepted. Preserve cash versus accrual/summary measure distinctions.
- Keep {publisher} and {pages} placeholders unchanged. PDF page numbering is separate from printed report pages.
- Do not translate source names into a different institution or describe a cash refusal as a budget amount refusal.

| Reviewer | Review date | Accepted keys / precise corrections | Evidence |
| --- | --- | --- | --- |
| Pending competent human | Pending | All six keys pending | No sign-off supplied |

No reviewer has been contacted by the coordinator. Record actual human feedback
and ship resulting corrections with rendered language-switch checks before closing
the competent-review issue.
