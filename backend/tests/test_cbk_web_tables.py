"""The CBK instrument-level extractor, against the real pages.

Fixtures in tests/fixtures/cbk/ are the live centralbank.go.ke tables captured
on 2026-09-03, trimmed to the parsed table with every data row preserved. The
house rule that produced them: confirm parser anchors against the real
document, because the last three parser bugs in this repo were all anchors
written from documentation the real page does not use.

What the extractor unblocks:

  * The maturity ladder, withdrawn because 3 of 28 register rows carried a
    maturity date and five Eurobond issues sat on one 2034 date (F24). The
    real table carries maturities from 2026 to 2047.
  * The flat 14.5% coupon assumed across the whole bond book, from which the
    site derived "ANNUAL SERVICE COST KES 1.27T" (F42). Every security here
    carries its own coupon.
  * The 2013-2021 debt timeline, nine round-number years attributed to CBK
    (F13). CBK's own monthly table publishes December 2013 at KSh 2,111.6bn
    against the fixture's 3,100bn.
"""

from __future__ import annotations

import pathlib
from datetime import date

import pytest
from seeding.domains.national_debt.cbk_web_tables import (
    AMBIGUITY_AMORTISING,
    AMBIGUITY_ODD_MATURITY,
    AMBIGUITY_REUSED_ISIN,
    BOND_COVERAGE_BAND,
    CbkTableError,
    check_bond_coverage,
    december_series,
    outstanding_securities,
    parse_bond_register,
    parse_public_debt_monthly,
    partition_ambiguous,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "cbk"
AS_OF = date(2026, 9, 3)


@pytest.fixture(scope="module")
def bonds_html() -> str:
    return (FIXTURES / "treasury_bonds.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def public_debt_html() -> str:
    return (FIXTURES / "public_debt_monthly.html").read_text(encoding="utf-8")


# ── The bond register ─────────────────────────────────────────────────────

def test_parses_every_usable_tranche_row(bonds_html):
    tranches = parse_bond_register(bonds_html)
    # 333 rows on the page; 4 carry a blank issue date and are dropped.
    assert len(tranches) == 329


def test_a_known_row_parses_exactly(bonds_html):
    """Pinned against the real first row, so a column shift is caught."""
    first = parse_bond_register(bonds_html)[0]
    assert first.issue_no == "FXD1/2010/10"
    assert first.isin == "KE1000001921"
    assert first.issue_date == date(2010, 4, 26)
    assert first.maturity_date == date(2020, 4, 13)
    assert first.coupon_rate == pytest.approx(8.79)
    # "Face Value (Kshs Millions)" 12052.6 -> whole shillings.
    assert first.face_value_kes == pytest.approx(12_052_600_000)


def test_matured_bonds_are_excluded(bonds_html):
    securities = outstanding_securities(parse_bond_register(bonds_html), as_of=AS_OF)
    assert securities, "expected outstanding securities"
    assert all(s.maturity_date > AS_OF for s in securities)
    # The 2020 maturities in the table must not survive.
    assert not any(s.maturity_date.year == 2020 for s in securities)


def test_reopenings_are_summed_into_one_security(bonds_html):
    """FXD1/2010/10 and FXD1/2010/10(R1) are the same ISIN. A register that
    lists them separately double-counts the security and puts two bars on the
    ladder where there is one bond."""
    tranches = parse_bond_register(bonds_html)
    isins = [t.isin for t in tranches]
    assert len(isins) > len(set(isins)), "fixture should contain reopenings"

    securities = outstanding_securities(tranches, as_of=AS_OF)
    # Keyed on (ISIN, maturity): unique per redemption line, and unique per
    # ISIN once the ambiguous ones are partitioned out.
    publishable, _ = partition_ambiguous(securities)
    assert len({s.isin for s in publishable}) == len(publishable)
    multi = [s for s in securities if s.tranches > 1]
    assert multi, "expected at least one security built from several tranches"
    for s in multi:
        contributing = [
            t for t in tranches
            if t.isin == s.isin
            and t.maturity_date == s.maturity_date
            and t.maturity_date > AS_OF
        ]
        assert s.face_value_kes == pytest.approx(
            sum(t.face_value_kes for t in contributing)
        )


def test_the_register_carries_real_maturities_and_coupons(bonds_html):
    """The two things the withdrawn ladder and service-cost figure needed."""
    securities = outstanding_securities(parse_bond_register(bonds_html), as_of=AS_OF)
    years = sorted({s.maturity_date.year for s in securities})
    assert len(years) >= 15, f"expected a real spread of maturities, got {years}"
    assert min(years) >= 2026 and max(years) >= 2040

    coupons = [s.coupon_rate for s in securities if s.coupon_rate is not None]
    assert len(coupons) == len(securities), "every security must carry a coupon"
    assert len(set(coupons)) > 20, (
        "coupons must vary by security — the site previously applied one "
        "assumed 14.5% to the whole book"
    )
    assert all(0 < c < 30 for c in coupons)


def test_instrument_types_are_classified(bonds_html):
    securities = outstanding_securities(parse_bond_register(bonds_html), as_of=AS_OF)
    kinds = {s.instrument_type for s in securities}
    assert "fixed_coupon_bond" in kinds
    assert "infrastructure_bond" in kinds, (
        "IFB issues must be distinguishable — they are tax-free and were "
        "previously shown as a separate KES 300B aggregate row"
    )


# ── The coverage gate ─────────────────────────────────────────────────────

def test_coverage_against_the_published_stock_is_reported(bonds_html):
    securities = outstanding_securities(parse_bond_register(bonds_html), as_of=AS_OF)
    # CBK Statistical Bulletin Table 4.1.4, December 2025.
    published = 5_579_000_000_000
    result = check_bond_coverage(securities, published)
    assert result["status"] == "within_band"
    assert 0.70 <= result["coverage_ratio"] <= 0.80, result


def test_a_partial_register_is_quarantined_not_published():
    """The gate's whole purpose. A register covering a fraction of the stock
    cannot describe the maturity profile of the book, and must not be
    presented as if it could."""
    from seeding.domains.national_debt.cbk_web_tables import BondSecurity

    tiny = [
        BondSecurity(
            isin="KE0000000001", issue_no="FXD1/2020/10",
            maturity_date=date(2030, 1, 1), coupon_rate=12.0, tenor_years=10,
            face_value_kes=1_000_000_000, tranches=1, first_issued=date(2020, 1, 1),
        )
    ]
    result = check_bond_coverage(tiny, 5_579_000_000_000)
    assert result["status"] == "out_of_band"
    assert "outside" in result["reason"]


def test_coverage_is_unchecked_rather_than_assumed_when_there_is_nothing_to_check():
    from seeding.domains.national_debt.cbk_web_tables import BondSecurity

    one = [
        BondSecurity(
            isin="KE0000000001", issue_no="FXD1/2020/10",
            maturity_date=date(2030, 1, 1), coupon_rate=12.0, tenor_years=10,
            face_value_kes=1_000_000_000, tranches=1, first_issued=date(2020, 1, 1),
        )
    ]
    result = check_bond_coverage(one, None)
    assert result["status"] == "unchecked"
    assert result["coverage_ratio"] is None


# ── The monthly public-debt series ────────────────────────────────────────

def test_parses_the_monthly_series(public_debt_html):
    rows = parse_public_debt_monthly(public_debt_html)
    assert len(rows) >= 250
    assert rows[0].year == 1999
    assert rows[-1].year == 2021


def test_every_published_row_satisfies_cbks_own_identity(public_debt_html):
    """domestic + external = total. A row that fails is dropped at parse time,
    so anything that survives must hold — this is what let the 2026-08-29
    correction trust its own output."""
    for row in parse_public_debt_monthly(public_debt_html):
        assert row.identity_holds(), (row.year, row.month)


def test_december_2013_contradicts_the_fixture(public_debt_html):
    """The finding this series exists to fix.

    The debt timeline publishes 2013 as KSh 3,100bn. CBK publishes 2,111.6bn —
    46.8% lower. The site's "4.0x since 2013" headline was computed against a
    base that was never real; on CBK's own figure the multiple is ~5.8x.
    """
    dec = december_series(parse_public_debt_monthly(public_debt_html))
    assert 2013 in dec
    cbk_2013 = dec[2013].total_kes
    assert cbk_2013 == pytest.approx(2_111_600_000_000, rel=0.001)

    fixture_2013 = 3_100_000_000_000
    assert fixture_2013 > cbk_2013 * 1.4

    latest_total = 12_299_476_400_000  # debt_timeline 2025, CBK-sourced
    assert latest_total / fixture_2013 == pytest.approx(3.97, abs=0.05)
    assert latest_total / cbk_2013 == pytest.approx(5.82, abs=0.05)


def test_the_series_covers_every_fabricated_year(public_debt_html):
    """2013-2021 are the round-number rows. All nine must be replaceable."""
    dec = december_series(parse_public_debt_monthly(public_debt_html))
    for year in range(2013, 2022):
        assert year in dec, f"no CBK December reading for {year}"
        assert dec[year].total_kes > 0


# ── Refusing to parse something we would get wrong ───────────────────────

def test_server_side_paging_is_refused(bonds_html):
    """If CBK switches these tables to server-side paging the HTML holds one
    page of rows, and we would publish a register missing most of its
    instruments while it looked complete."""
    paged = bonds_html.replace('"serverSide":false', '"serverSide":true')
    with pytest.raises(CbkTableError, match="server-side paging"):
        parse_bond_register(paged)


def test_a_missing_table_raises_rather_than_returning_nothing(public_debt_html):
    """A renamed or removed table must not read as 'no debt data published'."""
    with pytest.raises(CbkTableError, match="headers"):
        parse_bond_register(public_debt_html)


def test_the_band_is_a_band_not_a_rubber_stamp():
    low, high = BOND_COVERAGE_BAND
    assert 0 < low < high
    assert high <= 1.10, "a band that accepts any coverage is not a gate"


# ── The fixture must now match the source it cites ───────────────────────

def test_the_debt_timeline_fixture_matches_cbks_own_readings(public_debt_html):
    """The correction, pinned.

    debt_timeline.json cites CBK for 2013-2021. Before this change none of
    those nine rows matched anything CBK publishes — they were round hundreds
    of billions. This asserts the fixture now agrees with the table it names,
    so a future edit that reintroduces a tidy number fails here.
    """
    import json
    import pathlib

    fixture = json.loads(
        (
            pathlib.Path(__file__).parents[1]
            / "seeding" / "real_data" / "debt_timeline.json"
        ).read_text(encoding="utf-8")
    )
    dec = december_series(parse_public_debt_monthly(public_debt_html))
    B = 1_000_000_000

    checked = 0
    for row in fixture["timeline"]:
        year = row["year"]
        if year not in dec or year > 2021:
            continue
        cbk = dec[year]
        assert row["total"] == pytest.approx(cbk.total_kes / B, rel=0.001), year
        assert row["domestic"] == pytest.approx(cbk.domestic_kes / B, rel=0.001), year
        assert row["external"] == pytest.approx(cbk.external_kes / B, rel=0.001), year
        # And the identity has to survive the round-trip into the fixture.
        assert row["domestic"] + row["external"] == pytest.approx(
            row["total"], rel=0.001
        ), year
        checked += 1
    assert checked == 9, f"expected all nine replaced years, checked {checked}"


def test_no_timeline_row_is_a_round_hundred_billion():
    """The signature that identified the fabrication in the first place: every
    component landing exactly on 100Bn at once. Mirrors isRoundNumberEstimate
    in NationalDebtCard.tsx."""
    import json
    import pathlib

    fixture = json.loads(
        (
            pathlib.Path(__file__).parents[1]
            / "seeding" / "real_data" / "debt_timeline.json"
        ).read_text(encoding="utf-8")
    )
    offenders = [
        row["year"]
        for row in fixture["timeline"]
        if all(
            row.get(k) and float(row[k]) % 100 == 0
            for k in ("external", "domestic", "total")
        )
    ]
    assert not offenders, (
        f"years {offenders} are round hundreds of billions across every "
        "component at once — no CBK table produces that"
    )


def test_a_row_failing_cbks_identity_is_actually_dropped(public_debt_html):
    """The positive control for the identity filter.

    `test_every_published_row_satisfies_cbks_own_identity` passes whether or
    not the filter exists, because every real CBK row already satisfies the
    identity — it asserts a property of the data, not of the code. Disabling
    the filter left the whole suite green.

    This injects a row where domestic + external != total and requires that it
    does not survive. Without it the filter could be deleted and nothing would
    notice until a mis-parsed row became a published figure.
    """
    good = parse_public_debt_monthly(public_debt_html)
    before = len(good)
    assert not any(r.year == 1998 for r in good), "1998 is free for the probe"

    bad_row = (
        '<tr id="probe_row">'
        "<td>1998</td><td>December</td>"
        "<td>100,000.00</td><td>100,000.00</td><td>900,000.00</td>"
        "</tr>"
    )
    tampered = public_debt_html.replace("<tbody>", "<tbody>" + bad_row, 1)
    assert bad_row in tampered, "probe row was not injected"

    after = parse_public_debt_monthly(tampered)
    assert len(after) == before, "the row that breaks the identity was published"
    assert not any(r.year == 1998 for r in after)


def test_the_identity_probe_would_pass_if_it_balanced(public_debt_html):
    """And the filter must not simply reject everything it is given: the same
    injected row, made to balance, has to come through."""
    before = len(parse_public_debt_monthly(public_debt_html))
    ok_row = (
        '<tr id="probe_row">'
        "<td>1998</td><td>December</td>"
        "<td>100,000.00</td><td>100,000.00</td><td>200,000.00</td>"
        "</tr>"
    )
    tampered = public_debt_html.replace("<tbody>", "<tbody>" + ok_row, 1)
    after = parse_public_debt_monthly(tampered)
    assert len(after) == before + 1
    probe = [r for r in after if r.year == 1998]
    assert len(probe) == 1 and probe[0].identity_holds()


# ── The fetcher's use of the register ────────────────────────────────────

def test_the_register_is_never_summed_into_the_debt_total(bonds_html):
    """The rule the coverage gate exists to enforce.

    The register covers ~74% of CBK's published bond stock. Adding it to the
    debt total, or letting it replace the aggregate T-bond row, would trade a
    correct total for a lower wrong one — the exact shape of the finding that
    started this work, where a 28-row register was published as though it were
    Kenya's debt. It rides alongside as a maturity/coupon profile, and carries
    the coverage ratio so a consumer cannot mistake it for a stock measure.
    """
    from seeding.domains.national_debt.fetcher import _published_bond_stock_kes

    securities = outstanding_securities(parse_bond_register(bonds_html), as_of=AS_OF)
    payload = {
        "loans": [
            {"lender": "Domestic Treasury Bonds", "outstanding": 5_578_982_400_000},
            {"lender": "Domestic Infrastructure & Green Bonds", "outstanding": 300_000_000_000},
            {"lender": "Eurobonds (2014, 2018)", "outstanding": 2_276_000_000_000},
        ]
    }
    stock = _published_bond_stock_kes(payload)
    # 5.579T, NOT 5.879T. CBK's "Domestic Treasury Bonds" line already includes
    # infrastructure and green bonds — the payload's own note on that row says
    # so — while the payload also carries them as a separate KES 300B row.
    # Summing both counted them twice and inflated the coverage denominator.
    assert stock == pytest.approx(5_578_982_400_000), (
        "the inclusive Treasury-bond aggregate only: adding the separate "
        "infrastructure/green row double-counts bonds already inside it"
    )
    assert stock != pytest.approx(5_878_982_400_000), "the 300B double count is back"

    coverage = check_bond_coverage(securities, stock)
    assert coverage["status"] == "within_band"
    # The register is materially SMALLER than the published stock. That gap is
    # the reason it is a profile and not a total.
    assert coverage["register_total_kes"] < stock * 0.85


def test_the_published_stock_denominator_moves_with_the_data():
    """Measured against CBK's own rows, not a constant — so republishing the
    bond stock moves the denominator instead of silently failing the gate."""
    from seeding.domains.national_debt.fetcher import _published_bond_stock_kes

    assert _published_bond_stock_kes({"loans": []}) is None
    assert _published_bond_stock_kes(
        {"loans": [{"lender": "Domestic Treasury Bonds", "outstanding": 1_000}]}
    ) == 1_000
    # A creditor that is not a bond must not inflate it.
    assert _published_bond_stock_kes(
        {"loans": [{"lender": "CBK Overdraft Facility", "outstanding": 99}]}
    ) is None
    # Eurobonds are external commercial debt, not part of the domestic book.
    assert _published_bond_stock_kes(
        {"loans": [{"lender": "Eurobonds (2014, 2018)", "outstanding": 2_276_000_000_000}]}
    ) is None
    # Infrastructure bonds ARE Treasury bonds in CBK's classification — which
    # is exactly why the separate row must NOT be added: the aggregate
    # "Domestic Treasury Bonds" line already contains them (see that row's own
    # note in national_debt.json). Counting the standalone row as well
    # double-counts KES 300B of the same bonds.
    assert _published_bond_stock_kes(
        {"loans": [{"lender": "Domestic Infrastructure & Green Bonds", "outstanding": 300}]}
    ) is None
    # And it must not add to the aggregate that already includes it.
    assert _published_bond_stock_kes(
        {
            "loans": [
                {"lender": "Domestic Treasury Bonds", "outstanding": 1_000},
                {"lender": "Domestic Infrastructure & Green Bonds", "outstanding": 300},
            ]
        }
    ) == 1_000


# ── Ambiguous ISINs: withheld, with the reason ───────────────────────────

def test_the_three_kinds_of_ambiguity_are_told_apart(bonds_html):
    """Reading the real table found three separate reasons an ISIN carries two
    maturities. Collapsing them to one rule got the ladder wrong: on an
    ISIN key, 2027 jumped from 260Bn to 575Bn because amortising tranches
    landed on the earliest date."""
    securities = outstanding_securities(parse_bond_register(bonds_html), as_of=AS_OF)
    publishable, withheld = partition_ambiguous(securities)

    assert len(withheld) == 6, sorted(withheld)
    reasons = {v["reason"] for v in withheld.values()}
    assert reasons == {
        AMBIGUITY_REUSED_ISIN,
        AMBIGUITY_AMORTISING,
        AMBIGUITY_ODD_MATURITY,
    }, reasons

    # KE4000003808 is one ISIN over two securities: FXD2/2013/015 maturing
    # 2028 at 12.0%, and FXD2/2018/015 maturing 2033 at 12.75%.
    assert withheld["KE4000003808"]["reason"] == AMBIGUITY_REUSED_ISIN
    # KE8000005549 is IFB1/2023/017, amortising across 2033 and 2040.
    assert withheld["KE8000005549"]["reason"] == AMBIGUITY_AMORTISING


def test_withheld_isins_do_not_appear_in_the_publishable_register(bonds_html):
    securities = outstanding_securities(parse_bond_register(bonds_html), as_of=AS_OF)
    publishable, withheld = partition_ambiguous(securities)
    assert not ({s.isin for s in publishable} & set(withheld))
    assert len(publishable) == len({s.isin for s in publishable})


def test_the_withheld_amount_is_reported_not_just_dropped(bonds_html):
    """About 15% of the register's face value. Silently dropping it would make
    the coverage ratio look worse for no stated reason; publishing it would put
    money in a year it does not fall due."""
    securities = outstanding_securities(parse_bond_register(bonds_html), as_of=AS_OF)
    publishable, withheld = partition_ambiguous(securities)
    withheld_face = sum(v["face_value_kes"] for v in withheld.values())
    total_face = sum(s.face_value_kes for s in securities)
    assert withheld_face > 0
    assert 0.10 < withheld_face / total_face < 0.20
    for isin, info in withheld.items():
        assert info["reason"], isin
        assert len(info["maturities"]) > 1, isin


def test_partition_keeps_an_unambiguous_register_whole():
    """The positive control: a register with no conflicts loses nothing."""
    from seeding.domains.national_debt.cbk_web_tables import BondSecurity

    clean = [
        BondSecurity(
            isin=f"KE000000000{i}", issue_no=f"FXD{i}/2020/10",
            maturity_date=date(2030 + i, 1, 1), coupon_rate=12.0, tenor_years=10,
            face_value_kes=1e9, tranches=1, first_issued=date(2020, 1, 1),
        )
        for i in range(1, 5)
    ]
    publishable, withheld = partition_ambiguous(clean)
    assert len(publishable) == 4 and withheld == {}


def test_an_unknown_paging_configuration_is_quarantined_not_assumed_complete():
    """The guard must require the invariant, not just reject its negation.

    Rejecting only an explicit `"serverSide": true` fails OPEN: if CBK renames
    the setting, drops it, or switches table plugin, the page parses as though
    it embedded every row and a partial register publishes silently — looking
    exactly like a smaller bond book.
    """
    import pytest

    from seeding.domains.national_debt.cbk_web_tables import (
        CbkTableError,
        _assert_table_complete,
    )

    # Setting absent entirely.
    with pytest.raises(CbkTableError, match="serverSide"):
        _assert_table_complete("<table><tr><td>1</td></tr></table>", "https://x")

    # Setting renamed by a plugin change.
    with pytest.raises(CbkTableError, match="serverSide"):
        _assert_table_complete('<script>{"server_side":false}</script>', "https://x")

    # Positive control: an explicit false still passes.
    _assert_table_complete('<script>{"serverSide":false}</script>', "https://x")


def test_every_debt_timeline_ratio_matches_its_own_total_and_gdp():
    """The fixture must not contradict itself.

    Correcting the totals left the old ratios behind — 2,111.6 / 7,381 is 28.6%,
    not the 42.0% the row claimed. Those ratios matched the REMOVED totals, and
    when World Bank enrichment is disabled or fails the fixture values persist
    unchanged, so the API published internally inconsistent debt-to-GDP.
    """
    import json
    from pathlib import Path

    doc = json.loads(
        (Path(__file__).resolve().parents[1] / "seeding/real_data/debt_timeline.json")
        .read_text(encoding="utf-8")
    )
    rows = doc["timeline"]
    assert rows, "fixture is empty"

    bad = []
    for r in rows:
        total, gdp, stated = r.get("total"), r.get("gdp"), r.get("gdp_ratio")
        if not total or not gdp or stated is None:
            continue
        computed = round(total / gdp * 100, 1)
        # Allow one decimal of rounding slack, nothing more.
        if abs(computed - stated) > 0.1:
            bad.append((r["year"], stated, computed))

    assert not bad, "rows whose gdp_ratio disagrees with their own total/gdp: " + ", ".join(
        f"{y}: says {s}%, computes {c}%" for y, s, c in bad
    )
