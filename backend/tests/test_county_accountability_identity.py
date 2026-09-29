"""County scorecards must use the same Kenyan identity as the audit list."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models import (
    Audit,
    Country,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Severity,
    SourceDocument,
)


def _finding(db, country, entity, label, amount=None):
    period = FiscalPeriod(
        country_id=country.id,
        label=label,
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    doc = SourceDocument(
        country_id=country.id,
        publisher="Synthetic OAG",
        title=label,
        url=f"https://example.invalid/{country.iso_code.lower()}.pdf",
        fetch_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db.add_all([period, doc])
    db.flush()
    db.add(
        Audit(
            entity_id=entity.id,
            period_id=period.id,
            source_document_id=doc.id,
            finding_text=f"{country.iso_code} finding",
            severity=Severity.WARNING,
            page_ref="p. 7",
            audit_year=2024,
            amount=amount,
        )
    )
    db.commit()


def _county(db, country, name, slug, entity_type=EntityType.COUNTY):
    entity = Entity(
        country_id=country.id,
        type=entity_type,
        canonical_name=f"{name} County",
        slug=slug,
    )
    db.add(entity)
    db.flush()
    return entity


@pytest.mark.parametrize("endpoint", ["accountability", "summary"])
def test_foreign_namesake_and_wrong_type_never_supply_kenyan_scorecard(
    client,
    db_session,
    seed_country,
    endpoint,
):
    tanzania = Country(
        iso_code="TZA",
        name="Tanzania",
        currency="TZS",
        timezone="Africa/Dar_es_Salaam",
        default_locale="sw_TZ",
    )
    db_session.add(tanzania)
    db_session.flush()
    foreign_country = SimpleNamespace(id=tanzania.id, iso_code="TZA")
    kenya_country = SimpleNamespace(id=seed_country.id, iso_code="KEN")
    foreign = _county(db_session, foreign_country, "Nairobi", "foreign-nairobi")
    _finding(db_session, foreign_country, foreign, "FY2024/25 TZA")
    foreign_id = foreign.id

    for identifier in ("001", "code:047", "foreign-nairobi", str(foreign_id)):
        response = client.get(f"/api/v1/counties/{identifier}/{endpoint}")
        assert response.status_code == 404, response.text

    ministry = _county(
        db_session, kenya_country, "Nairobi", "ministry-nairobi", EntityType.MINISTRY
    )
    _finding(db_session, kenya_country, ministry, "FY2024/25 KEN ministry")
    assert client.get(f"/api/v1/counties/001/{endpoint}").status_code == 404

    kenya = _county(db_session, kenya_country, "Nairobi", "kenya-nairobi")
    _finding(db_session, kenya_country, kenya, "FY2024/25 KEN county")
    kenya_id = kenya.id
    from main import clear_all_caches

    clear_all_caches()
    for identifier in ("001", "code:047", "kenya-nairobi", str(kenya_id)):
        response = client.get(f"/api/v1/counties/{identifier}/{endpoint}")
        assert response.status_code == 200, response.text
        payload = response.json()
        count = (
            payload["total_findings"]
            if endpoint == "accountability"
            else payload["audit_findings_count"]
        )
        assert count == 1
    for unknown in ("999", "code:999", "not-a-county"):
        assert client.get(f"/api/v1/counties/{unknown}/{endpoint}").status_code == 404


@pytest.mark.parametrize("endpoint", ["accountability", "summary"])
def test_legacy_and_official_nairobi_mombasa_ids_remain_distinct(
    client,
    db_session,
    seed_country,
    endpoint,
):
    nairobi = _county(db_session, seed_country, "Nairobi", "nairobi-contract")
    mombasa = _county(db_session, seed_country, "Mombasa", "mombasa-contract")
    _finding(db_session, seed_country, nairobi, "FY2024/25 Nairobi")
    _finding(db_session, seed_country, mombasa, "FY2024/25 Mombasa")
    for identifier, expected in (
        ("001", "Nairobi"),
        ("code:047", "Nairobi"),
        ("047", "Mombasa"),
        ("code:001", "Mombasa"),
    ):
        response = client.get(f"/api/v1/counties/{identifier}/{endpoint}")
        assert response.status_code == 200, response.text
        assert response.json()["county_name"] == expected
        if endpoint == "accountability":
            expected_region = "Nairobi" if expected == "Nairobi" else "Coast"
            assert response.json()["peer_comparison"]["region"] == expected_region


def test_foreign_peer_cannot_change_kenyan_region_average(
    client,
    db_session,
    seed_country,
):
    kenya_country = SimpleNamespace(id=seed_country.id, iso_code="KEN")
    mombasa = _county(db_session, kenya_country, "Mombasa", "mombasa-peer-target")
    kwale = _county(db_session, kenya_country, "Kwale", "kenyan-kwale-peer")
    _finding(db_session, kenya_country, mombasa, "FY2024/25 Mombasa")
    _finding(db_session, kenya_country, kwale, "FY2024/25 Kwale", amount=2)

    tanzania = Country(
        iso_code="TZA",
        name="Tanzania",
        currency="TZS",
        timezone="Africa/Dar_es_Salaam",
        default_locale="sw_TZ",
    )
    db_session.add(tanzania)
    db_session.flush()
    foreign_country = SimpleNamespace(id=tanzania.id, iso_code="TZA")
    foreign_kwale = _county(db_session, foreign_country, "Kwale", "foreign-kwale-peer")
    _finding(
        db_session, foreign_country, foreign_kwale, "FY2024/25 foreign Kwale", amount=9
    )

    response = client.get("/api/v1/counties/047/accountability")
    assert response.status_code == 200, response.text
    assert response.json()["peer_comparison"]["region_avg_flagged_amount"] == 2
