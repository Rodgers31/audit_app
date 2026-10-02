"""refile the nine-month CBIRR under FY2025/26 9M

Revision ID: b8c4e2d17a90
Revises: a2f7c1b48d90
Create Date: 2026-09-26

DO NOT MERGE UNTIL THE PENDING-BILLS CODE IS DEPLOYED. Merging applies this
(ci.yml run-migrations, before the manual deploy). It creates a second county
period starting 2025-07-01 ("FY2025/26 9M"), and the code on main before that
PR orders county periods by start date only (_latest_county_period), so in 2 of
4 row orderings it would pick the part-year and publish the category over-sum
that PR fixes (consolidation review, 2026-09-27). It ships in one chain with
62a9f4131819 and ea1645a4c0b5, which has the same requirement.

Issue #238 §2. Measured against a ``pg_dump`` of production taken 2026-09-26
(stamped ``a2f7c1b48d90``).

The Controller of Budget's "County Governments Budget Implementation Review
Report for the First Nine Months of FY 2025/26" (May 2026) is source document
2388 in production, at

    https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-first-nine-months-of-fy-2025-26/?wpdmdl=16378

Its cover reads "FIRST NINE MONTHS OF FY 2025/26"; its introduction says it
"covers the first nine months of the 2025/26 financial year, specifically from
July 2025 to March 2026" (PDF p.54). All 188 county rows parsed from it sit in
period FY2024/25:

    label     | category           | rows | allocated KSh bn
    FY2024/25 | Total              |   47 |   633.30
    FY2024/25 | Recurrent          |   47 |   398.97
    FY2024/25 | Development        |   47 |   234.33
    FY2024/25 | Own Source Revenue |   47 |   100.13

because ``CoBQuarterlyReportParser`` read the year from the PDF's filename —
a sha256 in the PDF cache — and fell back to a hardcoded "2024/25". The parser
now reads the cover (same PR), so no new rows land in the wrong year, and the
writer moves a re-parsed document's rows out of any period it no longer files
them under. But the nightly now discovers the Controller's FULL-YEAR FY2025/26
report instead, so this document is never re-parsed and its rows would stay
mislabelled for good. This moves them.

An independent check that FY2024/25 is wrong: the Treasury BROP 2025 row for
Nairobi, already in production, notes "FY budget 43,564,270,000" for FY2024/25;
these rows give Nairobi 44,620,890,000 — the CBIRR's FY2025/26 figure.

Scope, and nothing else: rows of THAT document (exact URL), in FY2024/25, on
county entities. A row that already exists at the target key is left where it
is and reported, never overwritten. Replaying this on a database without the
document does nothing. The document's title, which the writer derived from the
same wrong year, is corrected with it.
"""
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "b8c4e2d17a90"
down_revision = "a2f7c1b48d90"
branch_labels = None
depends_on = None

NINE_MONTH_CBIRR_URL = (
    "https://cob.go.ke/download/county-governments-budget-implementation-"
    "review-report-for-the-first-nine-months-of-fy-2025-26/?wpdmdl=16378"
)
WRONG_LABEL = "FY2024/25"
RIGHT_LABEL = "FY2025/26 9M"
RIGHT_TITLE = "Controller of Budget County BIRR FY2025/26 9M"


def upgrade():
    bind = op.get_bind()
    docs = bind.execute(
        text("SELECT id, country_id FROM source_documents WHERE url = :url"),
        {"url": NINE_MONTH_CBIRR_URL},
    ).fetchall()
    if not docs:
        print("nine-month CBIRR not in this database; nothing to refile")
        return

    for doc_id, country_id in docs:
        wrong = bind.execute(
            text(
                "SELECT id FROM fiscal_periods "
                "WHERE country_id = :c AND label = :l"
            ),
            {"c": country_id, "l": WRONG_LABEL},
        ).scalar()
        if wrong is None:
            continue
        right = bind.execute(
            text(
                "SELECT id FROM fiscal_periods "
                "WHERE country_id = :c AND label = :l"
            ),
            {"c": country_id, "l": RIGHT_LABEL},
        ).scalar()
        if right is None:
            right = bind.execute(
                text(
                    "INSERT INTO fiscal_periods (country_id, label, start_date, end_date) "
                    "VALUES (:c, :l, '2025-07-01', '2026-03-31 23:59:59') RETURNING id"
                ),
                {"c": country_id, "l": RIGHT_LABEL},
            ).scalar()

        moved = bind.execute(
            text(
                """
                UPDATE budget_lines AS bl
                   SET period_id = :right
                 WHERE bl.source_document_id = :doc
                   AND bl.period_id = :wrong
                   AND bl.entity_id IN (SELECT id FROM entities WHERE type = 'COUNTY')
                   AND NOT EXISTS (
                       SELECT 1 FROM budget_lines AS other
                        WHERE other.entity_id = bl.entity_id
                          AND other.period_id = :right
                          AND other.category = bl.category
                          AND other.subcategory IS NOT DISTINCT FROM bl.subcategory
                   )
                """
            ),
            {"right": right, "doc": doc_id, "wrong": wrong},
        ).rowcount
        left = bind.execute(
            text(
                "SELECT count(*) FROM budget_lines WHERE source_document_id = :doc "
                "AND period_id = :wrong"
            ),
            {"doc": doc_id, "wrong": wrong},
        ).scalar()
        bind.execute(
            text("UPDATE source_documents SET title = :t WHERE id = :doc"),
            {"t": RIGHT_TITLE, "doc": doc_id},
        )
        print(
            f"nine-month CBIRR (document {doc_id}): moved {moved} county row(s) "
            f"{WRONG_LABEL} -> {RIGHT_LABEL}; {left} row(s) left in "
            f"{WRONG_LABEL} because the target already held that key; "
            "changes are in the current transaction, pending commit"
        )


def downgrade():
    # Not reversed. Putting the rows back would re-file the Controller of
    # Budget's FY2025/26 report under FY2024/25, which is the defect this
    # corrects; nothing reads the old placement.
    pass
