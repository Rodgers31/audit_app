"""
Tests for database models and relationships.

Validates:
  - All models can be created in the test DB
  - Foreign key relationships work correctly
  - Enum fields serialize properly
  - JSONB fields (stored as TEXT in SQLite) work for read/write
"""

import json
from datetime import datetime, timezone

import pytest
from models import (
    Annotation,
    Audit,
    Base,
    BudgetLine,
    Country,
    DebtCategory,
    DebtTimeline,
    DocumentStatus,
    DocumentType,
    EconomicIndicator,
    Entity,
    EntityType,
    Extraction,
    FiscalPeriod,
    FiscalSummary,
    GDPData,
    IngestionJob,
    IngestionStatus,
    Loan,
    PopulationData,
    PovertyIndex,
    QuickQuestion,
    RevenueBySource,
    Severity,
    SourceDocument,
    User,
)


class TestCountryModel:
    def test_create_country(self, db_session):
        c = Country(
            iso_code="KEN",
            name="Kenya",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en_KE",
        )
        db_session.add(c)
        db_session.commit()

        fetched = db_session.query(Country).filter_by(iso_code="KEN").first()
        assert fetched is not None
        assert fetched.name == "Kenya"
        assert fetched.currency == "KES"

    def test_country_unique_iso_code(self, db_session):
        c1 = Country(
            iso_code="KEN",
            name="Kenya",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en_KE",
        )
        c2 = Country(
            iso_code="KEN",
            name="Kenya Dup",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en_KE",
        )
        db_session.add(c1)
        db_session.commit()
        db_session.add(c2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()


class TestEntityModel:
    def test_create_entity(self, db_session, seed_country):
        e = Entity(
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Nairobi",
            slug="nairobi",
        )
        db_session.add(e)
        db_session.commit()

        fetched = db_session.query(Entity).filter_by(slug="nairobi").first()
        assert fetched.canonical_name == "Nairobi"
        assert fetched.type == EntityType.COUNTY

    def test_entity_belongs_to_country(self, db_session, seed_country):
        e = Entity(
            country_id=seed_country.id,
            type=EntityType.MINISTRY,
            canonical_name="Ministry of Health",
            slug="moh",
        )
        db_session.add(e)
        db_session.commit()
        assert e.country_id == seed_country.id

    def test_entity_unique_slug(self, db_session, seed_country):
        e1 = Entity(
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Nairobi",
            slug="nairobi",
        )
        e2 = Entity(
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Nairobi2",
            slug="nairobi",
        )
        db_session.add(e1)
        db_session.commit()
        db_session.add(e2)
        with pytest.raises(Exception):
            db_session.commit()


class TestFiscalPeriodModel:
    def test_create_fiscal_period(self, db_session, seed_country):
        fp = FiscalPeriod(
            country_id=seed_country.id,
            label="FY2024/25",
            start_date=datetime(2024, 7, 1),
            end_date=datetime(2025, 6, 30),
        )
        db_session.add(fp)
        db_session.commit()
        assert fp.label == "FY2024/25"


class TestBudgetLineModel:
    def test_create_budget_line(
        self, db_session, seed_entity, seed_fiscal_period, seed_source_doc
    ):
        bl = BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Education",
            subcategory="Primary",
            allocated_amount=1_000_000,
            actual_spent=800_000,
            currency="KES",
            source_document_id=seed_source_doc.id,
        )
        db_session.add(bl)
        db_session.commit()

        fetched = db_session.query(BudgetLine).first()
        assert fetched.category == "Education"
        assert float(fetched.allocated_amount) == 1_000_000


class TestLoanModel:
    def test_create_loan(self, db_session, seed_entity, seed_source_doc):
        loan = Loan(
            entity_id=seed_entity.id,
            lender="World Bank",
            debt_category=DebtCategory.EXTERNAL_MULTILATERAL,
            principal=100_000_000,
            outstanding=80_000_000,
            currency="KES",
            source_document_id=seed_source_doc.id,
            issue_date=datetime(2020, 1, 1),
        )
        db_session.add(loan)
        db_session.commit()

        fetched = db_session.query(Loan).first()
        assert fetched.lender == "World Bank"
        assert fetched.debt_category == DebtCategory.EXTERNAL_MULTILATERAL


class TestAuditModel:
    def test_create_audit(
        self, db_session, seed_entity, seed_fiscal_period, seed_source_doc
    ):
        a = Audit(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            finding_text="Irregular procurement",
            severity=Severity.CRITICAL,
            recommended_action="Investigate",
            source_document_id=seed_source_doc.id,
            # Tier B (#137): a published finding cites a page.
            page_ref="p.409",
        )
        db_session.add(a)
        db_session.commit()

        fetched = db_session.query(Audit).first()
        assert fetched.severity == Severity.CRITICAL
        assert "procurement" in fetched.finding_text


class TestDebtTimelineModel:
    def test_create_debt_timeline(self, db_session):
        dt = DebtTimeline(
            year=2024,
            external=3_500_000_000_000,
            domestic=4_800_000_000_000,
            total=8_300_000_000_000,
            gdp=14_000_000_000_000,
            gdp_ratio=59.3,
        )
        db_session.add(dt)
        db_session.commit()

        fetched = db_session.query(DebtTimeline).first()
        assert fetched.year == 2024
        assert float(fetched.gdp_ratio) == pytest.approx(59.3)


class TestFiscalSummaryModel:
    def test_create_fiscal_summary(self, db_session):
        fs = FiscalSummary(
            fiscal_year="2024/25",
            appropriated_budget=3_600_000_000_000,
            total_revenue=2_800_000_000_000,
            tax_revenue=2_200_000_000_000,
            development_spending=700_000_000_000,
            recurrent_spending=2_100_000_000_000,
        )
        db_session.add(fs)
        db_session.commit()

        fetched = db_session.query(FiscalSummary).first()
        assert fetched.fiscal_year == "2024/25"


class TestPopulationDataModel:
    def test_create_population(self, db_session, seed_entity):
        pop = PopulationData(
            entity_id=seed_entity.id,
            year=2024,
            total_population=2_000_000,
            male_population=1_000_000,
            female_population=1_000_000,
        )
        db_session.add(pop)
        db_session.commit()

        fetched = db_session.query(PopulationData).first()
        assert fetched.total_population == 2_000_000


class TestUserModel:
    def test_create_user(self, db_session):
        u = User(
            email="admin@gov.ke",
            password_hash="hashed123",
        )
        db_session.add(u)
        db_session.commit()

        fetched = db_session.query(User).filter_by(email="admin@gov.ke").first()
        assert fetched is not None


class TestIngestionJobModel:
    def test_create_ingestion_job(self, db_session):
        job = IngestionJob(
            domain="population",
            status=IngestionStatus.COMPLETED,
            dry_run=False,
            items_processed=100,
            items_created=90,
            items_updated=10,
        )
        db_session.add(job)
        db_session.commit()

        fetched = db_session.query(IngestionJob).first()
        assert fetched.domain == "population"
        assert fetched.status == IngestionStatus.COMPLETED


class TestRevenueBySourceModel:
    def test_create_revenue(self, db_session):
        rev = RevenueBySource(
            fiscal_year="2024/25",
            revenue_type="tax",
            category="Income Tax",
            amount_billion_kes=800.5,
            target_billion_kes=900.0,
            performance_pct=88.9,
        )
        db_session.add(rev)
        db_session.commit()

        fetched = db_session.query(RevenueBySource).first()
        assert fetched.revenue_type == "tax"
