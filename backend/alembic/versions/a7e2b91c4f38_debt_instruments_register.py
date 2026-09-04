"""instrument-level debt register: the debt_instruments table

Kenya's debt was published on this site as 28 aggregate buckets. Three of them
carried a maturity date, five separate Eurobond issues sat on one 2034 date,
and a single assumed 14.5% coupon was applied to the whole domestic bond book —
from which the homepage derived "ANNUAL SERVICE COST KES 1.27T". The maturity
ladder and the lender treemap were withdrawn before launch because no amount of
frontend work substitutes for instrument data (credibility audit F24/F42).

CBK publishes the instruments. Not in the Statistical Bulletin — which is why
an earlier investigation (PR #75) concluded they were unavailable — but as a
data table at /bills-bonds/treasury-bonds/, carrying ISIN, tenor, face value,
maturity date and coupon per auction tranche. This table holds what
``seeding/domains/national_debt/cbk_web_tables.py`` extracts from it.

WHAT A ROW IS
-------------
One redemption line: this much face value redeems on this date. Keyed on
(isin, maturity_date), NOT on isin — reading the real table found three reasons
one ISIN carries several maturities (amortising infrastructure bonds, an ISIN
reused across two securities, apparent CBK typos), and keying on ISIN put a
bond's whole face value on its earliest date, inflating 2027 by more than
double.

WHAT IT IS NOT
--------------
A debt total. The register covers ~60% of CBK's published Treasury-bond stock:
it sees bonds sold at auction since 2007 and cannot see pre-2007 paper,
non-auction issuance or amortisation. Summing it into a headline would trade a
correct total for a lower wrong one, which is the shape of the finding this
whole body of work started from. ``debt_timeline`` and the ``loans`` aggregate
remain the sources for totals; this table is authoritative on DATES and
COUPONS and silent on stock.

SCOPE
-----
One new table and nothing else. ``alembic revision --autogenerate`` against a
migrated clone proposes ~274 unrelated operations — the accumulated drift
between a schema grown by hand and one generated from ``models.py`` (see
d1a7c9e40b12's note and issue #137). None of them is this table, and several
would drop deliberate performance indexes. That reconciliation is its own piece
of work with its own review.

PRODUCTION
----------
Production is still on the orphaned ``k1f2a3b4c5d6`` and has never run this
chain. This migration is written to be correct from BOTH starting points — a
clean replay from the ``21d0394c1d6b`` baseline, and a drifted production — by
checking what exists rather than assuming. It has NOT been applied to
production; per STAGE3 that needs the stamp --purge procedure rehearsed on a
pg_dump clone first, and the user's say-so.
"""

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

logger = logging.getLogger("alembic.stage1")

revision = "a7e2b91c4f38"
down_revision = "d1a7c9e40b12"
branch_labels = None
depends_on = None

TABLE = "debt_instruments"


def _table_exists(name: str) -> bool:
    """Checked, not assumed.

    The baseline was generated from ``models.py`` as it stood then, so it does
    NOT contain this table and a clean replay needs it created. But a database
    built by ``Base.metadata.create_all`` — which is what the test suite and
    some local setups use — already has it, and ``create_table`` would fail
    there with DuplicateTable. The same migration has to be correct from both.
    """
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _jsonb():
    """JSONB on Postgres, JSON elsewhere.

    conftest runs the suite on in-memory SQLite, which has no JSONB. The models
    register a compiler for it (conftest.py:32) but a migration builds its own
    types, so pick per-dialect here rather than emit SQL SQLite cannot execute.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if _table_exists(TABLE):
        logger.info("%s already exists; nothing to create", TABLE)
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("isin", sa.String(length=20), nullable=False),
        sa.Column("issue_no", sa.String(length=60), nullable=False),
        sa.Column("instrument_type", sa.String(length=40), nullable=False),
        # Face value redeeming on this date, RAW KES. CBK publishes the source
        # table in millions; the writer converts at the DB boundary and `unit`
        # records the convention rather than leaving it to be remembered —
        # the same rule debt_timeline adopted after F5.5, where bare integers
        # meaning billions were recorded nowhere.
        sa.Column("face_value", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("unit", sa.String(length=10), server_default="KES", nullable=False),
        sa.Column("coupon_rate", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("tenor_years", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("first_issued", sa.DateTime(), nullable=True),
        sa.Column("maturity_date", sa.DateTime(), nullable=False),
        sa.Column("tranches", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("metadata", _jsonb(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("extraction_id", sa.Integer(), nullable=True),
        sa.Column("page_ref", sa.String(length=50), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        # Withheld until something proves it may be published — the same
        # default every fact table carries since b3d8ab47bf3b.
        sa.Column(
            "publishable",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("quarantine_reason", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["extraction_id"], ["extractions.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        # A security may redeem on several dates (an amortising IFB), but one
        # security cannot redeem twice on the SAME date. This is the key the
        # writer upserts on; without it a re-run duplicates the register.
        sa.UniqueConstraint("isin", "maturity_date", name="uq_debt_instruments_isin_maturity"),
    )
    op.create_index(op.f("ix_debt_instruments_id"), TABLE, ["id"])
    op.create_index(op.f("ix_debt_instruments_isin"), TABLE, ["isin"])
    op.create_index(op.f("ix_debt_instruments_instrument_type"), TABLE, ["instrument_type"])
    # The maturity ladder groups by year over publishable rows; that is the
    # only query this table exists to serve at speed.
    op.create_index(op.f("ix_debt_instruments_maturity_date"), TABLE, ["maturity_date"])
    op.create_index(op.f("ix_debt_instruments_publishable"), TABLE, ["publishable"])
    op.create_index(op.f("ix_debt_instruments_extraction_id"), TABLE, ["extraction_id"])
    logger.info("created %s", TABLE)


def downgrade() -> None:
    """Drops the table — and here that is safe, unlike d1a7c9e40b12.

    The rule that migration settled is "never drop a column you cannot prove
    you created". It applies to columns on tables that predate the migration,
    where a downgrade cannot tell a clean replay from production. This
    migration OWNS the whole table: nothing before it references
    debt_instruments, so on either path dropping it returns the schema to a
    working d1a7c9e40b12 state.

    Guarded anyway, so a downgrade against a database that never got the table
    is a no-op rather than an error.
    """
    if not _table_exists(TABLE):
        logger.info("%s does not exist; nothing to drop", TABLE)
        return
    op.drop_table(TABLE)
    logger.info("dropped %s", TABLE)
