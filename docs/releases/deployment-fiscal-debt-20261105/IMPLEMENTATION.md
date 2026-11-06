# Fiscal and debt publication boundaries

This local repair is based on commit `8ef389d7ffc5bfb86bed22ae5a9b63858f13424a`
and tree `75637cdf82b20fdc8190305638d45ca019c838d0`. It does not authorize a
production data change or deployment.

Debt writers discard supplied ratios and derive a one-decimal, Decimal half-up
ratio only from the independently qualified persisted stock and GDP pair.
An incoming GDP observation cannot certify an old unqualified stock. A new
qualified stock can use a compatible retained GDP observation. Public timeline,
national fallback, sustainability and provenance readers share the same check.
Historical stock with a usable citation remains visible with its qualification;
unavailable or conflicting cells and unsupported units are withheld. Both
reconciliation directions use the public stock value. The frontend preserves
null through headlines, charts, tooltips and annual-change calculations.

The required inventory is fourteen stock years, 2013–2026, and thirteen completed
annual GDP years, 2013–2025. The 2026 annual GDP period has not ended. Its absence
is explicit and cannot hide a missing historical year. Monthly stock dates and
annual denominators are disclosed separately. Unknown publication and vintage
dates remain unknown.

Every nested fiscal-framework measure has its own amount, fiscal year, basis,
vintage, printed precision and source-cell witness. The public projection
requires the source's actual KES 100 million quantum and same-column
reconciliation. It separately withholds invalid optional components. Explicitly
signed cash, financing and statistical adjustments remain supported. Sources
and proofs expose an allowlist of typed metadata. The framework cannot bypass
the guard through fiscal outturns, borrowing ratios, charts or budget readers.
Failed refreshes retain independently qualified last-good measures, including a
qualified nested framework when no top-level measure is retained.

The existing public fiscal-money boundary already rejected matching negative
amount/proof pairs on the supplied baseline. Review comment `4485289483` is
refuted by executed counterexamples; there is no cosmetic sign patch. Comments
`4485289419` and `4485289537` describe confirmed debt and nested-framework paths.
Local reply drafts and red/green evidence are in the lane delivery packet.

`services.fiscal_authority.verify_fiscal_debt_authority` is a read-only semantic
observer for an actual, clean PostgreSQL session and explicit expected periods.
It refuses pending changes, rereads persisted rows and reports the actual
database and role. The registered APDMR adapter checks the retained document,
Extraction, response manifest, observation identity, scaling, locator and
checks. With a configured `receipt_store.read(sha256)` reader, it also replays
the pinned original PDF's native cover and table. Without that reader, the
manifest association is reported separately from original-byte verification.
Missing or contradictory framework/BROP associations remain engineering holds.
The observer always returns `production_accepted=false` and
`source_adoption_authorized=false`.

No database model, migration, shared acceptance tool, workflow, source plan,
refresh policy or ingestion control is changed by this lane.
