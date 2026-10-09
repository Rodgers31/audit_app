# Current financial-literal source-context review (#591)

This review accepts exact current source contexts, preserving the raw detector,
existing site signatures and dispositions, and all unresolved finance disclosures.
It does not certify that every finance source in the repository is complete or
that a policy threshold is an independently verified legal requirement.

All three reviewed modules have identical bytes in actual main
`672c5c011ce57dc41551f5fbc642bc4e69134c43` and tested combined tree
`90794acf1fb241020b78fcda4b6c810408872718`. The latter is tree-equivalent to
the actual prospective main+584 merge, not a descendant of actual main.

| Module | Prior exact reviewed context | Current source SHA256 | Current portable AST SHA256 |
| --- | --- | --- | --- |
| `backend/main.py` | `2d24aab2eb4ff65f68be9d1d5501f3fbdfe08887` | `dbac56fe5b9c2300cf6946a65021e24b292da429bacf11cc6a45b1c52e12c82a` | `a1feee54730bad33f8b69712d2ba210ddfd7e2d1a6ee718bf03c97a81b60eac1` |
| `backend/seeding/config.py` | `355c057a6138ed47212a5aab865f4bdf26a02177` | `ecc99f91c6d7015c0bace8bb9c92bf27390f8617f4935a06d7ee6c3debb7cb72` | `6805dc66af8d2a0a15eab20d9dddd4bb383f6d77a276da3974eff3c38c41855d` |
| `backend/scripts/r2_producer_acceptance.py` | new exact contextual entry | `9124c3c8abad7b48c8ed78d580c01012662174fd1ca4b5bdd148cc0250a1478f` | `314708e335750c7f61f9db185e5f342f051e1e8c0e717d223c1dc90ecd67738a` |

An independent read-only source reviewer inspected every main/config delta
since the matching pins, all raw sites and their callers, and the producer's
row-count/publication path. The coordinator inspected the relevant source and
retained executable drift controls. No application startup, real database,
publisher or financial writer was executed for this source-context review.

## Existing contextual sites

- `_MAX_COUNTY_BUDGET_KES=50000000000`: no runtime load beyond its definition.
  This unused private bound cannot currently clamp or publish a county amount.
- `_PENDING_BILLS_SEVERE_SHARE=25.0`: the two loads scale the score and disclose
  its chosen calibration. Observed share remains pending bills divided by
  supplied budget. Three callers preserve missing inputs and require compatible
  period/currency; none substitutes the threshold for observed bills or share.
- `_budget_overview_meta`'s `1800`: only `cache_ttl_seconds`, returned as duration
  metadata. Financial totals still use database aggregates; failures raise HTTP
  errors rather than filling monetary values with a TTL.
- `anchor_pct_gdp=55.0`: stated policy context. Ratio is separately sourced from
  database IMF observations, with absence preserved. `above_anchor=None` and
  the explicit incomparable-basis reason remain. This review does not certify
  the legislative statement or equate nominal ratio with present-value policy.
- `audits_county_start_budget_seconds=240`: four runtime consumers in audits
  `run` disclose scheduling metadata or compare elapsed monotonic seconds for
  national discovery, county-volume and older-document admission. Deferrals
  report processing state; the threshold never supplies an audit amount.

Main's changes since its exact pin concern opt-in telemetry and audit query
projection/status/pagination. Full ASTs of `county_financial_health`,
`_response_meta`, `get_budget_overview`, `get_fiscal_summary`, `get_counties`,
`get_county_comprehensive` and `_latest_imf_debt_to_gdp` remain identical.
`get_county_details` changed audit query/text projection, preserving financial
helper operands. Config's changes add receipt settings and limit validators.
Audit source/observation changes preserve the same admission comparisons.

## New producer diagnostic

`sqlite_budget_rows:468` is a checked retained-source acceptance row count.
Parsing/persistence must return 468 records without errors/skips, with
`stats.created == len(records)`. The actual disposable SQLite BudgetLine count
must also be 468; extraction count and independently assembled qualification
results must match. The actual county endpoint is called with the disposable
session and must equal the row-derived expected public contract. Only then is
the count returned into the producer's acceptance report.

Financial public amounts derive from row fields/sums with missing values
preserved. Neither the report count nor the producer's caller supplies monetary
data. The real producer consumes retained PDF records; unit fixtures can use
explicitly synthetic records. This distinction remains part of acceptance.
The new entry preserves its raw finding and binds the entire exact module to
this context. Any future source/caller change needs another review.

## Retained drift controls and limits

The existing baseline guard fails two stale module pins and the unreviewed
producer site. New controls execute the unchanged detector on actual source:
three positive reviewed contexts and ten mutations. Seven mutations retain raw
numeric signatures yet change use/callers or remove the SQL count check; the
whole-module guard must refuse. Monetary replacement and row-count change must
refuse. An added suppression preserves AST context but changes raw signatures
and must refuse through the signature guard.

The initial new-control attempt precedes the inventory update: its five producer
mutation errors reflect the absent new entry, and are not five product defects.
Baseline full-suite failures remain separately retained. Final current/minimum
Python guard results and the frozen full hosted result belong in the coordinator
acceptance packet; this document alone is not a successful hosted verdict.

The IMF helper currently uses `(actuals or usable)[-1]`; an all-projection vintage
can return a database projection despite its actual-only docstring. Comparison
with the policy anchor remains withheld. This broader discrepancy is separate
from the contextual disposition and requires deduplicated issue accounting;
this review must not describe the returned ratio as guaranteed nonprojection.

The #586 workflow source-pin change does not alter these producer bytes. Future
producer edits require substantive review of the final source before any new
inventory pin. Detector, scan roots, suppression policy, and unrelated inventory
entries remain unchanged.
