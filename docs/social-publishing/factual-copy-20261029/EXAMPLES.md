# Financial copy examples

These are read-only typed copy fixtures. The Nairobi amount comes from the earlier review reference; the Health and KRA values are synthetic. All IDs and checksums are synthetic. Every observation is uncommitted, marked as a fixture and not publishable. No source acquisition or production draft was created. Actual source qualification and draft controls are exercised separately in PostgreSQL.

## Pending Bills

Legacy factual-v1:

```text
Nairobi County pending bills data.
Nairobi County — Reported pending bills: county, FY 2025/26: 86899380000.00 units KES (actual; publisher-reported Grand Total stock as at 2026-06-30; completeness is not assumed).
```

New financial-v2:

```text
Nairobi County: KSh 86,899,380,000 in reported pending bills as at 30 June 2026.

This is the report’s Grand Total. Completeness is not established by this figure.

Source: Office of the Controller of Budget, FY 2025/26.

Explore the figures and original source on AuditGava.
```

## National Budget

Legacy factual-v1:

```text
Kenya national budget data.
Kenya — Actual expenditure: Health, FY 2025/26: 1200000000.00 units KES (actual; actual expenditure, same sector and annual reporting period).
Kenya — Revised gross budget: Health, FY 2025/26: 1500000000.00 units KES (actual; revised gross budget, same sector and annual reporting period).
```

New financial-v2:

```text
Kenya: KSh 1,200,000,000 in actual expenditure for Health in FY 2025/26.

The revised gross budget for the same sector and reporting year was KSh 1,500,000,000.

Source: Office of the Controller of Budget, FY 2025/26.

Explore the figures and original source on AuditGava.
```

## Revenue By Source

Legacy factual-v1:

```text
Kenya revenue by source data.
Kenya — Revenue collected: Customs departmental collections, including agency levies, FY 2025/26: 800.25 billions KES (actual; published collections on the same revenue-head basis and annual reporting period).
```

New financial-v2:

```text
Kenya, FY 2025/26: KSh 800.25 billion reported for Customs departmental collections, including agency levies.

Source: Kenya Revenue Authority, FY 2025/26.

Explore the figures and original source on AuditGava.
```
