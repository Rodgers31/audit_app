"""External debt by creditor (credibility audit F4, and the lender treemap).

The last aggregate-only part of the register. wb_ids.py covered two creditors
and left the rest on fixture rows whose numbers no publisher reports: against
IDS 2024 at KSh 130/USD the site's Eurobond row is 2,276Bn where IDS reports
858Bn (+165%), and syndicated banks 400Bn against 120Bn (+234%). The Eurobond
row alone implied a USD 17.5bn Eurobond stock against an actual 6.6bn.

IDS source 6 carries a Counterpart-Area dimension against which every series
wb_ids.py had written off — bonds, commercial banks, per-country bilateral —
resolves for Kenya. These tests use captured IDS responses so the identity
gates are exercised without the network, and pin what happens when they fail.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from seeding.domains.national_debt.wb_ids_creditors import (
    EXTERNAL_COVERAGE_BAND,
    IdsCreditorError,
    USD_KES_RATE,
    check_external_coverage,
    fetch_creditors,
    latest_year_with_data,
    to_loan_rows,
)


def _record(area_name, area_id, series, value):
    return {
        "variable": [
            {"concept": "Country", "id": "KEN", "value": "Kenya"},
            {"concept": "Time", "id": "YR2024", "value": "2024"},
            {"concept": "Series", "id": series, "value": series},
            {"concept": "Counterpart-Area", "id": area_id, "value": area_name},
        ],
        "value": value,
    }


# Real IDS 2024 values for Kenya, captured 2026-09-03.
IDS_2024 = {
    "DT.DOD.MLAT.CD": [
        ("World", "WLD", 19_994_656_367.0),
        ("World Bank-IDA", "905", 11_872_969_000.0),
        ("African Dev. Bank", "913", 3_892_767_530.0),
        ("World Bank-IBRD", "901", 1_947_156_000.0),
        ("Eastern & Southern African Trade & Dev. Bank", "817", 1_432_372_817.0),
        ("International Fund for Agricultural Dev.", "988", 279_485_695.0),
        ("African Export-Import Bank", "815", 279_022_568.0),
        ("European Investment Bank", "919", 188_757_741.0),
        ("Arab Bank for Economic Dev. in Africa", "953", 44_292_000.0),
        ("OPEC Fund for International Dev.", "951", 21_555_000.0),
        ("Nordic Development Fund", "950", 13_271_948.0),
        ("Arab African International Bank", "922", 8_716_000.0),
        ("Nordic Investment Bank", "969", 8_311_200.0),
        ("European Economic Community (EEC)", "917", 5_978_868.0),
    ],
    "DT.DOD.BLAT.CD": [
        ("World", "WLD", 8_065_996_375.0),
        ("China", "730", 5_600_000_000.0),
        ("Japan", "701", 1_300_000_000.0),
        ("France", "004", 800_000_000.0),
        ("Germany, Fed. Rep. of", "005", 365_996_375.0),
    ],
    "DT.DOD.PBND.CD": [
        ("World", "WLD", 6_600_000_000.0),
        ("Bondholders", "808", 6_600_000_000.0),
    ],
    "DT.DOD.PCBK.CD": [
        ("World", "WLD", 921_891_367.0),
        ("Italy", "006", 419_915_016.0),
        ("South Africa", "216", 194_925_700.0),
        ("Belgium", "002", 307_050_651.0),
    ],
    "DT.DOD.DPPG.CD": [("World", "WLD", 35_582_544_109.0)],
}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeIds:
    """Serves the captured responses; records what was asked for."""

    def __init__(self, data=None, years_with_data=(2024,)):
        self.data = data if data is not None else IDS_2024
        self.years = set(years_with_data)
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        series = url.split("/series/")[1].split("/")[0]
        year = int(url.split("/time/YR")[1].split("?")[0])
        rows = self.data.get(series, []) if year in self.years else []
        return _Resp(
            {"source": {"data": [_record(n, i, series, v) for n, i, v in rows]}}
        )


# ── The pull ─────────────────────────────────────────────────────────────

def test_finds_the_newest_year_with_data():
    """Derived from the API, not hardcoded — IDS runs about a year behind and
    the lag moves. A hardcoded year is how a register quietly freezes."""
    client = FakeIds(years_with_data=(2024,))
    assert latest_year_with_data(client, candidates=[2026, 2025, 2024, 2023]) == 2024


def test_returns_none_when_ids_has_no_year_at_all():
    client = FakeIds(years_with_data=())
    assert latest_year_with_data(client, candidates=[2026, 2025]) is None


def test_pulls_every_creditor_across_the_four_series():
    creditors, checks = fetch_creditors(FakeIds(), 2024)
    # 13 multilateral + 4 bilateral + 1 bondholders + 3 banks
    assert len(creditors) == 21
    assert checks["components_identity"] == "ok"
    categories = {c.debt_category for c in creditors}
    assert categories == {
        "external_multilateral",
        "external_bilateral",
        "external_commercial",
    }


def test_the_world_aggregate_is_never_a_creditor():
    """IDS's World row is the identity check. Publishing it as a creditor
    would double the external book."""
    creditors, _ = fetch_creditors(FakeIds(), 2024)
    assert not any(c.name == "World" for c in creditors)


def test_creditors_the_fixture_never_had():
    """The Trade & Development Bank lends Kenya USD 1.43bn and appears nowhere
    in the fixture's four bilateral and three multilateral buckets."""
    creditors, _ = fetch_creditors(FakeIds(), 2024)
    names = {c.name for c in creditors}
    assert "Eastern & Southern African Trade & Dev. Bank" in names
    assert "African Export-Import Bank" in names


# ── The gates ────────────────────────────────────────────────────────────

def test_gate_1_creditor_rows_must_sum_to_ids_own_world_row():
    broken = {k: list(v) for k, v in IDS_2024.items()}
    # Drop a creditor without adjusting World: the parts no longer make the whole.
    broken["DT.DOD.MLAT.CD"] = [
        r for r in broken["DT.DOD.MLAT.CD"] if r[0] != "African Dev. Bank"
    ]
    with pytest.raises(IdsCreditorError, match="creditor rows sum to"):
        fetch_creditors(FakeIds(broken), 2024)


def test_gate_2_components_must_sum_to_the_ppg_total():
    broken = {k: list(v) for k, v in IDS_2024.items()}
    broken["DT.DOD.DPPG.CD"] = [("World", "WLD", 99_000_000_000.0)]
    with pytest.raises(IdsCreditorError, match="components sum to"):
        fetch_creditors(FakeIds(broken), 2024)


def test_a_series_with_no_world_row_is_refused():
    """Without the aggregate there is nothing to verify the parts against, and
    an unverifiable creditor list must not be published."""
    broken = {k: list(v) for k, v in IDS_2024.items()}
    broken["DT.DOD.BLAT.CD"] = [
        r for r in broken["DT.DOD.BLAT.CD"] if r[0] != "World"
    ]
    with pytest.raises(IdsCreditorError, match="no World row"):
        fetch_creditors(FakeIds(broken), 2024)


def test_gate_3_flags_a_units_or_fx_error():
    """IDS is PPG-only and a year behind, so it should read somewhat LOW
    against a current CBK figure. A ratio far outside that is arithmetic, not
    vintage."""
    creditors, _ = fetch_creditors(FakeIds(), 2024)
    good = check_external_coverage(creditors, 5_462_000_000_000)
    assert good["status"] == "within_band"
    assert 0.60 <= good["coverage_ratio"] <= 1.15

    # A thousand-fold slip — the shape a millions/units confusion takes.
    bad = check_external_coverage(creditors, 5_462_000_000)
    assert bad["status"] == "out_of_band"
    assert "units or exchange-rate error" in bad["reason"]


def test_coverage_is_unchecked_rather_than_assumed():
    creditors, _ = fetch_creditors(FakeIds(), 2024)
    result = check_external_coverage(creditors, None)
    assert result["status"] == "unchecked"
    assert result["coverage_ratio"] is None


def test_the_band_is_a_band():
    low, high = EXTERNAL_COVERAGE_BAND
    assert 0 < low < 1 < high <= 1.5


# ── What gets written ────────────────────────────────────────────────────

def test_loan_rows_carry_their_own_provenance():
    creditors, _ = fetch_creditors(FakeIds(), 2024)
    rows = to_loan_rows(creditors, 2024)
    assert len(rows) == len(creditors)
    for row in rows:
        assert row["debt_category"].startswith("external_")
        assert "International Debt Statistics 2024" in row["notes"]
        assert "counterpart area" in row["notes"]
        assert "130" in row["notes"], "the FX rate used must be on the row"
        assert "publicly guaranteed" in row["notes"], "PPG scope must be stated"


def test_bondholders_are_named_for_what_kenya_issued():
    creditors, _ = fetch_creditors(FakeIds(), 2024)
    rows = to_loan_rows(creditors, 2024)
    bonds = [r for r in rows if r["debt_category"] == "external_commercial"
             and "Eurobond" in r["lender"]]
    assert len(bonds) == 1
    assert bonds[0]["lender"] == "Eurobonds and other international bonds"


def test_the_eurobond_figure_contradicts_what_the_site_publishes():
    """The finding this work exists to fix. The site's Eurobond row is
    KES 2,276Bn; IDS reports USD 6.6bn, which is KES 858Bn."""
    creditors, _ = fetch_creditors(FakeIds(), 2024)
    bonds = [c for c in creditors if c.series == "DT.DOD.PBND.CD"]
    assert len(bonds) == 1
    kes_bn = float(bonds[0].kes) / 1e9
    assert kes_bn == pytest.approx(858.0, abs=1.0)

    site_figure_bn = 2276.0
    assert site_figure_bn > kes_bn * 2.5


def test_usd_is_converted_once_and_the_rate_is_declared():
    creditors, _ = fetch_creditors(FakeIds(), 2024)
    china = next(c for c in creditors if c.name == "China")
    assert china.kes == Decimal(str(china.usd)) * USD_KES_RATE


# ── Replace, never append ────────────────────────────────────────────────

def test_external_fixture_rows_are_replaced_not_joined():
    """The integration decision that matters.

    The fixture's external rows and the IDS creditors describe the SAME debt
    under different names. Appending would count Kenya's Eurobonds twice —
    once at the fixture's 2,276Bn and once at IDS's 858Bn — and give the lender
    treemap two sets of slices for one book. That is the failure the treemap
    was withdrawn over.
    """
    from seeding.domains.national_debt.fetcher import _replace_external_loans

    payload = {
        "loans": [
            {"lender": "Eurobonds (2014, 2018)", "debt_category": "external_commercial",
             "outstanding": 2_276_000_000_000},
            {"lender": "Bilateral (China — Exim Bank / CDB)", "debt_category": "external_bilateral",
             "outstanding": 540_000_000_000},
            {"lender": "Multilateral (World Bank / IDA / IBRD)", "debt_category": "external_multilateral",
             "outstanding": 1_796_616_250_000},
            {"lender": "Domestic Treasury Bonds", "debt_category": "domestic_bonds",
             "outstanding": 5_578_982_400_000},
            {"lender": "Pending Bills — MDAs", "debt_category": "pending_bills",
             "outstanding": 15_800_000_000},
        ]
    }
    creditors, _ = fetch_creditors(FakeIds(), 2024)
    new_rows = to_loan_rows(creditors, 2024)

    result = _replace_external_loans(payload, new_rows)
    lenders = [l["lender"] for l in result["loans"]]

    # Every old external row is gone.
    assert not any("Eurobonds (2014" in l for l in lenders)
    assert not any("Bilateral (China — Exim" in l for l in lenders)
    assert not any("Multilateral (World Bank / IDA" in l for l in lenders)
    # Domestic and pending bills are untouched — this pull owns neither.
    assert "Domestic Treasury Bonds" in lenders
    assert "Pending Bills — MDAs" in lenders
    # And the real creditors are there.
    assert "Eurobonds and other international bonds" in lenders
    assert any("Trade & Dev. Bank" in l for l in lenders)

    # No external category appears twice for the same debt.
    external = [l for l in result["loans"]
                if l["debt_category"].startswith("external_")]
    assert len(external) == len(new_rows)


def test_the_coverage_denominator_is_cbks_own_total_not_the_payload():
    """Gate 3 must check IDS against something independent of IDS.

    It used to sum the loans payload — whose own baseline says its external
    rows are not re-sourced and its total is not published, and which the IDS
    overlay earlier in the same function has already mutated. That compared the
    pull against the fixture it was replacing. It now reads CBK's monthly
    /public-debt/ external figure, and returns None (which quarantines the
    pull) when that is unavailable.
    """
    from seeding.domains.national_debt import fetcher as fx
    from seeding.domains.national_debt.cbk_web_tables import PublicDebtMonth

    rows = [
        PublicDebtMonth(2025, 6, domestic_kes=6.0e12, external_kes=5.0e12, total_kes=11.0e12),
        PublicDebtMonth(2025, 12, domestic_kes=6.8e12, external_kes=5.4e12, total_kes=12.2e12),
        # Fails CBK's own identity: must not be selected even though newest.
        PublicDebtMonth(2026, 1, domestic_kes=1.0e12, external_kes=1.0e12, total_kes=9.9e12),
    ]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(fx, "fetch_public_debt_monthly", lambda c, s: {"rows": rows, "covers": []})

        # Same year as asked for -> the December figure for that year.
        assert fx._cbk_published_external_kes(object(), None, 2025) == pytest.approx(5.4e12)

        # A year the monthly table does not carry must NOT fall back to its
        # newest row: /public-debt/ is frozen at 2021-12, so a 2024 pull
        # measured against it reads 1.20x and quarantines for a reason that is
        # about CBK's website, not the data. It falls through to the CBK
        # Statistical Bulletin series instead, which does publish 2024.
        v2024 = fx._cbk_published_external_kes(object(), None, 2024)
        assert v2024 is not None and v2024 != pytest.approx(5.4e12), v2024

        # Nothing published for the year at all -> None -> quarantine.
        assert fx._cbk_published_external_kes(object(), None, 1975) is None

        def _boom(c, s):
            raise RuntimeError("CBK unreachable")

        mp.setattr(fx, "fetch_public_debt_monthly", _boom)
        # Still resolvable from the Bulletin series for a year it covers.
        assert fx._cbk_published_external_kes(object(), None, 2024) is not None
        assert fx._cbk_published_external_kes(object(), None, 1975) is None


def test_a_failed_pull_leaves_the_fixture_alone(monkeypatch):
    """Quarantine means the old rows stand. A partial creditor list replacing
    a complete aggregate would be worse than not running at all."""
    from seeding.domains.national_debt import wb_ids_creditors as mod

    broken = {k: list(v) for k, v in IDS_2024.items()}
    broken["DT.DOD.DPPG.CD"] = [("World", "WLD", 99_000_000_000.0)]
    assert mod.fetch_external_creditors(FakeIds(broken)) is None


def test_an_out_of_band_pull_is_quarantined():
    from seeding.domains.national_debt import wb_ids_creditors as mod

    # A plausible-looking pull measured against an implausible denominator.
    assert mod.fetch_external_creditors(
        FakeIds(), published_external_kes_for_year=lambda _yr: 5_462_000_000
    ) is None
    # And the same pull against the real one publishes.
    ok = mod.fetch_external_creditors(
        FakeIds(), published_external_kes_for_year=lambda _yr: 5_462_000_000_000
    )
    assert ok is not None and ok["year"] == 2024
    assert len(ok["creditors"]) == 21


# ── Both gates must be able to fire on the shapes that matter ──────────────

def test_a_dropped_creditor_is_caught_even_though_it_is_under_half_a_percent():
    """The identity gate exists to catch omitted rows.

    At 0.5% of the portfolio it tolerated ~USD 100m of missing detail on a
    USD 20bn total, so real creditors could vanish while it still reported
    "identity: ok". IDS publishes at currency precision; the only slack the
    gate needs is rounding.
    """
    import pytest

    from seeding.domains.national_debt.wb_ids_creditors import (
        IdsCreditorError,
        fetch_creditors,
    )

    world_total = 20_000_000_000
    # BADEA-sized: 0.4% of the portfolio, comfortably inside the old tolerance.
    dropped = 80_000_000

    class _Client:
        def get(self, url, **kw):
            raise AssertionError("network must not be reached")

    def _rows(series, year):
        return {
            "World": ("WLD", world_total),
            "International Development Association": ("IDA", world_total - dropped),
        }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "seeding.domains.national_debt.wb_ids_creditors._fetch_series",
            lambda client, series, year: dict(_rows(series, year)),
        )
        with pytest.raises(IdsCreditorError, match="rows are missing"):
            fetch_creditors(_Client(), 2024)


def test_an_unchecked_coverage_result_quarantines_the_pull():
    """A missing denominator must not silently disable gate 3.

    Quarantining only `out_of_band` let `unchecked` through, so a malformed or
    absent baseline turned a mandatory gate into no gate at all. Asserted on
    the CALLER's decision, not on the helper's return value — the helper always
    reported the right status; it was the caller that ignored it.
    """
    import pytest

    from seeding.domains.national_debt import wb_ids_creditors as mod

    creditors = [
        mod.Creditor(
            name="International Development Association",
            counterpart_id="IDA",
            series="DT.DOD.MLAT.CD",
            debt_category="external_multilateral",
            usd=1_000_000_000.0,
        )
    ]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mod, "latest_year_with_data", lambda client: 2024)
        mp.setattr(
            mod, "fetch_creditors", lambda client, year: (creditors, {"series": {}})
        )

        # Denominator absent -> coverage is "unchecked" -> nothing may publish.
        assert mod.check_external_coverage(creditors, None)["status"] != "within_band"
        assert (
            mod.fetch_external_creditors(object(), published_external_kes_for_year=lambda _yr: None) is None
        ), "gate 3 was skipped when there was no independent total to check against"

        # Positive control: with a denominator in band, the pull proceeds.
        in_band = float(creditors[0].kes) / 0.9
        assert (
            mod.fetch_external_creditors(object(), published_external_kes_for_year=lambda _yr: in_band)
            is not None
        )


def test_a_denominator_of_the_wrong_vintage_is_refused():
    """The gate must compare like with like.

    CBK's /public-debt/ page is frozen at 2021-12. Taking its newest row as the
    denominator for a 2024 IDS pull gives a ratio of ~1.20 and quarantines
    every pull — a gate that always fires is as useless as one that never does,
    and it fails for a reason about CBK's website rather than the data.
    """
    from seeding.domains.national_debt import fetcher as fx
    from seeding.domains.national_debt.cbk_web_tables import PublicDebtMonth

    frozen = [
        PublicDebtMonth(2021, 11, domestic_kes=4.008e12, external_kes=4.109e12, total_kes=8.117e12),
        PublicDebtMonth(2021, 12, domestic_kes=4.032e12, external_kes=4.174e12, total_kes=8.207e12),
    ]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            fx, "fetch_public_debt_monthly",
            lambda c, s: {"rows": frozen, "covers": ["1999-09", "2021-12"]},
        )
        denom = fx._cbk_published_external_kes(object(), None, 2024)

    assert denom != pytest.approx(4.174e12), (
        "the 2021 figure was used as the denominator for a 2024 pull"
    )
    # It resolves the vintage-matched Statistical Bulletin figure instead.
    assert denom == pytest.approx(5.057e12, rel=0.01), denom
