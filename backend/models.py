import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import false as sa_false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class EntityType(enum.Enum):
    NATIONAL = "national"
    COUNTY = "county"
    MINISTRY = "ministry"
    AGENCY = "agency"
    MUNICIPALITY = "municipality"
    STATE_CORPORATION = "state_corporation"
    JUDICIARY = "judiciary"
    COMMISSION = "commission"
    FUND = "fund"
    CONSTITUENCY = "constituency"
    SUB_COUNTY = "sub_county"


class DebtCategory(enum.Enum):
    """Categories of government debt per Treasury classification."""

    EXTERNAL_MULTILATERAL = "external_multilateral"  # World Bank, IMF, AfDB, etc.
    EXTERNAL_BILATERAL = "external_bilateral"  # China, Japan, France, etc.
    EXTERNAL_COMMERCIAL = "external_commercial"  # Eurobonds, syndicated loans
    DOMESTIC_BONDS = "domestic_bonds"  # Treasury bonds (long-term)
    DOMESTIC_BILLS = "domestic_bills"  # Treasury bills (short-term)
    DOMESTIC_OVERDRAFT = "domestic_overdraft"  # CBK overdraft facility
    PENDING_BILLS = "pending_bills"  # Accumulated arrears/pending bills
    COUNTY_GUARANTEED = "county_guaranteed"  # County government guaranteed debt
    OTHER = "other"


class DocumentType(enum.Enum):
    BUDGET = "budget"
    AUDIT = "audit"
    REPORT = "report"
    LOAN = "loan"
    OTHER = "other"


class DocumentStatus(enum.Enum):
    AVAILABLE = "available"
    ARCHIVED = "archived"
    FAILED = "failed"


class FigureBasis(enum.Enum):
    """How a published figure was arrived at.

    The audit found modelled, hardcoded and extracted values stored in the
    same shape, so a missing number, an invented number and a real number
    rendered identically. This column makes the difference queryable, so a
    modelled figure can never be summed into a total of actuals or presented
    as a county-reported number.
    """

    ACTUAL = "actual"        # read from a source document
    MODELLED = "modelled"    # derived from a formula (e.g. the CRA share)
    PROJECTED = "projected"  # a forward estimate from a planning document


class Severity(enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Country(Base):
    __tablename__ = "countries"

    id = Column(Integer, primary_key=True, index=True)
    iso_code = Column(String(3), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    currency = Column(String(3), nullable=False)
    timezone = Column(String(50), nullable=False)
    default_locale = Column(String(10), nullable=False)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    entities = relationship("Entity", back_populates="country")
    fiscal_periods = relationship("FiscalPeriod", back_populates="country")
    source_documents = relationship("SourceDocument", back_populates="country")


class Entity(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    type = Column(Enum(EntityType), nullable=False)
    canonical_name = Column(String(200), nullable=False)
    slug = Column(String(200), unique=True, index=True, nullable=False)
    alt_names = Column(JSONB, default=list)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    country = relationship("Country", back_populates="entities")
    budget_lines = relationship("BudgetLine", back_populates="entity")
    loans = relationship("Loan", back_populates="entity")
    audits = relationship("Audit", back_populates="entity")


class FiscalPeriod(Base):
    __tablename__ = "fiscal_periods"
    __table_args__ = (
        UniqueConstraint(
            "country_id",
            "label",
            name="uq_fiscal_period_country_label",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    label = Column(String(50), nullable=False)  # e.g., "FY2024/25"
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    country = relationship("Country", back_populates="fiscal_periods")
    budget_lines = relationship("BudgetLine", back_populates="period")
    audits = relationship("Audit", back_populates="period")


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id = Column(Integer, primary_key=True, index=True)
    country_id = Column(Integer, ForeignKey("countries.id"), nullable=False)
    publisher = Column(String(200), nullable=False)
    title = Column(String(500), nullable=False)
    url = Column(Text, nullable=True)
    file_path = Column(Text, nullable=True)
    fetch_date = Column(DateTime, nullable=False)
    md5 = Column(String(32), nullable=True)
    doc_type = Column(Enum(DocumentType), nullable=False)
    status = Column(
        Enum(DocumentStatus), nullable=False, default=DocumentStatus.AVAILABLE
    )
    # Fetch bookkeeping. 48 of the 68 documents behind published figures had
    # url IS NULL while status was 'AVAILABLE', and 3 of the 20 that had a URL
    # returned 404 (AUDIT_FINDINGS 5.0c). "Available" must mean "fetched".
    content_type = Column(String(100), nullable=True)
    http_status = Column(Integer, nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    last_seen_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    country = relationship("Country", back_populates="source_documents")
    extractions = relationship("Extraction", back_populates="source_document")
    budget_lines = relationship("BudgetLine", back_populates="source_document")
    loans = relationship("Loan", back_populates="source_document")
    audits = relationship("Audit", back_populates="source_document")


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True, index=True)
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=False
    )
    page_number = Column(Integer, nullable=True)
    extracted_json = Column(JSONB, nullable=False)
    extractor = Column(String(50), nullable=False)  # camelot/tabula/pdfplumber
    confidence = Column(Numeric(3, 2), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    source_document = relationship("SourceDocument", back_populates="extractions")


class BudgetLine(Base):
    __tablename__ = "budget_lines"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "period_id",
            "category",
            "subcategory",
            name="uq_budget_entity_period_cat_subcat",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    period_id = Column(Integer, ForeignKey("fiscal_periods.id"), nullable=False, index=True)
    category = Column(String(200), nullable=False)
    subcategory = Column(String(200), nullable=True)
    allocated_amount = Column(Numeric(15, 2), nullable=True)
    actual_spent = Column(Numeric(15, 2), nullable=True)
    committed_amount = Column(Numeric(15, 2), nullable=True)
    currency = Column(String(3), nullable=False)
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=False
    )
    # Aggregate rows ("Total", "Recurrent", "Development") and component rows
    # (sectors) share this table. Without a discriminator, SUM() over a period
    # triple-counts: FY2024/25 county budget lines summed to KES 1.36T against
    # a national county_allocation of KES 400B (AUDIT_FINDINGS F5.6).
    line_type = Column(String(20), nullable=True, index=True)  # total|aggregate|component
    page_ref = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    provenance = Column(JSONB, default=list)  # List of source references
    source_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    entity = relationship("Entity", back_populates="budget_lines")
    period = relationship("FiscalPeriod", back_populates="budget_lines")
    source_document = relationship("SourceDocument", back_populates="budget_lines")
    annotations = relationship(
        "Annotation",
        back_populates="budget_line",
        primaryjoin="and_(Annotation.ref_type=='budget_line', Annotation.ref_id==BudgetLine.id)",
        foreign_keys="[Annotation.ref_id]",
    )


class Loan(Base):
    __tablename__ = "loans"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "lender",
            "issue_date",
            name="uq_loans_entity_lender_date",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    lender = Column(String(200), nullable=False)
    debt_category = Column(
        Enum(DebtCategory), nullable=True, default=DebtCategory.OTHER, index=True
    )
    principal = Column(Numeric(15, 2), nullable=False)
    outstanding = Column(Numeric(15, 2), nullable=False)
    interest_rate = Column(Numeric(5, 2), nullable=True)  # Annual interest rate %
    issue_date = Column(DateTime, nullable=False)
    maturity_date = Column(DateTime, nullable=True)
    currency = Column(String(3), nullable=False)
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=False
    )
    provenance = Column(JSONB, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    entity = relationship("Entity", back_populates="loans")
    source_document = relationship("SourceDocument", back_populates="loans")


class Audit(Base):
    __tablename__ = "audits"

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    period_id = Column(Integer, ForeignKey("fiscal_periods.id"), nullable=False, index=True)
    finding_text = Column(Text, nullable=False)
    severity = Column(Enum(Severity), nullable=False)
    recommended_action = Column(Text, nullable=True)
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=False
    )
    provenance = Column(JSONB, default=list)

    # Audit finding detail columns
    query_type = Column(String(100), nullable=True)
    amount = Column(Numeric(15, 2), nullable=True)
    status = Column(String(50), nullable=True)
    audit_opinion = Column(String(50), nullable=True)
    audit_year = Column(Integer, nullable=True)
    external_reference = Column(String(200), nullable=True)
    management_response = Column(Text, nullable=True)
    follow_up_status = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    entity = relationship("Entity", back_populates="audits")
    period = relationship("FiscalPeriod", back_populates="audits")
    source_document = relationship("SourceDocument", back_populates="audits")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(120), nullable=True)
    roles = Column(JSONB, default=list)
    disabled = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    annotations = relationship("Annotation", back_populates="user")
    question_answers = relationship("UserQuestionAnswer", back_populates="user")
    watchlist_items = relationship(
        "WatchlistItem", back_populates="user", cascade="all, delete-orphan"
    )
    data_alerts = relationship(
        "DataAlert", back_populates="user", cascade="all, delete-orphan"
    )


class WatchlistItem(Base):
    """User-pinned counties or national categories for their personal dashboard."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "item_type", "item_id", name="uq_watchlist_user_type_item"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    item_type = Column(
        String(30), nullable=False
    )  # "county", "national_category", "budget_programme"
    item_id = Column(String(100), nullable=False)  # entity slug or category key
    label = Column(String(200), nullable=False)  # Human-friendly label for display
    notify = Column(Boolean, default=True)  # Whether to send alerts for this item
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="watchlist_items")


class DataAlert(Base):
    """Alerts sent to users when watched items have new data."""

    __tablename__ = "data_alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    alert_type = Column(
        String(50), nullable=False
    )  # "new_audit", "budget_update", "debt_change"
    title = Column(String(300), nullable=False)
    body = Column(Text, nullable=True)
    item_type = Column(String(30), nullable=True)  # matches watchlist item_type
    item_id = Column(String(100), nullable=True)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="data_alerts")


class NewsletterSubscriber(Base):
    """Email-only newsletter subscriptions (no account required)."""

    __tablename__ = "newsletter_subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    confirmed = Column(Boolean, default=False)
    subscribed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    unsubscribed_at = Column(DateTime, nullable=True)
    meta = Column("metadata", JSONB, default=dict)


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ref_type = Column(String(20), nullable=False)  # budget_line, audit, loan
    ref_id = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="annotations")
    budget_line = relationship(
        "BudgetLine",
        back_populates="annotations",
        foreign_keys="[Annotation.ref_id]",
        primaryjoin="and_(Annotation.ref_type=='budget_line', "
        "Annotation.ref_id==BudgetLine.id)",
    )


class QuestionCategory(enum.Enum):
    BUDGET_BASICS = "budget_basics"
    AUDIT_FUNDAMENTALS = "audit_fundamentals"
    DEBT_MANAGEMENT = "debt_management"
    FINANCIAL_TRANSPARENCY = "financial_transparency"
    GOVERNANCE = "governance"
    PUBLIC_FINANCE = "public_finance"


class QuickQuestion(Base):
    __tablename__ = "quick_questions"

    id = Column(Integer, primary_key=True, index=True)
    question_text = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    option_a = Column(Text, nullable=False)
    option_b = Column(Text, nullable=False)
    option_c = Column(Text, nullable=False)
    option_d = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    category = Column(Enum(QuestionCategory), nullable=False)
    difficulty_level = Column(Integer, nullable=False, default=1)  # 1-5 scale
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    source_url = Column(String(500), nullable=True)
    tags = Column(JSONB, default=list)

    # Relationships
    user_answers = relationship("UserQuestionAnswer", back_populates="question")


class UserQuestionAnswer(Base):
    __tablename__ = "user_question_answers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("quick_questions.id"), nullable=False)
    selected_answer = Column(String(1), nullable=False)  # A, B, C, or D
    is_correct = Column(Boolean, nullable=False)
    answered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="question_answers")
    question = relationship("QuickQuestion", back_populates="user_answers")


# ===== KNBS Economic Data Models =====


class PopulationData(Base):
    """Population data from KNBS (Kenya National Bureau of Statistics)."""

    __tablename__ = "population_data"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "year",
            name="uq_population_entity_year",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(
        Integer, ForeignKey("entities.id"), nullable=True, index=True
    )  # County or national
    year = Column(Integer, nullable=False, index=True)
    total_population = Column(Integer, nullable=False)
    male_population = Column(Integer, nullable=True)
    female_population = Column(Integer, nullable=True)
    urban_population = Column(Integer, nullable=True)
    rural_population = Column(Integer, nullable=True)
    population_density = Column(Numeric(10, 2), nullable=True)  # People per sq km
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=True
    )
    source_page = Column(Integer, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=True, default=1.0)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    entity = relationship("Entity")
    source_document = relationship("SourceDocument")


class GDPData(Base):
    """GDP and Gross County Product data from KNBS."""

    __tablename__ = "gdp_data"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "year",
            "quarter",
            name="uq_gdp_entity_year_quarter",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(
        Integer, ForeignKey("entities.id"), nullable=True, index=True
    )  # NULL for national, county_id for GCP
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(String(2), nullable=True, index=True)  # Q1, Q2, Q3, Q4
    gdp_value = Column(Numeric(20, 2), nullable=False)  # KES
    gdp_growth_rate = Column(Numeric(5, 2), nullable=True)  # Percentage
    currency = Column(String(3), nullable=False, default="KES")
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=True
    )
    source_page = Column(Integer, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=True, default=1.0)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    entity = relationship("Entity")
    source_document = relationship("SourceDocument")


class EconomicIndicator(Base):
    """Economic indicators from KNBS (CPI, PPI, inflation, unemployment, etc.)."""

    __tablename__ = "economic_indicators"
    __table_args__ = (
        UniqueConstraint(
            "indicator_type",
            "indicator_date",
            "entity_id",
            name="uq_econ_type_date_entity",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    indicator_type = Column(
        String(50), nullable=False, index=True
    )  # CPI, PPI, inflation_rate, unemployment_rate
    indicator_date = Column(DateTime, nullable=False, index=True)
    value = Column(Numeric(10, 2), nullable=False)
    entity_id = Column(
        Integer, ForeignKey("entities.id"), nullable=True
    )  # NULL for national, county_id for county-level
    unit = Column(String(20), nullable=True)  # percent, index, etc.
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=True
    )
    source_page = Column(Integer, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=True, default=1.0)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    entity = relationship("Entity")
    source_document = relationship("SourceDocument")


class ImfWeoObservation(Base):
    """One IMF World Economic Outlook observation for a country/indicator/year.

    Kept separate from ``economic_indicators`` because the semantics differ:
      * Country-level, not entity-level (no FK into `entities` which is
        county-scoped in this app).
      * Year granularity, not an arbitrary date — WEO publishes annual
        values, with future years being IMF projections.
      * Vintage-aware — we preserve every snapshot IMF publishes (WEO
        drops twice a year in April and October) so we can tell stories
        like "IMF revised Kenya's 2027 projection from 72% → 75%
        between the April and October vintages". `(country, indicator,
        year)` can therefore have multiple rows, each with a different
        `vintage` timestamp.

    Primary consumer: the ``/api/v1/debt/broader`` endpoint that shows
    IMF's general-government gross debt alongside the CBK central-
    government figure on the debt page and home dashboard. Seeded
    nightly by ``backend.seeding.domains.imf_weo``.
    """

    __tablename__ = "imf_weo_observations"
    __table_args__ = (
        UniqueConstraint(
            "country_code",
            "indicator",
            "year",
            "vintage",
            name="uq_imf_weo_country_indicator_year_vintage",
        ),
        Index(
            "ix_imf_weo_country_indicator_year",
            "country_code",
            "indicator",
            "year",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # ISO3 is 3 chars, but IMF DataMapper also returns regional aggregate
    # codes (WEOWORLD, ADVEC, EURO, EU) that can reach ~8 chars. We filter
    # them out in the parser, but widen the column as defense-in-depth so
    # a parser regression surfaces as garbage data rather than a crash.
    country_code = Column(String(16), nullable=False)  # e.g. "KEN"
    indicator = Column(String(32), nullable=False)  # e.g. "GGXWDG_NGDP"
    year = Column(Integer, nullable=False)
    # Can be NULL — some years have no IMF value (especially for recently
    # added indicators or data-gap countries).
    value = Column(Numeric(20, 4), nullable=True)
    is_projection = Column(Boolean, nullable=False, default=False)
    # When this value was published/fetched. Multiple vintages per
    # (country, indicator, year) let us track IMF's revisions over time.
    vintage = Column(DateTime(timezone=True), nullable=False)
    source = Column(String(32), nullable=False, default="imf_datamapper")
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class IngestionStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class IngestionJob(Base):
    """Track each seeding domain execution for observability."""

    __tablename__ = "ingestion_jobs"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(100), nullable=False, index=True)
    status = Column(
        Enum(IngestionStatus), nullable=False, default=IngestionStatus.PENDING
    )
    dry_run = Column(Boolean, nullable=False, default=False)
    started_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    finished_at = Column(DateTime, nullable=True)
    items_processed = Column(Integer, nullable=False, default=0)
    items_created = Column(Integer, nullable=False, default=0)
    items_updated = Column(Integer, nullable=False, default=0)
    errors = Column(JSONB, default=list)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PovertyIndex(Base):
    """Poverty indices from KNBS."""

    __tablename__ = "poverty_indices"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "year",
            name="uq_poverty_entity_year",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(
        Integer, ForeignKey("entities.id"), nullable=True
    )  # County or national
    year = Column(Integer, nullable=False, index=True)
    poverty_headcount_rate = Column(Numeric(5, 2), nullable=True)  # Percentage
    extreme_poverty_rate = Column(Numeric(5, 2), nullable=True)  # Percentage
    gini_coefficient = Column(Numeric(4, 3), nullable=True)  # 0-1 scale
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=True
    )
    source_page = Column(Integer, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=True, default=1.0)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    entity = relationship("Entity")
    source_document = relationship("SourceDocument")


class DebtTimeline(Base):
    """Historical public debt composition by year (external vs domestic).

    Source: CBK Annual Reports & National Treasury Budget Policy Statements.
    """

    __tablename__ = "debt_timeline"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False, unique=True, index=True)
    # Money columns are RAW KES (F5.5: they were bare integers meaning
    # billions, recorded nowhere). `unit` makes the convention a queryable
    # fact instead of tribal knowledge; the seeding writer converts at the
    # DB boundary and every consumer reads the declared unit.
    external = Column(Numeric(20, 2), nullable=False)  # raw KES
    domestic = Column(Numeric(20, 2), nullable=False)  # raw KES
    total = Column(Numeric(20, 2), nullable=False)  # raw KES
    gdp = Column(Numeric(20, 2), nullable=True)  # raw KES
    gdp_ratio = Column(Numeric(5, 1), nullable=True)  # e.g. 77.6
    unit = Column(String(10), nullable=False, server_default="KES")
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=True
    )
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    source_document = relationship("SourceDocument")


class DebtInstrument(Base):
    """One redemption line of one government security.

    Source: CBK's "Issues of Treasury Bonds" table
    (https://www.centralbank.go.ke/bills-bonds/treasury-bonds/), extracted by
    seeding/domains/national_debt/cbk_web_tables.py.

    WHAT A ROW IS, AND IS NOT
    -------------------------
    A row is *this much face value redeems on this date*, which is what the CBK
    table asserts. It is keyed on (isin, maturity_date) rather than on ISIN,
    because reading the real table found three reasons one ISIN carries several
    maturities: amortising infrastructure bonds, an ISIN reused across two
    securities, and apparent CBK typos. Keying on ISIN put a bond's whole face
    value on its earliest date and inflated 2027 by more than double.

    These rows are NOT a debt total and must never be summed into one. The
    register covers ~60% of CBK's published Treasury-bond stock — it is drawn
    from bonds sold at auction since 2007 and cannot see pre-2007 paper,
    non-auction issuance or amortisation. It is authoritative on DATES and
    COUPONS, which is what the maturity ladder and any interest calculation
    need, and silent on stock. ``debt_timeline`` and the ``loans`` aggregate
    remain the sources for totals.

    Rows the source cannot settle are not written at all: see
    ``partition_ambiguous``. The count and reason are recorded on the ingestion
    job instead, so an absence is visible rather than inferred.
    """

    __tablename__ = "debt_instruments"
    __table_args__ = (
        UniqueConstraint(
            "isin",
            "maturity_date",
            name="uq_debt_instruments_isin_maturity",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    isin = Column(String(20), nullable=False, index=True)
    issue_no = Column(String(60), nullable=False)
    # fixed_coupon_bond | infrastructure_bond | savings_development_bond | other_bond
    instrument_type = Column(String(40), nullable=False, index=True)

    # Face value redeeming on this date, RAW KES. CBK publishes the table in
    # millions; the writer converts at the DB boundary and `unit` records the
    # convention rather than leaving it to be remembered (same rule as
    # debt_timeline, F5.5).
    face_value = Column(Numeric(20, 2), nullable=False)
    unit = Column(String(10), nullable=False, server_default="KES")

    coupon_rate = Column(Numeric(6, 3), nullable=True)  # annual %, e.g. 14.399
    tenor_years = Column(Numeric(5, 1), nullable=True)
    first_issued = Column(DateTime, nullable=True)
    maturity_date = Column(DateTime, nullable=False, index=True)

    # How many auction tranches were summed into this line. >1 means
    # reopenings of the same security at the same maturity.
    tranches = Column(Integer, nullable=False, server_default="1")

    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=True
    )
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    extraction_id = Column(
        Integer, ForeignKey("extractions.id"), nullable=True, index=True
    )
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    source_document = relationship("SourceDocument")


class FiscalSummary(Base):
    """National fiscal summary per fiscal year.

    Source: National Treasury BPS, Controller of Budget, CBK.
    """

    __tablename__ = "fiscal_summaries"

    id = Column(Integer, primary_key=True, index=True)
    fiscal_year = Column(String(20), nullable=False, unique=True, index=True)
    # Money columns are RAW KES (see DebtTimeline: F5.5). Percentage/ratio
    # columns (borrowing_pct_of_budget, debt_service_per_shilling,
    # debt_ceiling_usage_pct) are unit-free and unaffected.
    appropriated_budget = Column(Numeric(20, 2), nullable=True)  # raw KES
    total_revenue = Column(Numeric(20, 2), nullable=True)  # raw KES
    tax_revenue = Column(Numeric(20, 2), nullable=True)  # raw KES
    non_tax_revenue = Column(Numeric(20, 2), nullable=True)  # raw KES
    total_borrowing = Column(Numeric(20, 2), nullable=True)  # raw KES
    borrowing_pct_of_budget = Column(Numeric(5, 1), nullable=True)
    debt_service_cost = Column(Numeric(20, 2), nullable=True)  # raw KES
    debt_service_per_shilling = Column(Numeric(5, 1), nullable=True)
    debt_ceiling = Column(Numeric(20, 2), nullable=True)  # raw KES
    actual_debt = Column(Numeric(20, 2), nullable=True)  # raw KES
    debt_ceiling_usage_pct = Column(Numeric(5, 1), nullable=True)
    development_spending = Column(Numeric(20, 2), nullable=True)  # raw KES
    recurrent_spending = Column(Numeric(20, 2), nullable=True)  # raw KES
    county_allocation = Column(Numeric(20, 2), nullable=True)  # raw KES
    unit = Column(String(10), nullable=False, server_default="KES")
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=True
    )
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    source_document = relationship("SourceDocument")


class BillType(enum.Enum):
    """Classification of pending bill types."""

    SUPPLIER_ARREARS = "supplier_arrears"
    SALARY = "salary"
    PENSION = "pension"
    STATUTORY = "statutory"
    COURT_AWARDS = "court_awards"
    OTHER = "other"


class PendingBill(Base):
    """Pending bills (unpaid government obligations) with aging and type info.

    Source: Office of the Controller of Budget (OCOB) reports.
    """

    __tablename__ = "pending_bills"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "bill_type", "fiscal_year",
            name="uq_pending_bill_entity_type_fy",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    bill_type = Column(Enum(BillType), nullable=False, default=BillType.SUPPLIER_ARREARS)
    amount = Column(Numeric(15, 2), nullable=False)  # KES
    fiscal_year = Column(String(20), nullable=False, index=True)  # e.g. "2024/25"
    aging_days = Column(Integer, nullable=True)  # days the bill has been pending
    eligible_amount = Column(Numeric(15, 2), nullable=True)
    ineligible_amount = Column(Numeric(15, 2), nullable=True)
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=True
    )
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    entity = relationship("Entity")
    source_document = relationship("SourceDocument")


class RevenueBySource(Base):
    """Revenue collection breakdown by tax type per fiscal year.

    Source: Kenya Revenue Authority (KRA) Annual Revenue Performance Reports,
    KNBS Economic Survey, National Treasury BPS.
    """

    __tablename__ = "revenue_by_source"
    __table_args__ = (
        UniqueConstraint("fiscal_year", "revenue_type", name="uq_revenue_fy_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    fiscal_year = Column(String(20), nullable=False, index=True)
    revenue_type = Column(
        String(60), nullable=False, index=True
    )  # e.g. "Income Tax", "VAT"
    category = Column(
        String(30), nullable=False, default="tax"
    )  # tax | non_tax | grants
    amount_billion_kes = Column(
        Numeric(15, 2), nullable=True
    )  # Billions KES (null for projections)
    target_billion_kes = Column(Numeric(15, 2), nullable=True)  # KRA target
    performance_pct = Column(Numeric(5, 1), nullable=True)  # actual/target × 100
    share_of_total_pct = Column(Numeric(5, 1), nullable=True)  # % of total revenue
    yoy_growth_pct = Column(Numeric(6, 1), nullable=True)  # year-on-year growth
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=True
    )
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Provenance and publication gate (Stage 1) ──────────────────────
    # `publishable` defaults to FALSE: a row is withheld until something
    # proves it may be published. The gate is defined once in
    # services/publication_gate.py and backfilled from there.
    extraction_id = Column(Integer, ForeignKey("extractions.id"), nullable=True, index=True)
    page_ref = Column(String(50), nullable=True)
    source_hash = Column(String(64), nullable=True)
    confidence_score = Column(Float, nullable=True)
    basis = Column(Enum(FigureBasis), nullable=True, index=True)
    publishable = Column(Boolean, nullable=False, server_default=sa_false(), index=True)
    quarantine_reason = Column(String(120), nullable=True)

    # Relationships
    source_document = relationship("SourceDocument")


# ===== Parliament & Accountability Expansion Models =====


class ParliamentDocType(enum.Enum):
    """Classification of Parliament library documents."""

    AUDIT_REPORT = "audit_report"
    COMMITTEE_REPORT = "committee_report"
    BUDGET_ESTIMATE = "budget_estimate"
    GREEN_BOOK = "green_book"
    HANSARD = "hansard"
    BILL = "bill"
    ACT = "act"
    POLICY_DOCUMENT = "policy_document"
    OTHER = "other"


class AuditOpinion(enum.Enum):
    """Standardised OAG audit opinions."""

    UNQUALIFIED = "unqualified"
    QUALIFIED = "qualified"
    ADVERSE = "adverse"
    DISCLAIMER = "disclaimer"


class FiscalYear(Base):
    """Canonical fiscal year reference table.

    Kenya's fiscal year runs July 1 - June 30.
    This complements FiscalPeriod but is simpler and keyed on the 'YYYY/YY' label.
    """

    __tablename__ = "fiscal_years"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(
        String(20), unique=True, nullable=False, index=True
    )  # e.g. "2023/24"
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CountyOrgUnit(Base):
    """Sub-county administrative units within a county entity.

    Enables linking audit findings to wards, sub-counties, or specific
    county departments when reports provide that granularity.
    """

    __tablename__ = "county_org_units"
    __table_args__ = (
        UniqueConstraint("entity_id", "name", name="uq_county_org_entity_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(
        Integer, ForeignKey("entities.id"), nullable=False, index=True
    )  # parent county entity
    name = Column(String(200), nullable=False)
    unit_type = Column(
        String(50), nullable=False, default="sub_county"
    )  # sub_county | ward | department
    code = Column(String(20), nullable=True)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    entity = relationship("Entity")


class Constituency(Base):
    """National Assembly constituencies, each linked to a parent county.

    Useful for mapping constituency-level audit findings and budget allocations
    (e.g. CDF / NG-CDF disbursements).
    """

    __tablename__ = "constituencies"
    __table_args__ = (
        UniqueConstraint("name", name="uq_constituency_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(20), nullable=True, unique=True, index=True)
    county_entity_id = Column(
        Integer, ForeignKey("entities.id"), nullable=False, index=True
    )  # parent county
    population = Column(Integer, nullable=True)
    registered_voters = Column(Integer, nullable=True)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    county_entity = relationship("Entity")


class NationalEntity(Base):
    """Extended detail for national-level audited entities
    (state corporations, commissions, funds, etc.).

    These are entities that appear in OAG audit reports but are not counties
    or ministries.  Linking them here provides richer metadata for resolution.
    """

    __tablename__ = "national_entities"
    __table_args__ = (
        UniqueConstraint("entity_id", name="uq_national_entity"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Uniqueness + the FK-lookup index come from the uq_national_entity
    # UniqueConstraint above; a column-level unique/index here would be a
    # duplicate (Supabase "Duplicate Index" advisor). See migration j0e1f2a3b4c5.
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    parent_ministry_entity_id = Column(
        Integer, ForeignKey("entities.id"), nullable=True
    )
    establishment_act = Column(String(300), nullable=True)
    website = Column(String(300), nullable=True)
    category = Column(
        String(50), nullable=True
    )  # commercial | regulatory | executive_agency | constitutional_commission
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    entity = relationship("Entity", foreign_keys=[entity_id])
    parent_ministry = relationship("Entity", foreign_keys=[parent_ministry_entity_id])


class ParliamentSourceDocument(Base):
    """Parliament-specific metadata extension for source_documents.

    Rather than widening the source_documents table directly, this is a
    companion table linked 1:1 via source_document_id.  It stores DSpace
    metadata, committee references, and tabling dates.
    """

    __tablename__ = "parliament_source_documents"
    __table_args__ = (
        UniqueConstraint("source_document_id", name="uq_parliament_src_doc"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Uniqueness + the FK-lookup index come from the uq_parliament_src_doc
    # UniqueConstraint above; a column-level unique/index here would be a
    # duplicate (Supabase "Duplicate Index" advisor). See migration j0e1f2a3b4c5.
    source_document_id = Column(
        Integer, ForeignKey("source_documents.id"), nullable=False
    )
    dspace_uuid = Column(String(64), nullable=True, unique=True, index=True)
    dspace_handle = Column(String(100), nullable=True)
    collection_uuid = Column(String(64), nullable=True)
    community_uuid = Column(String(64), nullable=True)
    parliament_doc_type = Column(
        Enum(ParliamentDocType, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
    )
    tabling_date = Column(DateTime, nullable=True)
    fiscal_year_label = Column(String(20), nullable=True)  # e.g. "2022/23"
    committee_name = Column(String(200), nullable=True)
    entity_table = Column(String(50), nullable=True)  # polymorphic ref: "entities" etc.
    entity_ref_id = Column(Integer, nullable=True)  # polymorphic FK
    audit_opinion = Column(
        Enum(AuditOpinion, values_callable=lambda e: [x.value for x in e]),
        nullable=True,
    )
    confidence_score = Column(Numeric(3, 2), nullable=True)
    meta = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    source_document = relationship("SourceDocument")


class AdminAuditLog(Base):
    """
    Append-only log of admin write actions.

    Every destructive or privileged operation in the admin API
    (modifying user roles, deleting users, manually triggering ETL,
    etc.) records a row here so we have a "who did what, when"
    trail. Read-only operations are NOT logged — only mutations.

    Schema design:
    - ``actor_id`` is the Supabase user UUID of the admin performing
      the action (from the JWT ``sub`` claim).
    - ``action`` is a short stable identifier like
      ``"users.update_roles"`` or ``"etl.trigger"`` — these strings
      become the filterable axis on the admin audit-log UI.
    - ``target_type`` + ``target_id`` describe what the action was
      performed on (``"user"`` + a UUID, ``"etl_source"`` + ``"cob"``,
      etc.). Both nullable for actions that have no specific target.
    - ``payload`` is the JSON body of the action — the
      ``{old: [...], new: [...]}`` for a role change, the request
      body for a trigger, etc. Useful for forensics; sensitive bits
      (passwords, tokens) MUST be redacted before this is written.
    """

    __tablename__ = "admin_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(String(64), nullable=False, index=True)
    actor_email = Column(String(255), nullable=True)
    action = Column(String(80), nullable=False, index=True)
    target_type = Column(String(40), nullable=True, index=True)
    target_id = Column(String(64), nullable=True, index=True)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
