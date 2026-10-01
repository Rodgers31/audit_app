"""County coverage is Kenyan-only; findings and money retain institution scope."""
from decimal import Decimal

import pytest
from sqlalchemy import event

from main import clear_all_caches
from models import Audit, Country, Entity, EntityType, Severity


def statistics(client):
    clear_all_caches()
    response = client.get("/api/v1/audits/statistics")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("iso,kind,expected", [
    ("KEN", EntityType.COUNTY, 1),
    ("KEN", EntityType.MINISTRY, 0),
    ("KEN", EntityType.NATIONAL, 0),
    ("UGA", EntityType.COUNTY, 0),
])
def test_county_coverage_uses_entity_country_and_type(
    client, db_session, seed_country, seed_fiscal_period, seed_source_doc,
    iso, kind, expected,
):
    country_id = seed_country.id
    if iso != "KEN":
        foreign = Country(iso_code=iso, name="Uganda", currency="UGX",
                          timezone="Africa/Kampala", default_locale="en_UG")
        db_session.add(foreign)
        db_session.flush()
        country_id = foreign.id
    # A Kenyan-looking name and Kenyan source cannot override entity identity.
    entity = Entity(country_id=country_id, type=kind,
                    canonical_name="Mombasa County", slug="synthetic-entity")
    db_session.add(entity)
    db_session.flush()
    db_session.add(Audit(entity_id=entity.id, period_id=seed_fiscal_period.id,
                         source_document_id=seed_source_doc.id, page_ref="p.7",
                         finding_text="Cited synthetic finding", severity=Severity.WARNING,
                         amount=Decimal("0")))
    db_session.commit()
    body = statistics(client)
    assert body["counties_audited"] == expected
    assert body["total_counties"] == 47
    assert body["total_findings"] == 1
    assert body["by_severity"] == {"warning": 1}
    assert body["total_amount_flagged"] == 0
    assert body["findings_with_amount"] == 1


def test_mixed_scope_preserves_all_findings_money_missing_and_withheld(
    client, db_session, seed_country, seed_fiscal_period, seed_source_doc,
):
    foreign = Country(iso_code="UGA", name="Uganda", currency="UGX",
                          timezone="Africa/Kampala", default_locale="en_UG")
    db_session.add(foreign)
    db_session.flush()
    entities = [
        Entity(country_id=seed_country.id, type=EntityType.COUNTY,
               canonical_name="Covered County", slug="covered"),
        Entity(country_id=seed_country.id, type=EntityType.MINISTRY,
               canonical_name="Synthetic Ministry", slug="ministry"),
        Entity(country_id=foreign.id, type=EntityType.COUNTY,
               canonical_name="Foreign County", slug="foreign"),
        Entity(country_id=seed_country.id, type=EntityType.COUNTY,
               canonical_name="Withheld County", slug="withheld"),
    ]
    db_session.add_all(entities)
    db_session.flush()
    county_id, period_id, source_id = entities[0].id, seed_fiscal_period.id, seed_source_doc.id
    for index, amount, page in [(0, 100, "p.7"), (0, 0, "p.8"),
                                (1, 200, "p.9"), (2, 300, "p.10"),
                                (3, 900, None)]:
        db_session.add(Audit(entity_id=entities[index].id, period_id=seed_fiscal_period.id,
                             source_document_id=seed_source_doc.id, page_ref=page,
                             finding_text="Cited synthetic finding", severity=Severity.WARNING,
                             amount=Decimal(amount)))
    db_session.commit()
    body = statistics(client)
    assert body["counties_audited"] == 1
    assert body["total_findings"] == 4
    assert body["total_amount_flagged"] == 600
    assert body["findings_with_amount"] == 4
    assert body["withheld_findings"] == 1
    assert body["withheld_findings_by_reason"]["no_page_reference"] == 1

    db_session.add(Audit(entity_id=county_id, period_id=period_id,
                         source_document_id=source_id, page_ref="p.11",
                         finding_text="No monetary amount stated", severity=Severity.INFO))
    db_session.commit()
    body = statistics(client)
    assert body["counties_audited"] == 1
    assert body["total_findings"] == 5
    assert body["total_amount_flagged"] == 600
    assert body["findings_without_amount"] == 1
    assert body["findings_with_invalid_amount"] == 0


def test_county_scope_queries_do_not_grow_per_finding(
    client, db_session, seed_entity, seed_fiscal_period, seed_source_doc,
):
    statements = []
    bind = db_session.get_bind()

    def record(_conn, _cursor, sql, _params, _context, _many):
        if sql.lstrip().lower().startswith("select"):
            statements.append(sql)

    entity_id, period_id, source_id = seed_entity.id, seed_fiscal_period.id, seed_source_doc.id

    def add(count):
        db_session.add_all([
            Audit(entity_id=entity_id, period_id=period_id,
                  source_document_id=source_id, page_ref="p.7",
                  finding_text="Cited synthetic finding", severity=Severity.WARNING,
                  amount=Decimal("1")) for _ in range(count)
        ])
        db_session.commit()

    add(1)
    event.listen(bind, "before_cursor_execute", record)
    try:
        assert statistics(client)["counties_audited"] == 1
        first = len(statements)
        add(30)
        statements.clear()
        body = statistics(client)
        assert body["total_findings"] == 31
        assert body["counties_audited"] == 1
        assert len(statements) == first
    finally:
        event.remove(bind, "before_cursor_execute", record)
