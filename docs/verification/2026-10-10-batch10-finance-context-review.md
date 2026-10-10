# Batch 10 financial source-context re-review (#591)

The old complete main.py AST pin `a1feee54730bad33f8b69712d2ba210ddfd7e2d1a6ee718bf03c97a81b60eac1`
correctly refuses the changed PR604 module. This review covers the exact source
in `6db43b4a806f7006f7b14631f6f01bff7f5b3db7`, SHA256
`a40bca0006ea6d8942fc8967cddcb9a0e199226716f5cf7e9a90a595b6fdd235`,
and binds the new portable whole-module AST
`5cb0b69964a08ce4dbbd280abdf4f08382d2cc86d6a2d1ac074e6de9413ce4ab`.
The prior 672c5c source SHA256 is
`dbac56fe5b9c2300cf6946a65021e24b292da429bacf11cc6a45b1c52e12c82a`.
The old inventory and verifier/test bytes are retained unchanged under
`docs/admin/implementation/batch10-readiness-evidence/history/hosted-2026-10-10/`.
The October 9 review remains historical; its then-existing all-projection helper
observation describes that source, not the repaired helper.

## Each contextual site and every direct financial caller

* `_MAX_COUNTY_BUDGET_KES=50000000000` at main.py:304 still has no Name load
  anywhere in the module or runtime references elsewhere in production source.
  It cannot presently clamp, fill or publish a county observation.
* `_PENDING_BILLS_SEVERE_SHARE=25.0` at :992 is still used only to scale the
  disclosed pending-bills score and describe that calibration at :1109/:1115.
  The observed share remains `pending_bills / total_allocated * 100`, not the
  threshold. `county_financial_health` and all three callers (`get_counties`,
  `get_county_details`, `get_county_comprehensive`) have identical ASTs to the
  prior review: row-derived amounts, compatible fiscal period/currency and
  missing inputs remain preserved. The threshold supplies no reported bill.
* `_budget_overview_meta`'s `1800` at :8978 remains a cache duration.
  `_response_meta` and `get_budget_overview` have identical ASTs. Returned
  financial totals remain aggregates of published row inputs; metadata duration
  never replaces a total, category allocation or fiscal history value.
* `anchor_pct_gdp=55.0` at :9701 remains explicitly stated policy context.
  It does not supply the measured debt ratio. `get_fiscal_summary` now consumes
  only finite, explicitly nonprojection Kenya observations from the newest
  selected WEO vintage, and returns that vintage/source or an absence reason.
  `above_anchor=None` and the incomparable present-value/nominal basis disclosure
  remain. This source review does not independently validate the legal statement.

## Changed use contexts, publication and fallback

The complete AST delta comprises lifecycle/readiness helpers and health,
`get_fiscal_summary`, `_latest_imf_debt_to_gdp`, `_imf_observations_available`,
`get_national_debt`, `get_debt_sustainability`, `get_debt_broader` and
`_published_debt_projections`. No raw numeric detector site or signature changed.

The headline helper no longer substitutes a projection-only vintage or an older
vintage; malformed flags and nonfinite values preserve absence. Fiscal summary,
national debt and sustainability use that same helper. National debt's separate
CBK/World Bank computation requires finite positive GDP and a finite quotient;
it preserves its distinct basis/year/source or nulls and an absence reason.
Sustainability's finite CBK timeline fallback stays separately labeled. Neither
fallback takes its value from the 55 policy anchor, unused county bound or TTL.
Existing projection series remain explicitly projections; broader debt retains
its separately declared legacy forecast fallback, which this pin does not
reclassify as the actual-only headline contract. Catalog absence is checked
before optional IMF reads so partially seeded PostgreSQL transactions remain
usable; catalog failure remains an error rather than a made-up value.

## Executed gates and scope

The original main pin fails on current and minimum runtimes; its old source
passes. Existing controls execute the actual raw detector and whole-module guard
on all four main-site misuse mutations, plus config/producer mutations: new
callers, a calibration replacing observation, TTL replacing money, and nominal
ratio compared with the policy anchor all remain refused. Exact literals,
suppression rules, traversal, signatures, dispositions and unrelated pins remain
unchanged. Runtime controls cover actual financial-health calculations, mixed-unit
metadata, sourced county pending bills and IMF fiscal/national/sustainability
publication, invalid values, honest absence and preserved projections using inert
transports and disposable local fixture databases.

Execution receipts and exact inventories are external in the coordinator's
`BATCH_10_MERGE/604/HOSTED_REPAIR` packet. This document and a refreshed pin alone
are not a passing hosted run. The failed f75 run is diagnostic; fresh complete
hosted acceptance is still required. #583, #602 and #603 remain pending.
