"""Category shares of the national debt must sum to one whole, not 107.86%.

``/api/v1/debt/national`` computed every category's ``percentage_of_total``
against ``total_outstanding`` — a denominator that deliberately **excludes**
pending bills (``_is_debt_loan``, so the headline is not inflated by ~700Bn of
arrears that are not borrowed money). It then handed ``pending_bills`` a
percentage against that same denominator anyway.

Production on 2026-09-06::

    external_multilateral  22.74
    external_bilateral      9.17
    external_commercial     8.55
    domestic_bonds         49.59
    domestic_bills          9.19
    domestic_overdraft      0.76
    pending_bills           7.86   <- not in the denominator
                          -------
                          107.86

Every share on the page is therefore wrong by a factor of 1.0786 relative to
the whole a reader will add them up to, and the excess is exactly the row that
does not belong.

Pending bills are not 7.86% of the national debt, because they are not part of
the national debt as this endpoint defines it. There is no correct number to
put in that slot, so the endpoint declines it and says why — the shape
``/budget/national`` already uses for ``budget_split_absent_reason``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import DebtCategory, Entity, EntityType, Loan

#: The audit's production reading, to the second decimal.
PRODUCTION_PERCENTAGE_SUM = 107.86


def national_debt(client) -> dict:
    from main import clear_all_caches

    clear_all_caches()
    body = client.get("/api/v1/debt/national").json()
    assert body["status"] == "success", body
    return body["data"]


@pytest.fixture()
def national_entity(db_session, seed_country):
    entity = Entity(
        id=901,
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="Republic of Kenya",
        slug="republic-of-kenya",
    )
    db_session.add(entity)
    db_session.commit()
    return entity


@pytest.fixture()
def production_register(db_session, national_entity, seed_source_doc):
    """The seven categories production serves, at their production weights."""
    B = 1e9
    amounts = [
        ("Multilateral (World Bank — IDA)", DebtCategory.EXTERNAL_MULTILATERAL, 2695.7),
        ("Bilateral (China — Exim Bank)", DebtCategory.EXTERNAL_BILATERAL, 1087.5),
        ("Eurobond 2032", DebtCategory.EXTERNAL_COMMERCIAL, 1014.126958),
        ("Domestic Treasury Bonds", DebtCategory.DOMESTIC_BONDS, 5879.0),
        ("Treasury Bills", DebtCategory.DOMESTIC_BILLS, 1090.0),
        ("CBK Overdraft", DebtCategory.DOMESTIC_OVERDRAFT, 89.6519),
        ("Pending Bills — National Government", DebtCategory.PENDING_BILLS, 931.3),
    ]
    db_session.add_all([
        Loan(
            entity_id=national_entity.id,
            lender=lender,
            debt_category=cat,
            principal=amt * B,
            outstanding=amt * B,
            issue_date=datetime(2024, 1, 1 + i, tzinfo=timezone.utc),
            currency="KES",
            source_document_id=seed_source_doc.id,
        )
        for i, (lender, cat, amt) in enumerate(amounts)
    ])
    db_session.commit()
    return db_session


def test_published_shares_sum_to_one_hundred(client, production_register):
    cats = national_debt(client)["categories"]
    published = [
        c["percentage_of_total"]
        for c in cats.values()
        if c["percentage_of_total"] is not None
    ]
    total = round(sum(published), 2)
    assert total != pytest.approx(PRODUCTION_PERCENTAGE_SUM, abs=0.01), (
        "still serving the production 107.86% sum"
    )
    assert total == pytest.approx(100.0, abs=0.01), f"shares sum to {total}"


def test_pending_bills_share_is_withheld_with_a_reason(client, production_register):
    """The row outside the denominator gets no share, and says why.

    ``None`` and not ``0``: zero would claim there are no pending bills, and
    there are 931.3Bn of them — the ``total_principal`` in the same block.
    """
    pending = national_debt(client)["categories"]["pending_bills"]

    assert pending["percentage_of_total"] is None
    assert pending["percentage_absent_reason"] == (
        "category_excluded_from_total_debt_denominator"
    )
    assert pending["total_principal"] == pytest.approx(931.3e9)


def test_categories_inside_the_denominator_still_publish_a_share(
    client, production_register
):
    """Positive control: the withholding must not swallow the whole block."""
    cats = national_debt(client)["categories"]
    for name in (
        "external_multilateral",
        "external_bilateral",
        "external_commercial",
        "domestic_bonds",
        "domestic_bills",
        "domestic_overdraft",
    ):
        assert cats[name]["percentage_of_total"] is not None, name
        assert cats[name].get("percentage_absent_reason") is None, name

    # The production readings, unchanged — this fix moves no share that was
    # already inside the denominator.
    assert cats["domestic_bonds"]["percentage_of_total"] == pytest.approx(49.59, abs=0.01)
    assert cats["external_multilateral"]["percentage_of_total"] == pytest.approx(
        22.74, abs=0.01
    )


def test_shares_still_sum_to_one_hundred_when_a_category_is_uncategorised(
    client, db_session, national_entity, seed_source_doc
):
    """A row with no ``debt_category`` counts as debt (``_is_debt_loan``).

    It must therefore carry a share, or the remaining shares sum to less than
    100 — the mirror image of the defect above.
    """
    B = 1e9
    db_session.add_all([
        Loan(
            entity_id=national_entity.id,
            lender=lender,
            debt_category=cat,
            principal=amt * B,
            outstanding=amt * B,
            issue_date=datetime(2024, 2, 1 + i, tzinfo=timezone.utc),
            currency="KES",
            source_document_id=seed_source_doc.id,
        )
        for i, (lender, cat, amt) in enumerate([
            ("Domestic Treasury Bonds", DebtCategory.DOMESTIC_BONDS, 600.0),
            ("Unclassified instrument", None, 400.0),
            ("Pending Bills — National Government", DebtCategory.PENDING_BILLS, 250.0),
        ])
    ])
    db_session.commit()

    cats = national_debt(client)["categories"]
    published = [
        c["percentage_of_total"]
        for c in cats.values()
        if c["percentage_of_total"] is not None
    ]
    assert round(sum(published), 2) == pytest.approx(100.0, abs=0.01)
    assert cats["other"]["percentage_of_total"] == pytest.approx(40.0, abs=0.01)
