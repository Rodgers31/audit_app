# Bounded dispatch mappings for #554

Pinned base f6c31e271297eece52f34102dc40a1e2ed7069a8 / tree 69ddfad6deb814dd08fdaee2db2d512d73e14c78. Live issue body/comments match the frozen launch snapshot. Primary is read-only. No applicable AGENTS.md, CLAUDE.md, issue-tracker document or ADR was found. The explicit assignment supplies issue routing.

A source is an admin command label. A domain is the existing native ownership unit, not a guarantee of a single publisher. Each command invokes exactly one existing registered domain, with default settings and no arbitrary URLs or CLI arguments. Native financial publication contracts remain unchanged. This is dispatch plumbing acceptance using inert registered handlers, not financial ingestion acceptance.

| Admin source | Native domain / actual registered entrypoint | Inputs / persistence scope | Decision |
| --- | --- | --- | --- |
| OAG | audits / seeding.domains.audits.run | Existing OAG audit source admission / audits and source documents | Preserve accepted mapping |
| Treasury | fiscal_summary / seeding.domains.fiscal_summary.run | Treasury estimates/framework/revenue, CoB headlines, CBK data and existing fallback corpus / FiscalSummary and SourceDocument | Bounded national fiscal summary; explicitly mixed publishers |
| CoB | counties_budget / seeding.domains.counties_budget.run | CoB county BIRR and existing fallback corpus / BudgetLine, Entity, FiscalPeriod, SourceDocument; revision and revenue supersession within this domain | Bounded county budget run; national budget/stalled projects/pending bills are excluded |
| KNBS | population / seeding.domains.population.run | KNBS 2019 county census plus World Bank national population series / PopulationData, Entity, SourceDocument and census Extraction; existing document/cache files | Bounded population run; excludes GDP, poverty and economic indicators |
| OpenData | none | No OpenData entrypoint in the implemented registry; generic World Bank or county domains are not OpenData | Unavailable: prerequisite native ingestion entrypoint |
| CRA | none | Source freshness policy lists cra_recommendations, but no CRA native registry entrypoint exists; revenue_by_source is KRA, a different institution | Unavailable: prerequisite native ingestion entrypoint |

All entries are grounded in backend/seeding/registries.py, source_registry.py and the listed domain __init__, fetcher and writer files on the pinned base. No new financial domain is invented. One existing domain claim covers each selected run; all affected financial tables belong to that domain's existing native handler. Source documents and entity lookup/create side effects follow existing native ownership semantics, and every-writer production fencing remains #583.

`ADMIN_ETL_DISPATCH_ENABLED` remains default-off. A dedicated worker's source allowlist `ADMIN_ETL_DISPATCH_SOURCES` defaults to `oag`, preserving accepted activation scope; a validated comma-separated subset of the four implemented sources enables the additional bounded runs. Unknown, duplicate or empty selections refuse worker startup. API capabilities derive from the leased worker's durable per-domain readiness snapshot, never from API imports of financial modules. Missing handlers disable their own source; healthy sources may proceed. New readiness rows are default false until worker registration. Rollout ordering: migrate with all writers stopped, deploy code, then separately approve source selection/worker activation and deployed operator/admin acceptance.

No production migration, activation, reconciliation, financial source change, workflow dispatch or settings mutation is authorized. #554 and #583 remain open.
