"""Explicit county borrowing identities and dated observations; no backfill.

Existing Loan uniqueness, creditor aggregates, arrears and Treasury redemption
lines are untouched. Downgrade refuses populated new tables: export/reconcile
those accounts explicitly before removal rather than silently lose evidence.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from alembic import op

revision = "c415a10d2026"
down_revision = "ea1645a4c0b5"
branch_labels = None
depends_on = None


def upgrade():
    category = ENUM(
        "EXTERNAL_MULTILATERAL",
        "EXTERNAL_BILATERAL",
        "EXTERNAL_COMMERCIAL",
        "DOMESTIC_BONDS",
        "DOMESTIC_BILLS",
        "DOMESTIC_OVERDRAFT",
        "PENDING_BILLS",
        "COUNTY_GUARANTEED",
        "OTHER",
        name="debtcategory",
        create_type=False,
    )
    basis = ENUM(
        "ACTUAL", "MODELLED", "PROJECTED", name="figurebasis", create_type=False
    )
    op.create_table(
        "county_debt_instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entity_id", sa.Integer(), sa.ForeignKey("entities.id"), nullable=False
        ),
        sa.Column("identity_namespace", sa.String(120), nullable=False),
        sa.Column("instrument_reference", sa.String(200), nullable=False),
        sa.Column("lender", sa.String(200), nullable=False),
        sa.Column("issue_date", sa.DateTime(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("debt_category", category, nullable=False),
        sa.UniqueConstraint(
            "entity_id",
            "identity_namespace",
            "instrument_reference",
            name="uq_county_debt_identity",
        ),
        sa.CheckConstraint(
            "trim(identity_namespace) <> '' AND trim(instrument_reference) <> '' AND identity_namespace = trim(identity_namespace) AND instrument_reference = trim(instrument_reference)",
            name="ck_county_debt_explicit_identity",
        ),
        sa.CheckConstraint(
            "debt_category <> 'PENDING_BILLS'", name="ck_county_debt_not_arrears"
        ),
    )
    op.create_table(
        "county_debt_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("county_debt_instruments.id"),
            nullable=False,
        ),
        sa.Column("as_at", sa.Date(), nullable=False),
        sa.Column(
            "source_document_id",
            sa.Integer(),
            sa.ForeignKey("source_documents.id"),
            nullable=False,
        ),
        sa.Column("page_ref", sa.String(50), nullable=False),
        sa.Column("basis", basis, nullable=False),
        sa.Column("principal", sa.Numeric(20, 2), nullable=True),
        sa.Column("outstanding", sa.Numeric(20, 2), nullable=True),
        sa.Column("interest_rate", sa.Numeric(6, 3), nullable=True),
        sa.Column("provenance", JSONB(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("quarantine_reason", sa.String(120), nullable=True),
        sa.UniqueConstraint(
            "instrument_id",
            "as_at",
            "source_document_id",
            name="uq_county_debt_observation",
        ),
        sa.CheckConstraint(
            "principal IS NULL OR (principal >= 0 AND principal <> 'NaN')",
            name="ck_county_debt_principal",
        ),
        sa.CheckConstraint(
            "outstanding IS NULL OR (outstanding >= 0 AND outstanding <> 'NaN')",
            name="ck_county_debt_outstanding",
        ),
        sa.CheckConstraint(
            "interest_rate IS NULL OR (interest_rate >= 0 AND interest_rate <> 'NaN')",
            name="ck_county_debt_rate",
        ),
    )
    op.create_index(
        "ix_county_debt_observations_source_document_id",
        "county_debt_observations",
        ["source_document_id"],
    )


def downgrade():
    bind = op.get_bind()
    # Hold the empty-evidence decision through table removal. A concurrent
    # writer must commit before this lock (then the check refuses) or wait
    # until removal (then its insert fails), never commit between check/drop.
    bind.execute(
        sa.text(
            "LOCK TABLE county_debt_instruments, county_debt_observations IN ACCESS EXCLUSIVE MODE"
        )
    )
    if bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM county_debt_instruments) OR EXISTS (SELECT 1 FROM county_debt_observations)"
        )
    ).scalar():
        raise RuntimeError(
            "County debt evidence exists; export/reconcile it before downgrade"
        )
    op.drop_index(
        "ix_county_debt_observations_source_document_id",
        table_name="county_debt_observations",
    )
    op.drop_table("county_debt_observations")
    op.drop_table("county_debt_instruments")
