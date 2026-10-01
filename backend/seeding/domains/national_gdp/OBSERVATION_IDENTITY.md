# National economic observation authority

The World Bank GDP current-LCU series and national poverty/Gini series (including
the existing World Bank GDP fallback fixture) authorize values for their observed
Kenya calendar years. Numeric equality does not establish observation identity.

The writer may create an annual national observation, fill an unclaimed citation,
or refresh a row already citing its coherent source document. It reconciles the
value, source FK, supported metadata and confidence independently. GDP is raw KES;
poverty headcount is percent and Gini is 0–1. Values are rounded to the persisted
column precision before comparison. Missing poverty measures remain NULL; printed
zero remains zero. The unsupported national food-poverty measure remains absent
with the existing explicit reason.

An existing contradictory citation, country/scope/period/measure/unit declaration,
GDP currency, modelled/projected basis, PDF locator, malformed metadata or duplicate
annual observation refuses the entire domain savepoint. Declared source coverage
must include the observation year, and a declared ISO publication date cannot
predate that year. Observation vintage declarations must agree with the source;
undeclared vintage stays undeclared. Identity reconciliation preserves extra coherent metadata, publication flags and
source documents. Entity-linked and quarterly GDP stay outside the annual writer. It does not infer a
publication date from a series' latest observed year.

A numeric difference is not permission to relabel historical evidence. Correction
of a contradictory historical record requires a separate source-supported review
and explicit authorization. No automatic correction switch or backfill is added.
Synthetic tests explicitly correct their own fixture before retrying.

GDP and poverty fetches are independent checks. A poverty request/parse failure
reports `Poverty fetch failed` in the domain and ingestion-job errors, preserves
every last-valid poverty row, and permits valid GDP progress. It makes the combined
source mode partial when GDP is live; GDP fixture provenance remains fixture. Both
fetches failing or a domain write refusal records refused. A later successful
check clears the prior attempt's failure. The newest incomplete GDP/poverty check
warns even when an older run reached the publisher.

Per-check `gdp_source` and `poverty_source` receipts describe the source attempt,
not publication acceptance or an inferred edition. Poverty observations may be
sparse: a missing supported measure remains NULL, a sourced zero remains zero,
and a coherent empty response is a successful source check that changes/prunes
no poverty rows. No annual poverty completeness floor is inferred. Dry-run jobs
retain the same source/error verdict while rolling back observation writes.

The caller owns the outer transaction. Source/observation refusal or late database
failure rolls back all this domain's updates/inserts/pruning and resets its created
and updated counts. Caller-owned changes outside the savepoint survive a refusal;
a successful run can still be rolled back by the caller.

Scope limits: source identity checks do not authenticate publisher bytes. Existing
pruning policy and fetcher parsing/transport are separate boundaries; this change
adds no production data repair or publication acceptance. The registered seeding
handler and its retries share this contract. Bootstrap writes entity-linked GDP,
and the ETL loader writes extraction-specific records; those writers are unchanged.
