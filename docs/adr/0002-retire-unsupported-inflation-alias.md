# Retire the unsupported legacy inflation alias

Issue #474; 2026-10-03. Classification: valid publication failure, recurring
across generic indicator and county-profile readers plus a budget fallback.

`inflation_rate_cpi` is the deprecated fixture generator's unsupported
January 2024=6.3 literal, not a maintained inflation measure. The retained KNBS
January 2025 release, Table 1, PDF page 2, reports January 2024=6.9 and
February 2024=6.3. Its SHA-256 is
`ca9654579a2a0b8d14301de005cea70f1db2943c8d40cb111be3b8b1e0ccd44d`.
The publisher fact check does not recover original production lineage (#347)
or authorize replacing maintained CBK observations with rounded PDF values.

## Decision

The shared economic publication gate withholds this retired alias, including
case variants, with reason `retired unsupported inflation alias`. A high
confidence score, an official-looking label, or `publishable=True` does not
revive it. Existing finite-value refusals run first. Stored rows remain intact.
The filter runs before the public result limit and exposes existing withheld
counts/reasons on indicator lists and county profiles.

Budget inflation selects only national `inflation_rate_12m` and
`inflation_rate` observations, using the existing date/tie selection and
row-declared captions. When neither is available, the value, date, caption,
and measure stay NULL, with an explicit `inflation_missing_reason`. Measured
zero stays zero. The deprecated fixture generator omits the retired literal;
it does not rename it into a maintained series or correct its stored value.

The maintained monthly CBK, annual World Bank, World Bank CPI index and
approved KNBS CPI paths keep their existing policies. This narrow retirement
does not certify other economic observations or the generator's other
historical literals. There is no backfill, deletion, migration or source fetch.

## Caller inventory

Repository searches: `rg -n 'inflation_rate_cpi' .` and
`rg -n 'EconomicIndicator|RealDataFetcher|fetch_knbs_economic_indicators'
backend scripts`.

| Entry path | Disposition |
|---|---|
| `routers/economic.py`: indicators, filtered/unfiltered | Shared gate; omissions disclosed before limit |
| `routers/economic.py`: county economic profile | Same shared gate and disclosure fields |
| `main.py`: enhanced budget | Legacy fallback removed; maintained-only selection |
| `routers/economic.py`: national summary | Explicit annual-series filter; cannot select this alias |
| `main.py` / `data_provenance.py`: health inventories | Stored counts/vintages remain inventory, not publication of this numeric observation |
| `data_provenance.py`: verify endpoint | No economic value branch; does not promote this alias |
| Deprecated `RealDataFetcher` method, `generate_all_real_data`, module CLI | The only literal alias writer omitted; each caller reaches that method |
| Maintained economic fetch/parser/writer and configured fallback | Maintained fetchers do not emit this alias; retained JSON contains none. A separately supplied legacy fixture can remain stored, but public readers withhold it |
| CPI correction verification | Reuses shared gate; approved `CPI` checks unchanged |

## Regression receipts

The new actual FastAPI handler tests were executed against shipping
`cb8411c064922130f44f1200821e426bce3a810e` before the fix. The focused run had
**7 failures / 11 passes**: filtered indicators, unfiltered limit, county
profile, legacy-only budget, direct alias gate and deprecated generator
reproduced the retirement gap. The seventh failure was the healthy-zero
control expecting the newly added absence field; it was not another value leak.
The old test that expected the unsupported 6.3 fallback was revised to require
explicit absence.

Commands (from the checkout, existing dependencies, no outbound HTTP):

```sh
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/backend" \
  /Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python -B -m pytest \
  backend/tests/test_legacy_inflation_retirement.py \
  backend/tests/test_budget_inflation.py -q

PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/backend" \
  /Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python -B -m pytest \
  backend/tests/test_legacy_inflation_retirement.py \
  backend/tests/test_budget_inflation.py \
  backend/tests/test_budget_economic_context_provenance.py \
  backend/tests/test_cpi_publication.py \
  backend/tests/test_inflation_monthly_live.py \
  backend/tests/test_economic_endpoints.py -q
```

The first corrected combined run passed **93 tests**. With an additional 7.88
precision control, the final combined run passed **94 tests**. An independent
offline review passed **34 controls**, including forged official claims,
case variants, pagination, zero, approved CPI, unchanged historical rows and
the generator's exact old-versus-new output difference. Production URL
acceptance and deployment remain separate root-owned gates. Tests use isolated
SQLite and owned temporary fixture files; they do not prove production state or
original tuple lineage.
