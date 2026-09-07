"""KSh ~668Bn of IMF credit was deleted from the register on every seed.

``wb_ids.py`` fetched ``DT.DOD.DIMF.CD`` and wrote it as an
``external_multilateral`` row. ``fetcher._replace_external_loans`` then dropped
every external row the IDS creditor pull did not name, and
``writer.reconcile_external_creditors`` deleted the surviving database row. The
creditor pull was built from the ``DT.DOD.DPPG.CD`` components, which exclude
IMF credit by construction — IDS reports it separately — so the row could never
be named, and production carried no IMF row at all.

Nothing failed, because the only thing standing over the external book was a
coverage BAND of 0.60-1.15. With a whole creditor class missing the pull read
94.87% of CBK's published external debt: a comfortable pass.

The fix is a declaration. Every component of ``DT.DOD.DECT.CD`` is named in
``DECT_COMPONENTS`` as carried or excluded-with-a-reason, and the declaration is
checked against IDS's own external total. A component nobody declared makes
that sum short and stops the run.

Values below are the real IDS 2024 observations for Kenya, verified against the
live API on 2026-09-06:

    DT.DOD.DPPG.CD  35.583bn   carried (4 counterpart-area series)
    DT.DOD.DIMF.CD   4.958bn   carried (counterpart 907, IMF)
    DT.DOD.DSTC.CD   2.008bn   excluded — short-term, all sectors
    DT.DOD.DPNG.CD   0.338bn   excluded — private non-guaranteed
    DT.DOD.DECT.CD  42.886bn   == the sum of the four, to the cent
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from seeding.domains.national_debt import wb_ids_creditors as mod
from seeding.domains.national_debt.wb_ids_creditors import (
    IdsCreditorError,
    check_external_coverage,
    fetch_creditors,
    to_loan_rows,
)

# DECT_COMPONENTS / EXTERNAL_TOTAL_SERIES are reached through ``mod`` rather
# than imported at module level, so that against a build without them each
# test fails on its own assertion instead of the whole file failing to
# collect. A defect has to be visible test by test to count as a red run.

#: PA.NUS.FCRF for 2024 — the rate the pipeline converts a 2024 stock at.
IDS_TEST_RATE = Decimal("134.822483279332")

#: CBK Statistical Bulletin Dec 2025, Table 4.1.3: external public debt, 2024.
#: The coverage gate's denominator for a 2024 pull.
CBK_EXTERNAL_2024_KES = 5_057_000_000_000

DPPG_USD = 35_582_544_109.0
DIMF_USD = 4_958_198_572.8
DSTC_USD = 2_007_772_843.5
DPNG_USD = 337_611_692.6
DECT_USD = 42_886_127_218.3


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
    "DT.DOD.DPPG.CD": [("World", "WLD", DPPG_USD)],
    # Real: IDS breaks IMF credit out by counterpart area like anything else.
    "DT.DOD.DIMF.CD": [
        ("World", "WLD", DIMF_USD),
        ("International Monetary Fund", "907", DIMF_USD),
    ],
    "DT.DOD.DSTC.CD": [("World", "WLD", DSTC_USD)],
    "DT.DOD.DPNG.CD": [("World", "WLD", DPNG_USD)],
    "DT.DOD.DECT.CD": [("World", "WLD", DECT_USD)],
}


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


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeIds:
    """Serves the captured 2024 responses; records what was asked for."""

    def __init__(self, data=None, years_with_data=(2024,)):
        self.data = data if data is not None else IDS_2024
        self.years = set(years_with_data)
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        if "PA.NUS.FCRF" in url:
            return _Resp(
                [{"page": 1}, [{"date": "2024", "value": float(IDS_TEST_RATE)}]]
            )
        series = url.split("/series/")[1].split("/")[0]
        year = int(url.split("/time/YR")[1].split("?")[0])
        rows = self.data.get(series, []) if year in self.years else []
        return _Resp(
            {"source": {"data": [_record(n, i, series, v) for n, i, v in rows]}}
        )


def _broken(**overrides):
    data = {k: list(v) for k, v in IDS_2024.items()}
    data.update(overrides)
    return data


# ── The money: IMF credit is in the register ─────────────────────────────


def test_imf_credit_is_pulled_as_a_creditor():
    """USD 4.958bn of real national-government liability that the DPPG
    components cannot see, because IDS reports it outside them."""
    creditors, _checks = fetch_creditors(FakeIds(), 2024, IDS_TEST_RATE)
    imf = [c for c in creditors if c.series == "DT.DOD.DIMF.CD"]
    assert len(imf) == 1, (
        "no IMF creditor in the pull — the DPPG components exclude IMF credit "
        "by construction, so it has to be carried as its own component"
    )
    assert imf[0].name == "International Monetary Fund"
    assert imf[0].counterpart_id == "907"
    assert imf[0].debt_category == "external_multilateral"
    assert imf[0].usd == pytest.approx(DIMF_USD)


def test_imf_credit_is_worth_the_668bn_the_register_was_missing():
    creditors, _ = fetch_creditors(FakeIds(), 2024, IDS_TEST_RATE)
    imf = next(c for c in creditors if c.series == "DT.DOD.DIMF.CD")
    kes_bn = float(imf.kes) / 1e9
    assert kes_bn == pytest.approx(668.4, abs=1.0), kes_bn


def test_imf_credit_survives_the_external_replacement():
    """Where it was actually lost.

    ``_replace_external_loans`` drops every fixture row in the external
    categories and keeps only what the creditor pull names. When the pull did
    not name the IMF, the row ``wb_ids.py`` had just written was deleted — and
    ``writer.reconcile_external_creditors`` then deleted the database row too.
    """
    from seeding.domains.national_debt.fetcher import _replace_external_loans

    payload = {
        "loans": [
            {
                "lender": "Multilateral (IMF — Extended Credit & Resilience Trust)",
                "debt_category": "external_multilateral",
                "outstanding": 668_400_000_000,
            },
            {
                "lender": "Domestic Treasury Bonds",
                "debt_category": "domestic_bonds",
                "outstanding": 5_578_982_400_000,
            },
        ]
    }
    creditors, _ = fetch_creditors(FakeIds(), 2024, IDS_TEST_RATE)
    result = _replace_external_loans(payload, to_loan_rows(creditors, 2024))
    lenders = [l["lender"] for l in result["loans"]]

    assert "Multilateral (IMF — Extended Credit & Resilience Trust)" not in lenders
    assert any("International Monetary Fund" in l for l in lenders), (
        "the external replacement deleted IMF credit and put nothing back: "
        f"{[l for l in lenders if 'Multilateral' in l]}"
    )
    # Exactly one IMF row — replaced, not appended beside the fixture's.
    assert sum("International Monetary Fund" in l for l in lenders) == 1


def test_the_imf_row_does_not_claim_to_be_publicly_guaranteed_debt():
    """It is not. IDS reports use of IMF credit outside the PPG aggregate, and
    a row that says otherwise is a false citation on the register."""
    creditors, _ = fetch_creditors(FakeIds(), 2024, IDS_TEST_RATE)
    rows = to_loan_rows(creditors, 2024)
    imf = next(r for r in rows if "International Monetary Fund" in r["lender"])
    assert "Use of IMF credit" in imf["notes"]
    assert "DT.DOD.DIMF.CD" in imf["notes"]
    assert "counterpart area 907" in imf["notes"]

    ppg_row = next(r for r in rows if "China" in r["lender"])
    assert ppg_row["notes"].endswith(
        "Public and publicly guaranteed external debt only."
    )


# ── The gate: every component declared, or the run stops ─────────────────


def test_the_declared_components_must_be_ids_own_external_total():
    """Gate 3. IDS publishes a component the register does not name — the
    declaration is short and the run fails rather than publishing a book with
    a hole in it."""
    creditors, checks = fetch_creditors(FakeIds(), 2024, IDS_TEST_RATE)
    assert checks["declaration_identity"] == "ok"
    assert checks["external_total_usd"] == pytest.approx(DECT_USD)
    assert checks["declared_total_usd"] == pytest.approx(DECT_USD, abs=5.0)

    # IDS starts publishing another USD 1bn of external debt under a component
    # nobody declared.
    with pytest.raises(IdsCreditorError, match="neither carried nor excluded"):
        fetch_creditors(
            FakeIds(_broken(**{"DT.DOD.DECT.CD": [("World", "WLD", DECT_USD + 1e9)]})),
            2024,
            IDS_TEST_RATE,
        )


def test_the_historical_declaration_is_exactly_what_the_gate_catches(monkeypatch):
    """The regression, stated as the shape it had.

    Pin the declaration back to what shipped for twenty runs — DPPG only, IMF
    undeclared — and the run must stop. This is the check the coverage band
    could not perform.
    """
    ppg_only = tuple(
        c for c in mod.DECT_COMPONENTS if c.series == "DT.DOD.DPPG.CD"
    )
    monkeypatch.setattr(mod, "DECT_COMPONENTS", ppg_only)

    with pytest.raises(IdsCreditorError, match="neither carried nor excluded") as exc:
        fetch_creditors(FakeIds(), 2024, IDS_TEST_RATE)
    # And it says how much is unaccounted for, in dollars, not a percentage.
    assert "7,303,583,109" in str(exc.value) or "7,303,583,110" in str(exc.value), (
        str(exc.value)
    )


def test_the_coverage_band_cannot_see_a_missing_creditor_class():
    """Why nothing fired for twenty runs, held as a characterisation.

    The band was set wide on purpose — IDS is annual and a year behind — but
    that width is wider than a missing 12% creditor class. Carrying only DPPG
    reads 94.9% of CBK's published external debt and passes.
    """
    creditors, _ = fetch_creditors(FakeIds(), 2024, IDS_TEST_RATE)
    ppg_only = [c for c in creditors if c.series != "DT.DOD.DIMF.CD"]

    with_the_hole = check_external_coverage(ppg_only, CBK_EXTERNAL_2024_KES)
    assert with_the_hole["status"] == "within_band"
    assert with_the_hole["coverage_ratio"] == pytest.approx(0.949, abs=0.005)

    # The band still passes with IMF carried, so it never distinguished them.
    complete = check_external_coverage(creditors, CBK_EXTERNAL_2024_KES)
    assert complete["status"] == "within_band"
    assert complete["coverage_ratio"] > with_the_hole["coverage_ratio"]


def test_excluded_components_are_named_with_a_reason_and_a_size():
    """"Excluded" has to mean somebody decided, and a reader has to be able to
    see how much was left out. A component silently absent is the defect."""
    _creditors, checks = fetch_creditors(FakeIds(), 2024, IDS_TEST_RATE)
    components = checks["components"]

    assert set(components) == {c.series for c in mod.DECT_COMPONENTS}
    for series, entry in components.items():
        assert entry["disposition"] in {"carried", "excluded"}
        assert entry["reason"], f"{series} has no stated reason"
        assert entry["world_usd"] > 0

    short_term = components["DT.DOD.DSTC.CD"]
    assert short_term["disposition"] == "excluded"
    assert short_term["world_usd"] == pytest.approx(DSTC_USD)
    assert "all sectors" in short_term["reason"].lower()

    private = components["DT.DOD.DPNG.CD"]
    assert private["disposition"] == "excluded"
    assert "not a public liability" in private["reason"]

    assert checks["carried_total_usd"] == pytest.approx(DPPG_USD + DIMF_USD)
    assert checks["excluded_total_usd"] == pytest.approx(DSTC_USD + DPNG_USD)


def test_there_is_no_third_state_for_a_component():
    for component in mod.DECT_COMPONENTS:
        assert component.reason, f"{component.series} declares no reason"
        if component.carried:
            assert component.creditor_series, (
                f"{component.series} is carried but names no creditor series"
            )
            assert component.row_note, (
                f"{component.series} is carried but states no basis for its rows"
            )
        else:
            assert not component.creditor_series


def test_a_component_whose_parts_do_not_make_it_up_is_refused():
    """Gate 2, now at rounding precision rather than 0.5%.

    0.5% of DPPG is USD 178m — about KSh 24Bn — which is more than enough room
    to lose a real creditor while still reporting "identity: ok".
    """
    missing_178m = _broken(
        **{"DT.DOD.DPPG.CD": [("World", "WLD", DPPG_USD + 178_000_000)]}
    )
    with pytest.raises(IdsCreditorError, match="components sum to"):
        fetch_creditors(FakeIds(missing_178m), 2024, IDS_TEST_RATE)


def test_the_imf_component_is_checked_against_its_own_world_row():
    """Gate 1 and gate 2 apply to IMF credit like any other component."""
    broken = _broken(
        **{
            "DT.DOD.DIMF.CD": [
                ("World", "WLD", DIMF_USD),
                ("International Monetary Fund", "907", DIMF_USD - 500_000_000),
            ]
        }
    )
    with pytest.raises(IdsCreditorError, match="creditor rows sum to"):
        fetch_creditors(FakeIds(broken), 2024, IDS_TEST_RATE)


def test_a_component_with_no_world_row_stops_the_run():
    broken = _broken(**{mod.EXTERNAL_TOTAL_SERIES: []})
    with pytest.raises(IdsCreditorError, match="no World row"):
        fetch_creditors(FakeIds(broken), 2024, IDS_TEST_RATE)


def test_an_excluded_component_ids_stops_publishing_is_gate_3s_call():
    """Not a reason to quarantine on its own.

    If the series really went to zero, the declaration still sums to DECT and
    the run proceeds. If it did not, gate 3 fails and names the amount. Failing
    here instead would take the register down over a series we do not carry.
    """
    # Really zero: DSTC gone AND DECT reduced by the same amount.
    went_to_zero = _broken(
        **{
            "DT.DOD.DSTC.CD": [],
            "DT.DOD.DECT.CD": [("World", "WLD", DECT_USD - DSTC_USD)],
        }
    )
    _creditors, checks = fetch_creditors(FakeIds(went_to_zero), 2024, IDS_TEST_RATE)
    entry = checks["components"]["DT.DOD.DSTC.CD"]
    assert entry["disposition"] == "excluded"
    assert entry["world_usd"] == 0.0
    assert entry["published"] is False

    # Unfetchable but still real: DECT unchanged, so the declaration is short.
    with pytest.raises(IdsCreditorError, match="neither carried nor excluded"):
        fetch_creditors(
            FakeIds(_broken(**{"DT.DOD.DSTC.CD": []})), 2024, IDS_TEST_RATE
        )


# ── End to end ───────────────────────────────────────────────────────────


def test_the_whole_gated_pull_carries_imf_credit():
    result = mod.fetch_external_creditors(
        FakeIds(),
        published_external_kes_for_year=lambda _yr: CBK_EXTERNAL_2024_KES,
    )
    assert result is not None, "the pull was quarantined"
    assert result["year"] == 2024
    lenders = [r["lender"] for r in result["loans"]]
    assert any("International Monetary Fund" in l for l in lenders)
    # 21 PPG creditors + the IMF.
    assert len(result["creditors"]) == 22
    assert result["checks"]["declaration_identity"] == "ok"


def test_the_external_book_reconciles_to_ids_carried_total():
    """The shilling figure the register publishes for external debt."""
    creditors, checks = fetch_creditors(FakeIds(), 2024, IDS_TEST_RATE)
    total_kes = float(sum(c.kes for c in creditors))
    expected = (DPPG_USD + DIMF_USD) * float(IDS_TEST_RATE)
    assert total_kes == pytest.approx(expected, rel=1e-9)
    assert total_kes / 1e9 == pytest.approx(5_465.7, abs=1.0)
    assert checks["carried_total_usd"] == pytest.approx(DPPG_USD + DIMF_USD)
