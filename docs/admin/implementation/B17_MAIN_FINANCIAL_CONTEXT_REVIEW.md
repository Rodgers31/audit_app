# Main financial context review for #742

Reviewed source: PR #743 candidate `4260a42aaed54012b1ad42dc450d2fde817866ae`; `backend/main.py` SHA256 `71a3c6e91a873e74e1b1331f389be99fbb7d2da4e6579882bb4689e55bcf35c1`. Normalized whole-module AST is `b9a5f0cdcf9bed49b53fd8a94389b6d2b95af1ec1fe7e4630d165ff4f6cf9b0a`.

The exact previous reviewed candidate is `44a6c8b31e734cdc6d3a4eafbdfff4aa195fbdc6`, source SHA256 `12ef1349f1a69e9e117c4fdf45fce0bcf3d8414efdaf5baa6035df4c2e492bf4`, matching the old AST pin `094e1f9bd9d4563599fdc817d67207e8a73c284ead660f7a03e9ad826e666182`. The earlier bcb5ff baseline named in the inventory is not that final reviewed candidate.

## Complete context delta

All 184 top-level function/class ASTs were compared. 183 are unchanged; only `_app_lifespan` changes. There are no added or removed definitions. Eleven added module-level statements configure/include Studio, analytics and privacy components. `_app_lifespan` wraps the existing startup/shutdown sequence in the installed native runtime context using the shared engine. `_startup_sequence`, admission deferral, readiness, cancellation and autoseeder shutdown already existed in the reviewed candidate and remain unchanged.

Review followed the new imports into native startup, configuration, rendering facts, analytics and privacy assembly. Disabled defaults do not register a provider or start a worker; incomplete opt-ins refuse. Editorial Studio fact text is bound to source identity/attestation, not independently numerically validated by this review. Neither imported modules nor the wider financial backlog receive a financial correctness attestation from this pin.

## Four retained raw findings and publication paths

| Raw site | Reviewed use and boundary |
| --- | --- |
| `_MAX_COUNTY_BUDGET_KES`, 50,000,000,000 | Unused private definition; no Name-load consumer in the complete module and no production consumer found in the checkout. No reported observation is supplied by this value. |
| `_PENDING_BILLS_SEVERE_SHARE`, 25.0 | Disclosed policy calibration for the county financial-health score. Its only two loads apply the component threshold and expose its basis. County list/detail/comprehensive callers retain observed liabilities and shares; missing inputs contribute no score component. |
| `_budget_overview_meta`, 1800 | `cache_ttl_seconds` in response metadata. Actual overview execution preserves sourced KES totals, section unit labels and query-error behavior. It is not substituted for a budget amount. |
| `anchor_pct_gdp`, 55.0 | Declared policy threshold in fiscal summary. Observed ratios remain sourced through `_latest_imf_debt_to_gdp`; `above_anchor` stays null with an explicit explanation because nominal IMF debt ratios are incomparable with the present-value anchor. Projection-only, missing and incompatible-vintage cases retain absence, rather than substituting an older actual. Inherited legal wording was not revalidated as a current legal claim. |

Thirteen financial definitions/helpers and their callers are unchanged from the exact reviewed candidate. Existing fallback/projection labels, optional-table handling, qualification and unresolved-finance disclosures remain intact. This does not attest that all historical financial data is qualified.

## Narrow binding change and executable review

Only the main inventory entry's whole-module AST and four review pointers change. The four raw signatures, reasons, dispositions, tracking links and every other inventory entry remain identical. The detector, AST normalization, traversal, positive tests and hostile mutation controls are unchanged. This is a substantive context review, not a signature exemption or a weakened guard.

Independent Standards controls executed 17 cases in each mode; independent Spec controls executed 36 in each mode on Python 3.13. Both used the real guard with pytest assertion rewriting, a live positive candidate and hostile caller/value/publication/fallback/projection/suppression changes. Actual health/meta/default-off lifecycle behavior ran with isolated state and no provider effects. The stale pin refused before refresh. Python 3.12 and final-source acceptance results are recorded separately in the final handoff; pending checks must not be inferred as passes from this document.

Exact source inventories, previous candidate comparison, per-case results, helper hashes and separate reviewer reports are retained in `FULL_PLAN_COMPLETION_B17/opendata/financial-context-review-742-20261018`. The earlier workbook evidence remains immutable. #621/#602 remain open for parent acceptance. No deployment, production migration, activation, paid review or new service is part of this review.
