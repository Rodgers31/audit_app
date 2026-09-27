"""The KNBS homepage is not a population source (issue #204).

``KNBSDataFetcher.fetch_population_data`` had three sources, tried in order:

1. the KNBS extractor + parser (structured documents, a year per record);
2. ``_scrape_knbs_population`` — a regex over the KNBS homepage for a number
   next to the word "population", filed under ``census_year = <this year>``;
3. ``seeding/real_data/population.json`` — a git-tracked fixture.

It is reached from one place: ``services/auto_seeder.py``'s population domain,
a boot domain, which the auto-seeder runs on every production web start.

Run live on 2026-09-26, source 1 found no documents (every KNBS page failed TLS
verification) and source 2 returned ``{'national_population': 82,
'census_year': 2026}``. The 82 comes from the homepage sentence "the
population density of kenya in 2019 was of 82 people per square kilometre".
That is where population_data id=69 came from. #203's floor refuses it, but
only because a density happens to be small.

Removing source 2 alone would make source 3 reachable, and that is worse. The
fixture puts Mandera at 1,200,890 against the census's 867,457 (see
``seeding/domains/population/census_counties.py``), and it sums to 47,897,729
rather than the census total of 47,564,296. The auto-seeder would write both
over the extraction-backed 2019 rows in place, on every boot, leaving the
rows' ``extraction_id`` and ``page_ref`` pointing at a document that says
otherwise. The fixture already reaches the site through the nightly's
population domain, under the census gate. It is not a live fetch, and it no
longer poses as one here.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from typing import Iterator

import httpx
import pytest
from models import Base, Country, Entity, EntityType, PopulationData
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

NATIONAL_2019 = 47_564_296  # production id=64, source_document 1823
MANDERA_2019 = 867_457  # census Table 2.2; production extraction 4345, p. 17
MANDERA_IN_FIXTURE = 1_200_890  # population.json's figure for Mandera

#: The issue's six candidate strings, each with what the old regex made of it.
ISSUE_CANDIDATES = [
    ("kenya population 82", 82),
    ("population: 82%", 82),  # a percentage
    ("urban population 82.5 per cent", 82),  # a decimal percentage
    ("population 82 of 100 counties", 82),  # a count
    ("population 82,491,000", 82_491),  # a real figure, truncated
    ("population 47.6 million", 47_600_000),  # right shape, fabricated vintage
]

#: Captured from https://www.knbs.or.ke/ on 2026-09-26. The first sentence is
#: what the old regex matched; the second is a mid-2026 *projection* that it
#: missed only because of the markup between the word and the figure.
LIVE_HOMEPAGE_2026_09_26 = (
    '<a href="https://www.knbs.or.ke/census/"><u>Population</u></a> : '
    "54,227,015 (Mid 2026) ——— "
    '<p><span style="color: #0f0f0f;">The population density of Kenya in 2019 '
    "was of 82 people per square kilometre.</span></p>"
)

ALL_HOMEPAGES = [pytest.param(s, id=s) for s, _ in ISSUE_CANDIDATES] + [
    pytest.param(LIVE_HOMEPAGE_2026_09_26, id="live-homepage-2026-09-26")
]


class _NoDocuments:
    """Source 1 as it behaves today: discovery finds nothing."""

    def discover_documents(self):
        return []


@pytest.fixture()
def knbs_homepage(monkeypatch):
    """Serve ``body`` for every request to knbs.or.ke; record what was asked."""
    requested: list[str] = []
    state = {"body": ""}
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text=f"<html><body>{state['body']}</body></html>")

    def client(*args, **kwargs):
        kwargs.pop("verify", None)
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)

    def serve(body: str) -> list[str]:
        state["body"] = body
        return requested

    return serve


def _knbs_fetcher():
    from services.live_data_fetcher import KNBSDataFetcher

    fetcher = KNBSDataFetcher()
    fetcher._extractor = _NoDocuments()
    return fetcher


@pytest.mark.parametrize("homepage", ALL_HOMEPAGES)
def test_the_homepage_yields_no_population(knbs_homepage, homepage):
    """Whatever the homepage says, it is not read as Kenya's population."""
    knbs_homepage(homepage)

    result = asyncio.run(_knbs_fetcher().fetch_population_data())

    assert result["national_population"] is None, (
        f"read {result['national_population']!r} as Kenya's population, "
        f"filed under {result['census_year']!r}, from {homepage!r}"
    )
    assert result["fetch_success"] is False


def test_the_fixture_is_not_a_live_fetch(knbs_homepage):
    """With source 1 empty and nothing on the homepage, nothing is fetched.

    The old fallback handed the auto-seeder the whole of population.json,
    including Mandera at 1,200,890 and a national sum of 47,897,729.
    """
    knbs_homepage("<p>Nothing numeric here.</p>")

    result = asyncio.run(_knbs_fetcher().fetch_population_data())

    assert result["fetch_success"] is False
    assert result["national_population"] is None
    assert result["counties"] == []


# ── through the writer ────────────────────────────────────────────────────


@pytest.fixture()
def production_rows(tmp_path, monkeypatch) -> Iterator[tuple]:
    """The two production rows this path can reach, as they stand today."""
    engine = create_engine(f"sqlite:///{tmp_path/'pop.db'}")
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    session = Sess()

    country = Country(
        name="Kenya",
        iso_code="KE",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    session.add(country)
    session.flush()
    national = Entity(
        country_id=country.id,
        canonical_name="National Government",
        slug="national-government",
        type=EntityType.NATIONAL,
    )
    mandera = Entity(
        country_id=country.id,
        canonical_name="Mandera County",
        slug="mandera-county",
        type=EntityType.COUNTY,
    )
    session.add_all([national, mandera])
    session.flush()
    session.add_all(
        [
            PopulationData(
                entity_id=national.id,
                year=2019,
                total_population=NATIONAL_2019,
                source_document_id=1823,
            ),
            PopulationData(
                entity_id=mandera.id,
                year=2019,
                total_population=MANDERA_2019,
                extraction_id=4345,
                page_ref="p. 17",
            ),
        ]
    )
    session.commit()

    import services.auto_seeder  # noqa: F401  (see test_national_population_floor)

    module = sys.modules["services.auto_seeder"]
    monkeypatch.setattr(module, "SessionLocal", Sess)
    try:
        yield session, module
    finally:
        session.close()
        engine.dispose()


def _table(session) -> list[tuple]:
    session.expire_all()
    return sorted(
        (r.entity_id, r.year, r.total_population)
        for r in session.query(PopulationData).all()
    )


def _seed_with_real_fetcher(module):
    seeder = module.AutoSeeder()
    seeder.aggregator.knbs._extractor = _NoDocuments()
    asyncio.run(seeder._seed_population_live())


@pytest.mark.parametrize(
    "homepage",
    [
        # The one issue candidate #203's floor cannot see: a plausible figure
        # that the old code filed as a fresh observation for this year.
        pytest.param("population 47.6 million", id="plausible-figure-fabricated-vintage"),
        # Nothing on the homepage, so the old code fell through to the fixture.
        pytest.param("<p>Nothing numeric here.</p>", id="fixture-fallback"),
    ],
)
def test_the_boot_writer_leaves_production_rows_alone(
    knbs_homepage, production_rows, homepage
):
    session, module = production_rows
    before = _table(session)
    knbs_homepage(homepage)

    _seed_with_real_fetcher(module)

    after = _table(session)
    assert after == before, (
        f"the boot-time population domain rewrote population_data from {homepage!r}: "
        f"{sorted(set(after) - set(before))} replaced {sorted(set(before) - set(after))}"
    )


# ── the writer's own current-year stamp ───────────────────────────────────


def _seed_with_payload(module, payload):
    class _Aggregator:
        async def fetch_all_population_data(self):
            return payload

    seeder = module.AutoSeeder()
    seeder.aggregator = _Aggregator()
    asyncio.run(seeder._seed_population_live())


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {"fetch_success": True, "national_population": NATIONAL_2019, "counties": []},
            id="national-without-a-year",
        ),
        pytest.param(
            {
                "fetch_success": True,
                "national_population": None,
                "counties": [{"county": "Mandera", "total_population": MANDERA_2019}],
            },
            id="counties-without-a-year",
        ),
    ],
)
def test_a_figure_without_a_year_is_not_filed_under_this_one(production_rows, payload):
    """The writer used ``census_year or datetime.now().year``.

    That stamp is what made id=69's year equal the year it was written. A
    figure whose vintage the source did not state is refused, not dated
    today. Source 1 can return county records without a national one, which
    leaves ``census_year`` unset, so this is reachable without the scrape.
    """
    session, module = production_rows
    before = _table(session)

    _seed_with_payload(module, payload)

    after = _table(session)
    this_year = datetime.now().year
    assert [r for r in after if r[1] == this_year] == []
    assert after == before


def test_a_figure_with_its_year_still_lands(production_rows):
    """Positive control: a structured record that states its vintage is written."""
    session, module = production_rows

    _seed_with_payload(
        module,
        {
            "fetch_success": True,
            "national_population": 57_532_493,
            "census_year": 2025,
            "counties": [],
        },
    )

    assert (2025, 57_532_493) in [(y, p) for _, y, p in _table(session)]


@pytest.mark.parametrize("year", [None, 2025])
def test_document_year_survives_parser_fetcher_and_boot_writer(
    monkeypatch, production_rows, year
):
    from etl.knbs_parser import KNBSParser

    session, module = production_rows
    before = _table(session)
    parser = KNBSParser()
    monkeypatch.setattr(parser, "_download_pdf", lambda url: b"pdf")
    monkeypatch.setattr(parser, "_extract_text_from_pdf", lambda pdf:
                        "Kenya population: 57,532,493 persons. This is the national population total.")
    monkeypatch.setattr(parser, "_extract_tables_from_pdf", lambda pdf: [])

    class Documents:
        def discover_documents(self):
            return [{"title": "Population survey", "type": "economic_survey",
                     "url": "https://knbs.or.ke/survey.pdf", "year": year}]

    seeder = module.AutoSeeder()
    seeder.aggregator.knbs._extractor = Documents()
    seeder.aggregator.knbs._parser = parser
    fetched = asyncio.run(seeder.aggregator.knbs.fetch_population_data())
    assert fetched["census_year"] == year
    asyncio.run(seeder._seed_population_live())
    if year is None:
        assert _table(session) == before
    else:
        assert (year, 57_532_493) in [(y, p) for _, y, p in _table(session)]
