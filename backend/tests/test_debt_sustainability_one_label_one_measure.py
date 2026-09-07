"""``/debt/sustainability`` said two different things about Kenya, side by side.

**1. One label, two measures.** The response leads with headline indicators and
then repeats Kenya inside ``regional_peers`` under the same field names, filled
from World Bank series that measure something else::

    debt_service_to_revenue   headline 77.6   peer row 24.3
    external_debt_share       headline 44.4   peer row 35.0

77.6 is total debt service / revenue (FY2026/27, from ``fiscal_summaries``).
24.3 is ``GC.XPN.INTP.RV.ZS`` — **interest payments only**, no principal.
44.4 is external debt as a share of total public debt. 35.0 is
``DT.DOD.DECT.GN.ZS`` — external debt over **GNI**, a different denominator
entirely. Rwanda's 93.9 in that column is the giveaway: no country holds 93.9%
of its public debt externally, but 93.9% of GNI is ordinary.

The peer numbers are real World Bank data and they are comparable *across
countries*. They are simply not the measure the label names. Renaming them is
the whole fix; there is no substitute series to compute the headline's measure
for the peers, so those two columns are withheld rather than filled with the
nearest-looking number.

**1b. The offline fallback was on a third basis.** ``_fallback`` carried
KEN 57.6 / 52.3 for those same two fields — neither the headline's measure nor
the World Bank's. So the number in a given field changed *measure* depending on
whether api.worldbank.org answered, with nothing in the payload saying so.

**2. ``projections`` was a straight line nobody published.** An ordinary
least-squares fit over the last five ``DebtTimeline`` points, emitted as
``projected_debt_to_gdp``: 70.4 / 70.7 / 71.0 / 71.3 / 71.6 — +0.3 every year,
to 2030. The IMF's actual published projection for Kenya, already seeded in
this database and already served by ``/debt/broader``, is 71.6 / 72.4 / 73.3 /
73.6 / 74.2. The line is not merely unpublished; by 2030 it is 2.6 points of
GDP below the projection that does exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from models import DebtTimeline, FiscalSummary, ImfWeoObservation

VINTAGE = datetime(2026, 9, 7, tzinfo=timezone.utc)

#: What api.worldbank.org actually returned for these indicators on 2026-09-06.
WB_LIVE = {
    "GC.XPN.INTP.RV.ZS": {"KEN": 24.3, "ETH": 12.6, "TZA": 13.9,
                          "UGA": 21.0, "RWA": 7.7},
    "DT.DOD.DECT.GN.ZS": {"KEN": 35.0, "ETH": 24.3, "TZA": 47.3,
                          "UGA": 39.2, "RWA": 93.9},
    "GC.DOD.TOTL.GD.ZS": {},
}


@pytest.fixture(autouse=True)
def _reset_peer_cache():
    """``_peers_cache`` is module-level and outlives a test."""
    import main

    main._peers_cache["ts"] = 0.0
    main._peers_cache["data"] = None
    yield
    main._peers_cache["ts"] = 0.0
    main._peers_cache["data"] = None


@pytest.fixture()
def world_bank_live():
    """Serve the real World Bank values without touching the network."""
    with patch("main._wb_fetch_indicator", side_effect=lambda code, _c: WB_LIVE[code]), \
            patch("main._imf_fetch_debt_to_gdp", return_value={}):
        yield


def sustainability(client) -> dict:
    from main import clear_all_caches

    clear_all_caches()
    body = client.get("/api/v1/debt/sustainability").json()
    assert body["status"] == "success", body
    return body


def kenya_row(body: dict) -> dict:
    return next(p for p in body["regional_peers"] if p["country"] == "Kenya")


@pytest.fixture()
def seeded(db_session, seed_source_doc):
    """The production inputs behind 77.6, 44.4 and the OLS line."""
    B = 1e9
    db_session.add(
        FiscalSummary(
            fiscal_year="FY 2026/27",
            total_revenue=3000.0 * B,
            debt_service_cost=2328.0 * B,  # 77.6% of revenue
            unit="KES",
            source_document_id=seed_source_doc.id,
            # Tier B (#137): a published fiscal row cites a page.
            page_ref="s.3.2, report p.16 (PDF p.37)",
        )
    )
    # Five points chosen so the pre-fix least-squares fit reproduces
    # production's published line EXACTLY: 70.4 / 70.7 / 71.0 / 71.3 / 71.6.
    for year, ext, dom, ratio in [
        (2021, 3700.0, 4000.0, 68.9),
        (2022, 4200.0, 4400.0, 69.2),
        (2023, 6089.6, 5050.1, 69.5),
        (2024, 5057.0, 5868.3, 69.8),
        (2025, 5462.0, 6837.5, 70.1),
    ]:
        db_session.add(
            DebtTimeline(
                year=year, external=ext * B, domestic=dom * B,
                total=(ext + dom) * B, gdp_ratio=ratio, unit="KES",
                source_document_id=seed_source_doc.id,
            )
        )
    db_session.commit()
    return db_session


@pytest.fixture()
def imf_projections(db_session):
    """The IMF WEO rows ``/debt/broader`` already serves for Kenya."""
    rows = [(2024, 67.3, False), (2025, 69.3, False), (2026, 71.6, True),
            (2027, 72.4, True), (2028, 73.3, True), (2029, 73.6, True),
            (2030, 74.2, True), (2031, 75.1, True)]
    db_session.add_all([
        ImfWeoObservation(country_code="KEN", indicator="GGXWDG_NGDP", year=y,
                          value=v, is_projection=p, vintage=VINTAGE,
                          source="imf_datamapper")
        for y, v, p in rows
    ])
    db_session.commit()
    return db_session


# ── 1. One label, one measure ──────────────────────────────────────────────

def test_kenya_does_not_appear_twice_with_two_debt_service_numbers(
    client, seeded, world_bank_live
):
    body = sustainability(client)
    headline = body["debt_service_to_revenue"]["value"]
    peer = kenya_row(body)["debt_service_to_revenue"]

    assert headline == pytest.approx(77.6, abs=0.05)
    assert peer is None or peer == pytest.approx(headline, abs=0.05), (
        f"page states debt service to revenue as both {headline} and {peer}"
    )


def test_kenya_does_not_appear_twice_with_two_external_share_numbers(
    client, seeded, world_bank_live
):
    body = sustainability(client)
    headline = body["external_debt_share"]
    peer = kenya_row(body)["external_debt_share"]

    assert headline == pytest.approx(44.4, abs=0.05)
    assert peer is None or peer == pytest.approx(headline, abs=0.05), (
        f"page states external debt share as both {headline} and {peer}"
    )


def test_the_withheld_peer_columns_say_why(client, seeded, world_bank_live):
    row = kenya_row(sustainability(client))
    assert row["debt_service_to_revenue_absent_reason"] == (
        "no_comparable_total_debt_service_series_for_peers"
    )
    assert row["external_debt_share_absent_reason"] == (
        "no_comparable_share_of_total_public_debt_series_for_peers"
    )


def test_the_world_bank_series_are_published_under_their_own_names(
    client, seeded, world_bank_live
):
    """The data is not thrown away — 24.3 and 35.0 are real and comparable.

    They are published as what they are, so a reader cannot mistake either for
    the headline measure.
    """
    body = sustainability(client)
    row = kenya_row(body)
    assert row["interest_payments_pct_revenue"] == pytest.approx(24.3)
    assert row["external_debt_pct_gni"] == pytest.approx(35.0)

    rwanda = next(p for p in body["regional_peers"] if p["country"] == "Rwanda")
    assert rwanda["external_debt_pct_gni"] == pytest.approx(93.9)

    basis = body["regional_peers_basis"]
    assert basis["interest_payments_pct_revenue"]["indicator"] == "GC.XPN.INTP.RV.ZS"
    assert basis["external_debt_pct_gni"]["indicator"] == "DT.DOD.DECT.GN.ZS"


def test_an_unreachable_world_bank_does_not_swap_in_a_different_measure(
    client, seeded
):
    """With the API down, the fallback published 57.6 and 52.3 — a third basis.

    Absence must read as absence, not as a number on a measure the caller never
    asked for.
    """
    with patch("main._wb_fetch_indicator", side_effect=RuntimeError("WB down")), \
            patch("main._imf_fetch_debt_to_gdp", return_value={}):
        row = kenya_row(sustainability(client))

    assert row["interest_payments_pct_revenue"] is None
    assert row["external_debt_pct_gni"] is None
    assert row["debt_to_gdp"] is not None  # positive control: same-measure fallback


# ── 2. Projections must be published, not fitted ───────────────────────────

def test_projections_are_the_imf_series_not_a_straight_line(
    client, seeded, imf_projections
):
    body = sustainability(client)
    values = [p["projected_debt_to_gdp"] for p in body["projections"]]
    years = [p["year"] for p in body["projections"]]

    assert years[:5] == [2026, 2027, 2028, 2029, 2030]
    assert values[:5] == [
        pytest.approx(v) for v in (71.6, 72.4, 73.3, 73.6, 74.2)
    ]

    # The exact pre-fix output for this fixture, pinned so it cannot come back.
    assert values[:5] != [
        pytest.approx(v) for v in (70.4, 70.7, 71.0, 71.3, 71.6)
    ]

    steps = {round(b - a, 2) for a, b in zip(values, values[1:])}
    assert len(steps) > 1, f"still a constant-slope line: {values}"


def test_projections_name_their_publisher(client, seeded, imf_projections):
    body = sustainability(client)
    assert body["projections_source"] == "IMF World Economic Outlook (GGXWDG_NGDP)"
    assert body["projections_absent_reason"] is None
    assert all(p["is_published_projection"] for p in body["projections"])


def test_no_imf_rows_means_no_projections_not_a_fitted_line(client, seeded):
    """The timeline alone can still be extrapolated. It must not be."""
    body = sustainability(client)
    assert body["projections"] == []
    assert body["projections_absent_reason"] == "no_published_projection_seeded"
    assert body["projections_source"] is None
