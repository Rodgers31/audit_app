"""add parliament expansion tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-02

Adds:
  - Extended EntityType enum values (state_corporation, judiciary, commission, fund, constituency, sub_county)
  - fiscal_years table
  - county_org_units table
  - constituencies table
  - national_entities table
  - parliament_source_documents table
  - ParliamentDocType enum
  - AuditOpinion enum
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    # --- Extend EntityType enum with new values ---
    # PostgreSQL enums can be extended with ADD VALUE (non-transactional)
    op.execute("ALTER TYPE entitytype ADD VALUE IF NOT EXISTS 'state_corporation'")
    op.execute("ALTER TYPE entitytype ADD VALUE IF NOT EXISTS 'judiciary'")
    op.execute("ALTER TYPE entitytype ADD VALUE IF NOT EXISTS 'commission'")
    op.execute("ALTER TYPE entitytype ADD VALUE IF NOT EXISTS 'fund'")
    op.execute("ALTER TYPE entitytype ADD VALUE IF NOT EXISTS 'constituency'")
    op.execute("ALTER TYPE entitytype ADD VALUE IF NOT EXISTS 'sub_county'")

    # --- Create ParliamentDocType enum ---
    parliament_doc_type_enum = sa.Enum(
        "audit_report",
        "committee_report",
        "budget_estimate",
        "green_book",
        "hansard",
        "bill",
        "act",
        "policy_document",
        "other",
        name="parliamentdoctype",
    )
    parliament_doc_type_enum.create(op.get_bind(), checkfirst=True)

    # --- Create AuditOpinion enum ---
    audit_opinion_enum = sa.Enum(
        "unqualified",
        "qualified",
        "adverse",
        "disclaimer",
        name="auditopinion",
    )
    audit_opinion_enum.create(op.get_bind(), checkfirst=True)

    # --- fiscal_years ---
    op.create_table(
        "fiscal_years",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("label", sa.String(20), nullable=False, unique=True, index=True),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("end_date", sa.DateTime(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
        ),
    )

    # --- county_org_units ---
    op.create_table(
        "county_org_units",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "entity_id",
            sa.Integer(),
            sa.ForeignKey("entities.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("unit_type", sa.String(50), nullable=False, server_default="sub_county"),
        sa.Column("code", sa.String(20), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("entity_id", "name", name="uq_county_org_entity_name"),
    )

    # --- constituencies ---
    op.create_table(
        "constituencies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(20), nullable=True, unique=True, index=True),
        sa.Column(
            "county_entity_id",
            sa.Integer(),
            sa.ForeignKey("entities.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column("registered_voters", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_constituency_name"),
    )

    # --- national_entities ---
    op.create_table(
        "national_entities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "entity_id",
            sa.Integer(),
            sa.ForeignKey("entities.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "parent_ministry_entity_id",
            sa.Integer(),
            sa.ForeignKey("entities.id"),
            nullable=True,
        ),
        sa.Column("establishment_act", sa.String(300), nullable=True),
        sa.Column("website", sa.String(300), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("entity_id", name="uq_national_entity"),
    )

    # --- parliament_source_documents ---
    op.create_table(
        "parliament_source_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_document_id",
            sa.Integer(),
            sa.ForeignKey("source_documents.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("dspace_uuid", sa.String(64), nullable=True, unique=True, index=True),
        sa.Column("dspace_handle", sa.String(100), nullable=True),
        sa.Column("collection_uuid", sa.String(64), nullable=True),
        sa.Column("community_uuid", sa.String(64), nullable=True),
        sa.Column(
            "parliament_doc_type",
            postgresql.ENUM(
                "audit_report",
                "committee_report",
                "budget_estimate",
                "green_book",
                "hansard",
                "bill",
                "act",
                "policy_document",
                "other",
                name="parliamentdoctype",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("tabling_date", sa.DateTime(), nullable=True),
        sa.Column("fiscal_year_label", sa.String(20), nullable=True),
        sa.Column("committee_name", sa.String(200), nullable=True),
        sa.Column("entity_table", sa.String(50), nullable=True),
        sa.Column("entity_ref_id", sa.Integer(), nullable=True),
        sa.Column(
            "audit_opinion",
            postgresql.ENUM(
                "unqualified",
                "qualified",
                "adverse",
                "disclaimer",
                name="auditopinion",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("source_document_id", name="uq_parliament_src_doc"),
    )


def downgrade():
    op.drop_table("parliament_source_documents")
    op.drop_table("national_entities")
    op.drop_table("constituencies")
    op.drop_table("county_org_units")
    op.drop_table("fiscal_years")

    # Drop enums
    sa.Enum(name="auditopinion").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="parliamentdoctype").drop(op.get_bind(), checkfirst=True)

    # NOTE: PostgreSQL does not support removing individual enum values.
    # The extended EntityType values will remain but are harmless.
