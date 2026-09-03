# Poverty indices — correction record

Issue #137 P7. Every figure below was a Python constant in
`backend/seeding/domains/national_gdp/__init__.py`, written to `poverty_indices`
at confidence 0.85.

## Before

Observed by running the pre-fix seeder against an empty database:

```
year=2024 headcount=33.40 extreme=8.60 gini=0.408 conf=0.85
year=2021 headcount=36.10 extreme=10.20 gini=0.410 conf=0.85
year=2019 headcount=36.10 extreme=8.50 gini=0.408 conf=0.85
all three cite -> https://www.knbs.or.ke/economic-survey-2025/
```

Each row's `metadata.source` named a different publication — "World Bank Kenya
Economic Update 2024", "KNBS KIHBS 2021", "KNBS KIHBS 2015/16 (adjusted for 2019
Census)" — while all three cited the one Economic Survey 2025 URL above. None of
the three named publications is that document.

## The source

World Bank API, Kenya, retrieved 2026-09-02:

- headcount — `SI.POV.NAHC`, poverty headcount ratio at **national** poverty lines
  <https://api.worldbank.org/v2/country/KEN/indicator/SI.POV.NAHC>
- Gini — `SI.POV.GINI` (reported 0–100)
  <https://api.worldbank.org/v2/country/KEN/indicator/SI.POV.GINI>

| year | headcount | Gini (0–100) |
|---|---|---|
| 2022 | 39.8 | 38.5 |
| 2021 | 38.6 | 38.7 |
| 2020 | 42.9 | 36.2 |
| 2015 | 36.1 | 40.8 |
| 2005 | 46.8 | 46.4 |
| 1997 | 52.3 | 45.0 |
| 1994 | 40.3 | 43.1 |
| 1992 | 57.2 | 56.9 |

**There is no observation for 2019 or for 2024.**

## Before / after

| year | field | before | after | why |
|---|---|---|---|---|
| 2019 | headcount | 36.1 | *row removed* | 36.1 is the **2015** observation. No 2019 observation exists. |
| 2019 | Gini | 0.408 | *row removed* | 0.408 is the **2015** Gini. The whole row was the 2015 observation relabelled. |
| 2021 | headcount | 36.1 | **38.6** | 36.1 is the 2015 value, published under a row labelled "KNBS KIHBS 2021". |
| 2021 | Gini | 0.410 | **0.387** | matches no observation in the series; 2021 is 38.7/100. |
| 2024 | headcount | 33.4 | *row removed* | No observation for 2024 in any of the three named sources. |
| 2024 | Gini | 0.408 | *row removed* | The 2015 Gini again. |
| all | extreme | 8.5–10.2 | **null** | see below |
| all | confidence | 0.85 | **0.95** | now read from the API rather than typed in. |
| — | 2020, 2022, 2015, 2005, 1997, 1994, 1992 | absent | **published** | observed years the constant simply omitted. |

Net: three rows, two of them unsourced, become eight observed years.

## Why `extreme_poverty_rate` is null, not corrected

The World Bank's extreme-poverty indicator is `SI.POV.DDAY`, the $2.15/day
international line, which reads **44–46%** for Kenya. The constant held
**8.5–10.2**, which is the national *food-poverty* rate — a different measure,
not a wrong version of the same one.

Substituting one for the other would move a published figure roughly fivefold
while calling it a correction. So the column is set null and the rows carry
`metadata.extreme_poverty_rate_absent_reason` saying why. It stays null until a
KNBS food-poverty source is wired up.

## Scale

`SI.POV.GINI` is reported 0–100; `poverty_indices.gini_coefficient` holds 0–1.
The conversion happens once, in `fetch_kenya_poverty`, and is recorded per row as
`metadata.gini_scale`. A test asserts every stored Gini is strictly between 0
and 1, because getting this wrong publishes a Gini of 38.7.

## Production effect

The next nightly run will, in one pass:

- delete the NULL-entity `poverty_indices` rows for 2019 and 2024
- rewrite 2021 (headcount 36.1 → 38.6, Gini 0.410 → 0.387)
- null every `extreme_poverty_rate`
- insert 2022, 2020, 2015, 2005, 1997, 1994, 1992

The prune is guarded by a non-empty fetch, so a World Bank outage deletes
nothing — the same last-known-good rule the GDP path already follows.

No frontend component reads these fields; they are served only by
`/api/v1/economic/poverty`, whose response model already declares all three as
`Optional[float]`.
