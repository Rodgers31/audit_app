"""stage1 3a: raw-KES units for debt_timeline and fiscal_summaries

Revision ID: 6ce655115689
Revises: b3d8ab47bf3b
Create Date: 2026-08-29

F5.5: both tables stored KES BILLIONS as bare numbers with nothing in the
schema recording it — ``debt_timeline.total = 12500`` meant 12.5 trillion,
and every consumer carried the convention as tribal knowledge (one frontend
component annotated it with a comment; another multiplied by 1e9 inline).

This migration:

1. Widens the money columns to NUMERIC(20,2) — raw-KES totals (~1.3e13)
   overflow the old NUMERIC(15,2).
2. Multiplies stored values by 1e9, guarded by ``value < 1e6``: a genuine
   raw-KES national aggregate is >= 1e9 and a billions-encoded one is
   < 1e6, so the update is idempotent and safe on a partially-converted
   table. Percentage/ratio columns are untouched.
3. Adds ``unit VARCHAR(10) NOT NULL DEFAULT 'KES'`` to both tables, so
   the convention is a declared fact the API serves and the frontend
   reads — never a guess.
4. Asserts the A.4 unit-sanity invariant afterwards (national debt total
   in [1e11, 5e13] raw KES) and aborts the transaction on violation.

MUST land together with the frontend change (NationalDebtCard /
HeroSection and the other timeline/fiscal consumers reading the declared
unit) — converting one side alone makes the homepage wrong by 1e9.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6ce655115689'
down_revision = 'b3d8ab47bf3b'
branch_labels = None
depends_on = None


DEBT_TIMELINE_MONEY = ("external", "domestic", "total", "gdp")
FISCAL_SUMMARY_MONEY = (
    "appropriated_budget",
    "total_revenue",
    "tax_revenue",
    "non_tax_revenue",
    "total_borrowing",
    "debt_service_cost",
    "debt_ceiling",
    "actual_debt",
    "development_spending",
    "recurrent_spending",
    "county_allocation",
)

# A billions-encoded national aggregate is < 1e6; a raw-KES one is >= 1e9.
# Values in between exist in neither convention, so both directions of the
# conversion are unambiguous and idempotent.
BILLIONS_CEILING = 1_000_000


def _widen(table: str, columns: tuple) -> None:
    for col in columns:
        op.alter_column(
            table,
            col,
            type_=sa.Numeric(20, 2),
            existing_type=sa.Numeric(15, 2),
        )


def _narrow(table: str, columns: tuple) -> None:
    for col in columns:
        op.alter_column(
            table,
            col,
            type_=sa.Numeric(15, 2),
            existing_type=sa.Numeric(20, 2),
        )


def upgrade():
    bind = op.get_bind()

    _widen("debt_timeline", DEBT_TIMELINE_MONEY)
    _widen("fiscal_summaries", FISCAL_SUMMARY_MONEY)

    for table, columns in (
        ("debt_timeline", DEBT_TIMELINE_MONEY),
        ("fiscal_summaries", FISCAL_SUMMARY_MONEY),
    ):
        for col in columns:
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET {col} = {col} * 1e9 "
                    f"WHERE {col} IS NOT NULL AND {col} < :ceiling"
                ),
                {"ceiling": BILLIONS_CEILING},
            )
        op.add_column(
            table,
            sa.Column(
                "unit",
                sa.String(length=10),
                nullable=False,
                server_default="KES",
            ),
        )

    # A.4 unit sanity — a failed conversion must abort, not persist.
    bad_debt = bind.execute(
        sa.text(
            "SELECT count(*) FROM debt_timeline "
            "WHERE total NOT BETWEEN 1e11 AND 5e13"
        )
    ).scalar()
    bad_fiscal = bind.execute(
        sa.text(
            "SELECT count(*) FROM fiscal_summaries "
            "WHERE appropriated_budget IS NOT NULL "
            "AND appropriated_budget NOT BETWEEN 1e11 AND 2e13"
        )
    ).scalar()
    if bad_debt or bad_fiscal:
        raise RuntimeError(
            f"Unit-sanity invariant violated after conversion: "
            f"{bad_debt} debt_timeline totals and {bad_fiscal} "
            f"fiscal_summaries budgets outside plausible raw-KES bounds. "
            f"Transaction aborted; nothing was persisted."
        )


def downgrade():
    bind = op.get_bind()
    for table, columns in (
        ("debt_timeline", DEBT_TIMELINE_MONEY),
        ("fiscal_summaries", FISCAL_SUMMARY_MONEY),
    ):
        op.drop_column(table, "unit")
        for col in columns:
            # Reverse of the upgrade guard: only raw-KES values divide.
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET {col} = {col} / 1e9 "
                    f"WHERE {col} IS NOT NULL AND {col} >= 1e9"
                )
            )
    _narrow("debt_timeline", DEBT_TIMELINE_MONEY)
    _narrow("fiscal_summaries", FISCAL_SUMMARY_MONEY)
