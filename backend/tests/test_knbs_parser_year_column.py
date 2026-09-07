"""The year column must hold a year, and a county's population must be a county's.

Measured against production on 2026-09-07 (alembic ``ce6ed007f696``).

`population_data` holds 77 rows. Twelve were written from source_document 524,
the KNBS "2024 Statistical Abstract - Samburu County", all attributed to
Samburu: eleven with years 130, 135, 220, 232, 252, 335, 396, 399, 531, 621 and
897, and a twelfth at year 2024 with a total_population of 20,317,126 against
the county's real 310,327.

The county's real figure is in the same table, correct, and loses to the
misparse: id=42, 310,327, from source_document 2435 (2019 Kenya Population and
Housing Census Volume I), page_ref "p. 17", extraction_id 4331.

WHAT REACHES A READER, AND WHAT DOES NOT
----------------------------------------
The two faults have different blast radii, and saying so precisely is the point.

The 20,317,126 row is published. Every county read path in `main.py`
(:3299, :3600, :6011, :6295) takes `order_by(year.desc()).first()`, so 2024
outranks the 2019 census row, and production serves:

    www.auditgava.com/counties/25   ->  "20.32M residents"  (rendered; read in
                                        the browser 2026-09-07)
    /api/v1/counties/25             ->  population 20317126
    /api/v1/counties/25/comprehensive
                                    ->  demographics.population 20317126,
                                        population_year 2024,
                                        budget.per_capita_budget 399.14
                                        (KES 26,131.72 on the census figure)
    /api/v1/economic/counties/28/profile
                                    ->  population_growth_rate 1289.401115597418

`/comprehensive` labels that figure
`data_sources.population = "Kenya National Bureau of Statistics (KNBS) Census
2019"`. The 2019 census says 310,327. So the site does not merely publish a
wrong number; it attributes it to the document that contradicts it, on a page
headed "EVIDENCE STANDARD - SOURCE TRAIL VISIBLE".

The eleven non-year years are **not** rendered on any page. Every read path
takes the newest row per entity, so 130..897 lose to 2019 and 2024, and no
frontend file fetches the series. They are served raw by the public API:

    /api/v1/economic/population?entity_id=28  ->  all thirteen rows verbatim,
                                                  "year": 897 included

That is an API-visible defect, not a rendered-page one. Both are worth fixing;
only the first was ever on a page.

Nothing withholds either. Population rows are never filtered on `publishable` —
every one of the 77 rows carries `publishable = False` and the figures above are
live anyway — and `routers/economic.py:316`'s `min_confidence >= 0.7` passes
them, because the broken parse recorded confidence 1.00.

THE TWO FAULTS
--------------
Both are in `etl/knbs_parser.py`, which reaches this table through
`etl/kenya_pipeline.py` and `etl/database_loader.py:613` — the writer that
stamps `source_document_id` and `confidence`.

1. `_extract_population_from_table` chooses its year column by substring, so a
   header like "Age (Years)" matches `"year" in header`. It then does
   `int(cell)` with no range check, behind a bare `except: pass`.
2. `_extract_population_from_text` gates on `10_000_000 <= population <=
   100_000_000` - a band sized for Kenya. Applied to one county's abstract it
   accepts any national-scale figure as that county's population.

A year column that accepts 130 is not a year column, and a county population
of 20 million is not a county population.
"""

import pytest
from etl.knbs_parser import KNBSParser

# Kenya's most populous county at the 2019 census (Nairobi, 4,397,073). No
# county figure may plausibly exceed the national total either; the point of
# the band is that "is this Kenya?" and "is this one county?" are different
# questions and the parser was only ever asking the first.
NAIROBI_2019 = 4_397_073
SAMBURU_2019 = 310_327


def _emitted(table, metadata):
    parser = KNBSParser()
    extracted = {"population_data": []}
    parser._extract_population_from_table(table, extracted, metadata)
    return extracted["population_data"]


class TestYearColumnHoldsAYear:
    """A cell that is not a calendar year must never land in `year`."""

    def test_age_column_is_not_a_year_column(self):
        """"Age (Years)" matches `"year" in header`; 130 is not a year.

        This is the exact shape of population_data id=6: year 130,
        total_population 129,696, source_document 524.
        """
        table = [
            ["Sub-County", "Age (Years)", "Total Population"],
            ["Samburu East", "130", "129,696"],
        ]
        records = _emitted(table, {"year": None, "county": "Samburu"})

        years = [r["year"] for r in records if r.get("year") is not None]
        assert 130 not in years, (
            f"parser put 130 in the year column; emitted {records!r}"
        )
        for year in years:
            assert 1900 <= year <= 2100, (
                f"{year} is not a calendar year (from 'Age (Years)' column)"
            )

    @pytest.mark.parametrize(
        "cell,population",
        [
            ("130", "129,696"),
            ("135", "26,754"),
            ("220", "67,912"),
            ("232", "64,070"),
            ("252", "127,668"),
            ("335", "31,068"),
            ("396", "28,690"),
            ("399", "69,938"),
            ("531", "55,446"),
            ("621", "137,852"),
            ("897", "33,002"),
        ],
    )
    def test_none_of_the_eleven_db_years_can_be_written(self, cell, population):
        """Every non-year year currently sitting in population_data."""
        table = [
            ["Sub-County", "Reference Period", "Population"],
            ["Samburu", cell, population],
        ]
        records = _emitted(table, {"year": None, "county": "Samburu"})

        for record in records:
            year = record.get("year")
            if year is None:
                continue
            assert 1900 <= year <= 2100, (
                f"parser accepted {year!r} as a year for a row of {population}"
            )

    def test_a_real_year_column_still_works(self):
        """The guard must not cost the well-formed case."""
        table = [
            ["County", "Year", "Total Population"],
            ["Samburu", "2019", "310,327"],
        ]
        records = _emitted(table, {"year": None, "county": "Samburu"})

        assert records, "a well-formed table must still yield a record"
        assert records[0]["year"] == 2019
        assert records[0]["total_population"] == SAMBURU_2019

    def test_out_of_range_year_cell_falls_back_to_the_document_year(self):
        """An unusable year cell must yield the document's year, not the cell.

        `metadata["year"]` is the year the document is filed under, which is a
        defensible answer for a row whose own year cell is unreadable. The
        cell's contents are not.
        """
        table = [
            ["Sub-County", "Age (Years)", "Total Population"],
            ["Samburu East", "130", "129,696"],
        ]
        records = _emitted(table, {"year": 2024, "county": "Samburu"})

        for record in records:
            assert record.get("year") in (None, 2024), (
                f"expected the document year 2024 or None, got "
                f"{record.get('year')!r} — the parser used the age cell"
            )


class TestCountyPopulationIsACountyPopulation:
    """A single county's abstract cannot report a national-scale figure."""

    def test_national_scale_figure_is_not_a_county_population(self):
        """The exact shape of population_data id=5: 20,317,126 for Samburu.

        20,317,126 sits inside the parser's `10_000_000 <= p <= 100_000_000`
        band, which is sized for Kenya as a whole.
        """
        parser = KNBSParser()
        text = (
            "Samburu County Statistical Abstract 2024. "
            "The report covers a population of 20,317,126 people across the "
            "sub-counties, with detailed tables following in section two. "
        ) * 3

        result = parser._extract_population_from_text(text, 2024, county="Samburu")

        if result is not None:
            assert result.total_population <= NAIROBI_2019, (
                f"accepted {result.total_population:,} as Samburu's population; "
                f"Kenya's largest county is {NAIROBI_2019:,}"
            )

    def test_an_area_in_square_kilometres_is_not_a_population(self):
        """Samburu's abstract says "an area of 21,090 square kilometers".

        Pattern 2's trailing (people|persons|inhabitants) is an OPTIONAL
        group, so it matches any comma-formatted number. Widening the band to
        county scale without this guard makes the parser publish the county's
        area as its population — which is what it did when first tried.
        """
        parser = KNBSParser()
        text = (
            "A.1 OVERVIEW OF SAMBURU COUNTY. Samburu County is within the "
            "northern parts of the Great Rift Valley in Kenya. The County "
            "lies within the ASAL region covering an area of 21,090 square "
            "kilometers, and is bordered by Turkana, Baringo and Marsabit. "
        ) * 3

        result = parser._extract_population_from_text(text, 2024, county="Samburu")

        assert result is None or result.total_population != 21_090, (
            "parser read the county's area in km2 as its population"
        )

    def test_national_document_still_parses_from_text(self):
        """The guard is county-scoped; Kenya's own figure must still parse."""
        parser = KNBSParser()
        text = (
            "Kenya Economic Survey 2024. The Kenya National Bureau of "
            "Statistics reports a population of 47,564,296 people at the "
            "2019 census, with detailed tables following. "
        ) * 3

        result = parser._extract_population_from_text(text, 2019, county=None)

        assert result is not None, "the national text path must still work"
        assert result.total_population == 47_564_296
