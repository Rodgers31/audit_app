"""The external/domestic split must be the register's own sum, not a re-split.

Two defects on ``/api/v1/debt/national``, both visible in one production
response on 2026-09-06.

**1. The split was manufactured.** ``main.py`` discarded the loan register's
own external and domestic sums, kept only their *total*, and re-divided that
total by ``DebtTimeline``'s external/domestic proportion::

    external_debt = _base * (_tl_ext / _tl_split)
    domestic_debt = _base * (_tl_dom / _tl_split)

Production therefore served, in ONE response::

    summary.external_debt   5,265.0Bn   categories external   4,797.3Bn
    summary.domestic_debt   6,591.0Bn   categories domestic   7,058.7Bn

— a 467.7Bn contradiction between the headline card and the treemap beneath
it. Reproduced exactly: DebtTimeline 2025 is ext 5,462.0Bn / dom 6,837.5Bn
(44.41% / 55.59%), and 11,856.0 x 0.4441 = 5,265.0.

The in-code comment justified the re-split by saying the register
"under-represents domestic instruments (T-bonds/bills), which inverted the
split". That was true when written. It is not true now: the domestic side
carries the CBK bulletin overlay at 7,058.7Bn, which *exceeds* CBK's own
Dec-2025 domestic figure of 6,837.5Bn, and the register's domestic side
already leads its external side without any help. The correction now produces
the very error it was added to prevent — it moves domestic 467.7Bn *down*,
away from the register that measured it.

The register's sums are measurements. The re-split is arithmetic on a
measurement someone else made about a different quantity. Publish the
measurement.

**2. The response mixed two bases.** The re-split read ``["principal"]`` while
the headline the split is checked against (``total_outstanding``, which is also
what ``check_debt_composition`` compares the parts to) is an ``outstanding``
sum. Invisible in current data because every row has principal == outstanding,
which is exactly why it needed pinning: the day one row differs, the parts stop
summing to the whole and nothing says why.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import DebtCategory, DebtTimeline, Entity, EntityType, Loan


def national_debt(client) -> dict:
    """Fetch ``/debt/national`` through the test client.

    ``get_national_debt`` takes no ``db`` parameter — it opens its own session
    with ``next(get_db())`` — so it can only be pointed at the test database
    through the ``client`` fixture, which patches ``main.get_db``. The response
    cache is cleared first: several tests below call this twice in one test to
    show that a figure did (or did not) move.
    """
    from main import clear_all_caches

    clear_all_caches()
    body = client.get("/api/v1/debt/national").json()
    assert body["status"] == "success", body
    return body["data"]


@pytest.fixture()
def national_entity(db_session, seed_country):
    entity = Entity(
        id=900,
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="Republic of Kenya",
        slug="republic-of-kenya",
    )
    db_session.add(entity)
    db_session.commit()
    return entity


def _loan(entity, doc, lender, category, amount, outstanding=None, day=1):
    return Loan(
        entity_id=entity.id,
        lender=lender,
        debt_category=category,
        principal=amount,
        outstanding=amount if outstanding is None else outstanding,
        issue_date=datetime(2024, 1, day, tzinfo=timezone.utc),
        currency="KES",
        source_document_id=doc.id,
    )


@pytest.fixture()
def production_shape(db_session, national_entity, seed_source_doc):
    """The 2026-09-06 production register and timeline, to scale.

    Register: external 4,797.3Bn over three categories, domestic 7,058.7Bn over
    three, plus 931.3Bn of pending bills that the headline excludes.
    Timeline 2025: the CBK aggregate whose proportion did the re-splitting.
    """
    B = 1e9
    rows = [
        _loan(national_entity, seed_source_doc, "Multilateral (World Bank — IDA)",
              DebtCategory.EXTERNAL_MULTILATERAL, 2695.7 * B, day=1),
        _loan(national_entity, seed_source_doc, "Bilateral (China — Exim Bank)",
              DebtCategory.EXTERNAL_BILATERAL, 1087.5 * B, day=2),
        _loan(national_entity, seed_source_doc, "Eurobond 2032",
              DebtCategory.EXTERNAL_COMMERCIAL, 1014.126958 * B, day=3),
        _loan(national_entity, seed_source_doc, "Domestic Treasury Bonds",
              DebtCategory.DOMESTIC_BONDS, 5879.0 * B, day=4),
        _loan(national_entity, seed_source_doc, "Treasury Bills",
              DebtCategory.DOMESTIC_BILLS, 1090.0 * B, day=5),
        _loan(national_entity, seed_source_doc, "CBK Overdraft",
              DebtCategory.DOMESTIC_OVERDRAFT, 89.6519 * B, day=6),
        _loan(national_entity, seed_source_doc, "Pending Bills — National Government",
              DebtCategory.PENDING_BILLS, 931.3 * B, day=7),
    ]
    db_session.add_all(rows)
    db_session.add(
        DebtTimeline(
            year=2025,
            external=5462.0 * B,
            domestic=6837.5 * B,
            total=12299.5 * B,
            gdp_ratio=70.0,
            unit="KES",
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.commit()
    return db_session


# ── 1. The split is the register's own sum ─────────────────────────────────

def test_summary_split_equals_the_category_block_beside_it(client, production_shape):
    """The headline card and the treemap under it must state one number each."""
    data = national_debt(client)
    summary, cats = data["summary"], data["categories"]

    cat_external = sum(
        cats[c]["total_outstanding"]
        for c in ("external_multilateral", "external_bilateral", "external_commercial")
        if c in cats
    )
    cat_domestic = sum(
        cats[c]["total_outstanding"]
        for c in ("domestic_bonds", "domestic_bills", "domestic_overdraft")
        if c in cats
    )

    assert summary["external_debt"] == pytest.approx(cat_external, rel=1e-9)
    assert summary["domestic_debt"] == pytest.approx(cat_domestic, rel=1e-9)


def test_the_production_467bn_contradiction_is_gone(client, production_shape):
    """Pin the exact figures. Pre-fix this served 5,265.0 / 6,591.0."""
    summary = national_debt(client)["summary"]
    assert summary["external_debt"] / 1e9 == pytest.approx(4797.326958, abs=0.05)
    assert summary["domestic_debt"] / 1e9 == pytest.approx(7058.6519, abs=0.05)


def test_a_cbk_proportion_that_disagrees_cannot_move_the_register(
    client, production_shape, db_session
):
    """Direct control on the mechanism: change ONLY the timeline proportion.

    Pre-fix, inverting the CBK split swings the published external figure by
    trillions while not one loan row has changed. A measurement does not move
    when a different institution's unrelated ratio moves.
    """
    before = national_debt(client)["summary"]

    row = db_session.query(DebtTimeline).filter(DebtTimeline.year == 2025).one()
    row.external, row.domestic = row.domestic, row.external  # 55.59% / 44.41%
    db_session.commit()

    after = national_debt(client)["summary"]
    assert after["external_debt"] == pytest.approx(before["external_debt"], rel=1e-9)
    assert after["domestic_debt"] == pytest.approx(before["domestic_debt"], rel=1e-9)


# ── 2. One basis for every derived share ───────────────────────────────────

def test_split_is_on_the_same_basis_as_the_headline_it_is_checked_against(
    client, db_session, national_entity, seed_source_doc
):
    """principal != outstanding is the case the production data cannot show.

    Two rows whose principal is double their outstanding. ``total_outstanding``
    is the published headline; the parts must be on that same basis, or they do
    not sum to it.
    """
    B = 1e9
    db_session.add_all([
        _loan(national_entity, seed_source_doc, "Eurobond 2032",
              DebtCategory.EXTERNAL_COMMERCIAL, 800 * B, outstanding=400 * B, day=1),
        _loan(national_entity, seed_source_doc, "Domestic Treasury Bonds",
              DebtCategory.DOMESTIC_BONDS, 1200 * B, outstanding=600 * B, day=2),
    ])
    db_session.commit()

    data = national_debt(client)
    summary = data["summary"]

    assert summary["external_debt"] == pytest.approx(400 * B)
    assert summary["domestic_debt"] == pytest.approx(600 * B)
    assert summary["external_debt"] + summary["domestic_debt"] == pytest.approx(
        data["total_outstanding"]
    )
    assert summary["external_percentage"] == pytest.approx(40.0)
    assert summary["domestic_percentage"] == pytest.approx(60.0)


def test_the_basis_is_declared_not_inferred(client, production_shape):
    """A reader must not have to guess which of the two money columns this is."""
    assert national_debt(client)["summary"]["basis"] == "outstanding"
