# B66 source to job coverage

Frozen base: `924f1a4f27e1952f97d2291d8878d88603132237`. This is source inspection plus owned fixture execution; no current live source/operator acceptance is asserted. #744/#602/#554/#583/#699 stay open. #745 datasets/UI are deferred.

## Supported source contracts

| Publisher/source | Handler and selector | CLI / dedicated ownership | Workflow plan / flag | Persistence / qualification | UI and acceptance frontier |
|---|---|---|---|---|---|
| CRA FY2026/27 Table 5.2 | `seeding.domains.cra.run`; reviewed PDF source/parser/writer | `--domain cra`; admin `cra` maps to `cra`, native or dedicated domain claim | `SEED_CRA_INGESTION_ENABLED=false`; future Sunday03UTC or explicitly selected manual domain when enabled | SourceDocument + Extraction; recommendations, never enacted/actual financial facts | Existing source/command/job receipts; intended-host active source/operator acceptance outstanding |
| KNBS Economic Survey 2026 Table 5.13 | `seeding.domains.opendata.run`; exact reviewed URL/hash parser | `--domain opendata`; admin `opendata` maps to `opendata`, same durable ownership | `SEED_OPENDATA_INGESTION_ENABLED=false`; future Sunday03UTC or manual selection | SourceDocument + Extraction; 47 counties + published Total, 46 columns, 2,125 numeric/83 missing cells; raw labels and published discrepancies retained; **not public financial qualification** | Existing command/native metadata records; no new public endpoint/widget; current provider/operator acceptance outstanding |
| KNBS future release observation | same owned `opendata` handler, new `discovery.py` | Same CLI/dedicated command and exclusion; no separate daemon/cron/provider | additionally `SEED_KNBS_RELEASE_DISCOVERY_ENABLED=false`; weekly only when opt-ins approved | Bounded report/index/content identity in correlated native job metadata. Only accepted pinned URL+hash reaches existing parser/writer. Unknown compatible reissue/future edition is a **quarantined review candidate**, without extraction or fact writes | `release_discovery.checked_at/status/reason/last_recorded_edition` in existing native receipt metadata. Recorded source history is explicitly not fresh verification. No claim future editions are semantically accepted |
| Cancelled ArcGIS/OpenData portal | no substitute fetch through discovery | No portal job is created | Remains unavailable | Not repaired or relabelled | #621's replacement contract does not restore original portal |
| Admin `knbs` label | `population.run`, not Table5.13 | admin `knbs` → `population` | Legacy registered domain | World Bank national population plus separately attributed KNBS census county series | Preserve existing source attribution; never call this workbook automation |

Accepted URL and content are unchanged: `https://www.knbs.or.ke/reports/2026-economic-survey/`, workbook `https://www.knbs.or.ke/wp-content/uploads/2026/10/Chapter-5-Public-Finance.xlsx`, SHA256 `887712acdb8ec673f96d6d0fd14491a5861b0450d2ffcf49aedde093a257a5d5`, 224,617 bytes. Workbook upload path month is not publication date. Pinned parser preserves April2026 report publication evidence, unknown workbook publication date, distinct PDF/workbook revised markers and limited unit context. No checksum is silently advanced.

## Relevant legacy default registry

All fifteen remain selected Monday–Saturday02UTC and Sunday03UTC by the explicit workflow selection plan. Their underlying publication frequencies below are descriptive; the UI calendar is not consulted by `seed --all` or this plan. Registry presence does not prove fresh publisher data. Each native CLI run records an IngestionJob and uses existing shared exclusion; a dedicated UI mapping exists only where named. See `backend/seeding/domains/<domain>/__init__.py`, local fetcher/writer, `registries.py`, `admin_etl_dispatch.py`.

| Domain | Publisher/feed / handler inputs | Persistence/readback family | Native admin mapping / freshness qualification |
|---|---|---|---|
| counties_budget | CoB quarterly PDFs; configured county budget fixture fallback | BudgetLine + SourceDocument | `cob`; existing qualification/hold policy and fixture mode preserved |
| audits | OAG annual PDFs / explicit bounded scope | Audit + source/extraction evidence | `oag`; discovery preview not extraction/publication acceptance |
| economic_indicators | World Bank/CBK/KNBS series; configured fallback | EconomicIndicator + SourceDocument | CLI only; live/partial/fixture separately marked |
| population | World Bank national series and KNBS2019 county census | PopulationData + source/extraction evidence | `knbs`; source attribution remains series-specific |
| county_officials | county/official roster extraction and last known good | officials/source records | CLI only; live/fixture remains visible |
| national_debt | Treasury/CBK register and bulletin inputs | debt/loan facts + SourceDocument | CLI only; source validation/refused/fixture contracts unchanged |
| national_budget | Treasury/CoB budget execution PDFs | BudgetLine + SourceDocument | CLI only; live/partial/fixture unchanged; bootstrap writer remains separately owned |
| pending_bills | CoB/Treasury BROP plus retained inputs | Loan/pending bill facts + SourceDocument | CLI only; source availability/fallback labels unchanged |
| debt_timeline | Treasury/CBK debt timeline | DebtTimeline + SourceDocument | CLI only; live/fixture unchanged |
| fiscal_summary | Treasury BPS/QEBR / CoB | FiscalSummary + SourceDocument | `treasury`; existing annual/quarterly semantics preserved |
| revenue_by_source | KRA revenue, distinct from CRA | RevenueBySource + SourceDocument | CLI only; partial source coverage preserved |
| learning_hub | explicitly curated educational content | learning content tables | CLI only; curated fixture is not new publisher content |
| stalled_projects | CoB published stalled-project tables | stalled project records | CLI only; refusal remains visible |
| national_gdp | World Bank GDP/poverty inputs | national indicator/source records | CLI only; fixture labels and per-series origin preserved |
| imf_weo | IMF DataMapper | imf_weo_observations | CLI only; inserts/idempotency and fixture labels unchanged |

No financial publication or reconciliation rule changes. Existing county/financial/public and admin receipt UI read paths remain authoritative. Local source fixtures do not certify those deployed readbacks, current source availability or a representative SQL/egress/capacity budget.
