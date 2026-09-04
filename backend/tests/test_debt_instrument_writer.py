"""Persisting the Treasury bond register (credibility audit F24/F42).

The register is a maturity and coupon profile covering ~60% of CBK's published
Treasury-bond stock. These pin the two rules that keep it from becoming a debt
total by accident, and the upsert behaviour that keeps a re-run from
duplicating the ladder or leaving redeemed bonds on it.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import DebtInstrument, SourceDocument
from seeding.domains.national_debt.instrument_writer import write_bond_register


def _register(securities, coverage_ratio=0.60, withheld=None):
    return {
        "source_url": "https://www.centralbank.go.ke/bills-bonds/treasury-bonds/",
        "source_title": "CBK — Issues of Treasury Bonds",
        "as_of": "2026-09-03",
        "tranche_rows": 329,
        "coverage": {
            "coverage_ratio": coverage_ratio,
            "status": "within_band",
            "register_total_kes": 3.5e12,
            "published_stock_kes": 5.88e12,
        },
        "withheld_isins": withheld or {},
        "securities": securities,
    }


def _sec(isin, maturity, face=1e10, coupon=12.5, issue_no="FXD1/2020/10", tranches=1):
    return {
        "isin": isin,
        "issue_no": issue_no,
        "instrument_type": "fixed_coupon_bond",
        "maturity_date": maturity,
        "first_issued": "2020-01-01T00:00:00",
        "coupon_rate": coupon,
        "tenor_years": 10,
        "face_value_kes": face,
        "tranches": tranches,
    }


def test_writes_the_register(db_session, seed_country):
    counts = write_bond_register(
        db_session,
        _register([
            _sec("KE0000000001", "2030-01-15T00:00:00"),
            _sec("KE0000000002", "2032-06-01T00:00:00", coupon=14.399),
        ]),
    )
    db_session.commit()
    assert counts == {"created": 2, "updated": 0, "deleted": 0}
    rows = db_session.query(DebtInstrument).all()
    assert len(rows) == 2
    assert {float(r.coupon_rate) for r in rows} == {12.5, 14.399}
    assert all(r.unit == "KES" for r in rows)
    assert all(r.publishable for r in rows)


def test_a_rerun_updates_rather_than_duplicating(db_session, seed_country):
    """Upsert on (isin, maturity). Without it a nightly re-run doubles every
    bar on the maturity ladder."""
    reg = _register([_sec("KE0000000001", "2030-01-15T00:00:00", face=1e10)])
    write_bond_register(db_session, reg)
    db_session.commit()

    reg2 = _register([_sec("KE0000000001", "2030-01-15T00:00:00", face=2e10)])
    counts = write_bond_register(db_session, reg2)
    db_session.commit()

    assert counts == {"created": 0, "updated": 1, "deleted": 0}
    rows = db_session.query(DebtInstrument).all()
    assert len(rows) == 1
    assert float(rows[0].face_value) == pytest.approx(2e10)


def test_one_security_may_redeem_on_several_dates(db_session, seed_country):
    """Amortising bonds are the reason the key is (isin, maturity) and not
    isin. Both lines must survive."""
    write_bond_register(
        db_session,
        _register([
            _sec("KE8000005549", "2033-02-28T00:00:00", issue_no="IFB1/2023/017"),
            _sec("KE8000005549", "2040-02-20T00:00:00", issue_no="IFB1/2023/017"),
        ]),
    )
    db_session.commit()
    rows = db_session.query(DebtInstrument).filter_by(isin="KE8000005549").all()
    assert len(rows) == 2
    assert {r.maturity_date.year for r in rows} == {2033, 2040}


def test_a_bond_cbk_no_longer_lists_is_removed(db_session, seed_country):
    """A redeemed bond left in the table keeps drawing a bar on the ladder for
    debt that has been paid."""
    write_bond_register(
        db_session,
        _register([
            _sec("KE0000000001", "2027-01-15T00:00:00"),
            _sec("KE0000000002", "2032-06-01T00:00:00"),
        ]),
    )
    db_session.commit()

    counts = write_bond_register(
        db_session, _register([_sec("KE0000000002", "2032-06-01T00:00:00")])
    )
    db_session.commit()
    assert counts["deleted"] == 1
    assert [r.isin for r in db_session.query(DebtInstrument).all()] == ["KE0000000002"]


def test_the_source_document_carries_the_not_a_total_warning(db_session, seed_country):
    """The rule has to travel with the data. A consumer that reaches the
    document must find the coverage ratio and the instruction not to sum it."""
    write_bond_register(
        db_session,
        _register([_sec("KE0000000001", "2030-01-15T00:00:00")], coverage_ratio=0.60),
    )
    db_session.commit()

    doc = (
        db_session.query(SourceDocument)
        .filter(SourceDocument.url.like("%treasury-bonds%"))
        .one()
    )
    assert doc.url.endswith("/bills-bonds/treasury-bonds/"), "must be the table, not a listing page"
    assert doc.meta["coverage"]["coverage_ratio"] == 0.60
    assert "must not be summed into a debt total" in doc.meta["not_a_stock_measure"]
    assert "60%" in doc.meta["not_a_stock_measure"]


def test_withheld_isins_are_recorded_on_the_document(db_session, seed_country):
    """Six ISINs holding ~15% of face value are never written. The omission
    must be visible, not inferred from a total that looks slightly small."""
    withheld = {
        "KE4000003808": {
            "reason": "isin_covers_two_securities",
            "maturities": ["2028-04-10", "2033-10-03"],
            "face_value_kes": 5e10,
        }
    }
    write_bond_register(
        db_session,
        _register([_sec("KE0000000001", "2030-01-15T00:00:00")], withheld=withheld),
    )
    db_session.commit()

    doc = (
        db_session.query(SourceDocument)
        .filter(SourceDocument.url.like("%treasury-bonds%"))
        .one()
    )
    assert doc.meta["withheld_isins"]["KE4000003808"]["reason"] == "isin_covers_two_securities"
    assert not db_session.query(DebtInstrument).filter_by(isin="KE4000003808").count()


def test_an_empty_register_writes_nothing_rather_than_clearing_the_table(
    db_session, seed_country
):
    """A failed fetch must not empty the ladder. The domain reports the
    absence; it does not delete good rows to represent it."""
    write_bond_register(
        db_session, _register([_sec("KE0000000001", "2030-01-15T00:00:00")])
    )
    db_session.commit()

    counts = write_bond_register(db_session, _register([]))
    db_session.commit()
    assert counts == {"created": 0, "updated": 0, "deleted": 0}
    assert db_session.query(DebtInstrument).count() == 1


# ── The endpoint ─────────────────────────────────────────────────────────

def test_endpoint_says_absent_rather_than_showing_an_empty_ladder(client):
    """An empty ladder reads as "no government debt falls due". Say why."""
    resp = client.get("/api/v1/debt/instruments")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "no_instrument_register_ingested"
    assert "not a finding" in body["message"].lower()
    assert body["ladder"] == []


def test_endpoint_serves_the_ladder_and_refuses_to_be_a_total(
    client, db_session, seed_country
):
    write_bond_register(
        db_session,
        _register(
            [
                _sec("KE0000000001", "2030-01-15T00:00:00", face=1e10),
                _sec("KE0000000002", "2030-08-01T00:00:00", face=2e10),
                _sec("KE0000000003", "2032-06-01T00:00:00", face=5e10, coupon=14.399),
            ],
            coverage_ratio=0.60,
            withheld={"KE4000003808": {"reason": "isin_covers_two_securities",
                                       "maturities": ["2028-04-10", "2033-10-03"],
                                       "face_value_kes": 5e10}},
        ),
    )
    db_session.commit()

    body = client.get("/api/v1/debt/instruments").json()
    assert body["status"] == "success"
    assert body["instrument_count"] == 3

    # The ladder the withdrawn chart could not draw.
    ladder = {b["year"]: b for b in body["ladder"]}
    assert set(ladder) == {2030, 2032}
    assert ladder[2030]["face_value"] == pytest.approx(3e10)
    assert ladder[2030]["instruments"] == 2
    assert ladder[2032]["face_value"] == pytest.approx(5e10)

    # Real coupons, not one assumed rate applied to the whole book.
    coupons = {i["coupon_rate"] for i in body["instruments"]}
    assert coupons == {12.5, 14.399}

    # And it must refuse to be read as a debt total, in the response itself.
    assert body["is_debt_total"] is False
    assert body["coverage"]["coverage_ratio"] == 0.60
    assert "must not be summed into a debt total" in body["not_a_stock_measure"]
    assert body["withheld_count"] == 1
    assert body["source"]["url"].endswith("/bills-bonds/treasury-bonds/")


def test_unpublishable_rows_never_reach_the_endpoint(client, db_session, seed_country):
    """publishable defaults FALSE on every fact table since b3d8ab47bf3b. A
    row that has not earned it must not appear on the ladder."""
    write_bond_register(
        db_session, _register([_sec("KE0000000001", "2030-01-15T00:00:00")])
    )
    db_session.commit()
    row = db_session.query(DebtInstrument).one()
    row.publishable = False
    row.quarantine_reason = "probe"
    db_session.commit()

    body = client.get("/api/v1/debt/instruments").json()
    assert body["status"] == "unavailable"


def test_endpoint_survives_the_table_not_existing(client, db_session):
    """Deploy order must not decide whether a page renders.

    Production is still on the orphaned k1f2a3b4c5d6 revision, so this code
    ships ahead of its own migration. A route-smoke test caught this endpoint
    500ing with `relation "debt_instruments" does not exist`; it now reports
    the absence and says which kind it is.
    """
    from models import DebtInstrument
    from sqlalchemy import text

    DebtInstrument.__table__.drop(db_session.get_bind(), checkfirst=True)
    db_session.commit()

    resp = client.get("/api/v1/debt/instruments")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "table_not_migrated"
    assert "not a finding" in body["message"].lower()
    assert body["ladder"] == []

    DebtInstrument.__table__.create(db_session.get_bind(), checkfirst=True)
    db_session.commit()
