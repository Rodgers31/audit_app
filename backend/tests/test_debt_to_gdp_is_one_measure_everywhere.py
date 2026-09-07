"""One debt-to-GDP measure across the site, and across the peer table.

Follow-up to tests/test_debt_sustainability_one_label_one_measure.py, which
fixed the two columns beside this one. The ``debt_to_gdp`` column had the same
defect and it was harder to see, because the numbers happened to agree.

**1. The site published two headline debt-to-GDP figures.**

    /debt/national        debt_to_gdp_ratio  69.3   IMF GGXWDG_NGDP, declared
    /debt/sustainability  debt_to_gdp        70.0   DebtTimeline.gdp_ratio

Both labelled "debt to GDP", for the same year, on the same site, with only
one of them declaring a basis.

**2. Kenya's peer row was injected from the third basis.**

``_get_regional_peers(kenya_ratio=latest_dt.gdp_ratio)`` overwrote Kenya's
figure with the sustainability page's 70.0. That was not aligning Kenya with
the site's declared headline — it was importing ``DebtTimeline`` into a table
whose other four countries come from IMF GGXWDG. Kenya was the one country in
its own comparison measured differently from its comparators.

**3. And the column it was overwriting held projections.**

``_imf_fetch_debt_to_gdp`` asked the IMF DataMapper for five countries over
``periods=2018,...,2026`` and then took ``max(year)``. The DataMapper honours
neither filter — it answers with 226 countries (including aggregates like
WEOWORLD) covering 1998-2031 — so ``max(year)`` was **2031**, the furthest
projection in the file::

    country   max(year)=2031    2025 actual
    KEN            75.1             69.3
    ETH            27.0             43.1
    TZA            42.6             49.7
    UGA            53.3             54.2
    RWA            61.6             64.6

Ethiopia's cell would have read 27.0 — a 2031 forecast — in a column a reader
takes for today's debt level, 16 points below the actual. Removing the Kenya
injection without bounding the year would simply have swapped an injected 70.0
for a projected 75.1.

The column is now one indicator at one stated year for all five countries, and
Kenya's cell is the same figure, basis and year as the site's headline — by
construction, not by overwrite.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from models import DebtTimeline, ImfWeoObservation

VINTAGE = datetime(2026, 9, 7, tzinfo=timezone.utc)

#: The live DataMapper payload, to shape: every country, every year to 2031.
IMF_LIVE = {
    "KEN": {"2024": 67.3, "2025": 69.3, "2026": 71.6, "2030": 74.2, "2031": 75.1},
    "ETH": {"2024": 33.4, "2025": 43.1, "2026": 40.0, "2031": 27.0},
    "TZA": {"2024": 49.9, "2025": 49.7, "2026": 48.0, "2031": 42.6},
    "UGA": {"2024": 51.8, "2025": 54.2, "2026": 54.0, "2031": 53.3},
    "RWA": {"2024": 63.4, "2025": 64.6, "2026": 64.0, "2031": 61.6},
    # The aggregates and the other 200 countries the API returns unasked.
    "WEOWORLD": {"2025": 93.9, "2031": 102.3},
    "JPN": {"2025": 206.5, "2031": 192.8},
}


@pytest.fixture(autouse=True)
def _reset_peer_cache():
    import main

    main._peers_cache["ts"] = 0.0
    main._peers_cache["data"] = None
    yield
    main._peers_cache["ts"] = 0.0
    main._peers_cache["data"] = None


@pytest.fixture()
def imf_datamapper_live():
    """The real DataMapper response shape, with no network."""
    def _fetch(*_a, **_k):
        import httpx
        request = httpx.Request("GET", "https://www.imf.org/datamapper")
        return httpx.Response(
            200, json={"values": {"GGXWDG_NGDP": IMF_LIVE}}, request=request
        )

    with patch("main.httpx.get", side_effect=_fetch):
        yield


def sustainability(client) -> dict:
    from main import clear_all_caches

    clear_all_caches()
    body = client.get("/api/v1/debt/sustainability").json()
    assert body["status"] == "success", body
    return body


def peer(body: dict, country: str) -> dict:
    return next(p for p in body["regional_peers"] if p["country"] == country)


@pytest.fixture()
def seeded(db_session, seed_source_doc):
    """WEO rows as ``/debt/broader`` serves them, plus the DebtTimeline row
    whose 70.0 was the sustainability headline and the injected peer value."""
    B = 1e9
    for year, ext, dom, ratio in [
        (2024, 5057.0, 5868.3, 69.8),
        (2025, 5462.0, 6837.5, 70.0),
    ]:
        db_session.add(
            DebtTimeline(year=year, external=ext * B, domestic=dom * B,
                         total=(ext + dom) * B, gdp_ratio=ratio, unit="KES",
                         source_document_id=seed_source_doc.id)
        )
    for y, v, p in [(2024, 67.3, False), (2025, 69.3, False), (2026, 71.6, True),
                    (2030, 74.2, True), (2031, 75.1, True)]:
        db_session.add(
            ImfWeoObservation(country_code="KEN", indicator="GGXWDG_NGDP", year=y,
                              value=v, is_projection=p, vintage=VINTAGE,
                              source="imf_datamapper")
        )
    db_session.commit()
    return db_session


# ── 1. One headline ────────────────────────────────────────────────────────

def test_the_two_pages_state_one_debt_to_gdp(
    client, db_session, seeded, imf_datamapper_live
):
    """69.3 on the homepage and 70.0 on the debt page is two answers."""
    sust = sustainability(client)["debt_to_gdp"]
    # Read the declared headline through the same helper /debt/national uses,
    # on the test session — /debt/national itself needs a loan register this
    # fixture deliberately does not seed.
    import main

    declared = main._latest_imf_debt_to_gdp(db_session)

    assert declared is not None, "IMF WEO not seeded — fixture is wrong"
    assert sust["value"] == pytest.approx(declared[0]), (
        f"sustainability says {sust['value']}, the declared headline is {declared[0]}"
    )
    assert sust["value"] == pytest.approx(69.3)
    assert sust["year"] == 2025


def test_the_sustainability_headline_declares_its_basis(
    client, seeded, imf_datamapper_live
):
    d = sustainability(client)["debt_to_gdp"]
    assert "GGXWDG_NGDP" in d["basis"]
    assert d["source"] == "IMF World Economic Outlook"
    # The threshold verdict is unchanged by the basis switch.
    assert d["status"] == "above"


def test_without_imf_rows_the_fallback_basis_is_still_declared(
    client, db_session, seed_source_doc, imf_datamapper_live
):
    """DebtTimeline is a legitimate fallback. An UNdeclared basis is not."""
    B = 1e9
    db_session.add(
        DebtTimeline(year=2025, external=5462.0 * B, domestic=6837.5 * B,
                     total=12299.5 * B, gdp_ratio=70.0, unit="KES",
                     source_document_id=seed_source_doc.id)
    )
    db_session.commit()

    d = sustainability(client)["debt_to_gdp"]
    assert d["value"] == pytest.approx(70.0)
    assert "GGXWDG_NGDP" not in d["basis"]
    assert d["source"] != "IMF World Economic Outlook"
    assert d["basis"]


# ── 2. One measure across the five countries ───────────────────────────────

def test_kenyas_peer_cell_is_not_injected_from_the_debt_timeline(
    client, seeded, imf_datamapper_live
):
    """It read 70.0 — DebtTimeline.gdp_ratio — while its four comparators
    came from IMF GGXWDG."""
    body = sustainability(client)
    assert peer(body, "Kenya")["debt_to_gdp"] == pytest.approx(69.3)


def test_kenyas_peer_cell_equals_the_headline_above_it(
    client, seeded, imf_datamapper_live
):
    """They must agree BECAUSE they are the same measure.

    Equality alone is not evidence here, and asserting only that made this a
    tautology against the code it guards: pre-fix the two agreed at 70.0 by
    construction, because ``kenya_ratio`` copied DebtTimeline.gdp_ratio into
    both the headline and the peer cell. A test that the injection satisfies
    cannot be the test that removes it.

    So pin the reason as well as the result — same declared basis, same year,
    and that year is the one the whole column is pinned to.
    """
    body = sustainability(client)
    headline = body["debt_to_gdp"]
    row = peer(body, "Kenya")

    assert row["debt_to_gdp"] == pytest.approx(headline["value"])
    assert "GGXWDG_NGDP" in headline["basis"]
    assert row["debt_to_gdp_year"] == headline["year"]
    assert (
        body["regional_peers_basis"]["debt_to_gdp"]["reference_year"]
        == headline["year"]
    )


def test_no_peer_cell_carries_a_2031_projection(client, seeded, imf_datamapper_live):
    """``max(year)`` over a file the DataMapper serves to 2031 picked the
    furthest forecast for every country."""
    body = sustainability(client)
    for country, projected_2031 in [
        ("Kenya", 75.1), ("Ethiopia", 27.0), ("Tanzania", 42.6),
        ("Uganda", 53.3), ("Rwanda", 61.6),
    ]:
        assert peer(body, country)["debt_to_gdp"] != pytest.approx(projected_2031), (
            f"{country} is showing its 2031 projection"
        )


def test_every_peer_is_the_same_indicator_at_the_same_year(
    client, seeded, imf_datamapper_live
):
    body = sustainability(client)
    for country, actual_2025 in [
        ("Kenya", 69.3), ("Ethiopia", 43.1), ("Tanzania", 49.7),
        ("Uganda", 54.2), ("Rwanda", 64.6),
    ]:
        row = peer(body, country)
        assert row["debt_to_gdp"] == pytest.approx(actual_2025), country
        assert row["debt_to_gdp_year"] == 2025, country

    basis = body["regional_peers_basis"]["debt_to_gdp"]
    assert basis["indicator"] == "GGXWDG_NGDP"
    assert basis["reference_year"] == 2025


def test_a_country_missing_the_reference_year_is_absent_not_extrapolated(
    client, seeded
):
    """A peer with no value at the reference year gets nothing, rather than
    the nearest year the file happens to hold."""
    thin = dict(IMF_LIVE)
    thin["ETH"] = {"2031": 27.0}  # only the projection

    def _fetch(*_a, **_k):
        import httpx
        request = httpx.Request("GET", "https://www.imf.org/datamapper")
        return httpx.Response(
            200, json={"values": {"GGXWDG_NGDP": thin}}, request=request
        )

    with patch("main.httpx.get", side_effect=_fetch):
        body = sustainability(client)

    eth = peer(body, "Ethiopia")
    assert eth["debt_to_gdp"] != pytest.approx(27.0)
    assert eth["debt_to_gdp"] is None or eth["debt_to_gdp_year"] != 2031


def test_the_projection_series_continues_the_headline_series(
    client, seeded, imf_datamapper_live
):
    """The chart must start from the figure printed above it.

    The old least-squares line fitted ``DebtTimeline.gdp_ratio`` and so began
    at 70.0, while the headline stated 69.3 on the IMF basis. Now both are
    GGXWDG_NGDP from one vintage: the last actual and the first projection are
    consecutive years of one series.
    """
    body = sustainability(client)
    headline = body["debt_to_gdp"]
    first = body["projections"][0]

    assert first["year"] == headline["year"] + 1
    assert body["projections_source"] == "IMF World Economic Outlook (GGXWDG_NGDP)"
    assert "GGXWDG_NGDP" in headline["basis"]
