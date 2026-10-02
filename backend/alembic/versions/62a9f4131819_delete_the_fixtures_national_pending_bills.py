"""delete the pending-bills fixture's eleven national rows

Revision ID: 62a9f4131819
Revises: b8c4e2d17a90
Create Date: 2026-09-27

DO NOT MERGE WITHOUT THE OWNER'S SIGN-OFF. Merging this applies it: ci.yml's
run-migrations step runs ``alembic upgrade head`` against production on every
push to main. It deletes rows from production.

Issue #265. Measured against production on 2026-09-27, read-only
(``BEGIN READ ONLY``; ``transaction_read_only = on``; a probe INSERT was
refused). Production was stamped ``a2f7c1b48d90`` at the time.

``GET /api/v1/pending-bills`` served ``national_total = 931.3B``. The Treasury's
Budget Review and Outlook Paper 2025, para 18 (PDF p.18), prints 525.9B —
404.3B State Corporations + 121.6B MDAs, the whole National Government. Those
two lines are loans 398 and 399 (source document 2383, the BROP). The other
405.4B is eleven rows the pending-bills writer took from the git fixture
``backend/seeding/fixtures/pending_bills.json`` on a night the BROP fetch
failed (last updated 2026-07-09):

    id   KSh bn  lender
    385   89.7   Pending Bills — MDAs (Ministry of Health)
    386   76.3   Pending Bills — MDAs (Ministry of Roads and Transport)
    387   45.2   Pending Bills — MDAs (Ministry of Education)
    388   32.1   Pending Bills — MDAs (Ministry of Interior and National Administration)
    389   28.9   Pending Bills — MDAs (Ministry of Defence)
    390   24.6   Pending Bills — MDAs (Ministry of Water, Sanitation and Irrigation)
    391   18.4   Pending Bills — MDAs (Ministry of Energy and Petroleum)
    392   15.8   Pending Bills — MDAs (State Department for Public Works)
    393   42.3   Pending Bills — State Corporations (Kenya National Highways Authority (KeNHA))
    394   19.7   Pending Bills — State Corporations (Kenya Rural Roads Authority (KeRRA))
    395   12.4   Pending Bills — State Corporations (Kenya Power and Lighting Company (KPLC))
               405.4

All on the National Government entity, all citing source document 1839
("Controller of Budget — National Government Budget Implementation Review
Report FY 2024/25", url https://cob.go.ke/reports/pending-bills/, which
resolves to a pending-bills action-plan TEMPLATE). The figures are round tenths
of a billion that no publication prints; the ministries and corporations are
members of the BROP's two lines, so summing them with it counted the same
bills twice.

The code PR for #265 already withholds these rows: no reader counts a row that
does not declare ``provenance.publication = "treasury_brop"``, and the writer no
longer writes a fixture payload at all. This migration removes them so that
nothing — ``/provenance/verify/pending_bills``, an ad-hoc query, a future
reader that forgets the gate — can find them.

Scope, and nothing else: PENDING_BILLS loans on a NATIONAL entity, citing a
document at the fixture's URL, under one of the eleven lenders above, that do
NOT declare the BROP. The ids are not used — a clone or a re-seeded database
numbers them differently. It refuses, and deletes nothing, if the predicate
matches more than eleven rows. Replaying it on a database without the rows
does nothing. Source document 1839 is left in place; after this nothing in
``loans`` cites it.
"""
from alembic import op
from sqlalchemy import bindparam, text

# revision identifiers, used by Alembic.
revision = "62a9f4131819"
down_revision = "b8c4e2d17a90"
branch_labels = None
depends_on = None

FIXTURE_SOURCE_URL = "https://cob.go.ke/reports/pending-bills/"
FIXTURE_LENDERS = (
    "Pending Bills — MDAs (Ministry of Health)",
    "Pending Bills — MDAs (Ministry of Roads and Transport)",
    "Pending Bills — MDAs (Ministry of Education)",
    "Pending Bills — MDAs (Ministry of Interior and National Administration)",
    "Pending Bills — MDAs (Ministry of Defence)",
    "Pending Bills — MDAs (Ministry of Water, Sanitation and Irrigation)",
    "Pending Bills — MDAs (Ministry of Energy and Petroleum)",
    "Pending Bills — MDAs (State Department for Public Works)",
    "Pending Bills — State Corporations (Kenya National Highways Authority (KeNHA))",
    "Pending Bills — State Corporations (Kenya Rural Roads Authority (KeRRA))",
    "Pending Bills — State Corporations (Kenya Power and Lighting Company (KPLC))",
)

_TARGET = """
    FROM loans AS l
    JOIN entities AS e ON e.id = l.entity_id
    JOIN source_documents AS s ON s.id = l.source_document_id
   WHERE l.debt_category = 'PENDING_BILLS'
     AND e.type = 'NATIONAL'
     AND s.url = :url
     AND l.lender IN :lenders
     AND COALESCE(l.provenance ->> 'publication', '') <> 'treasury_brop'
"""


def upgrade():
    bind = op.get_bind()
    params = {"url": FIXTURE_SOURCE_URL, "lenders": list(FIXTURE_LENDERS)}
    select = text(
        "SELECT l.id, l.lender, l.outstanding" + _TARGET + " ORDER BY l.id"
    ).bindparams(bindparam("lenders", expanding=True))
    rows = bind.execute(select, params).fetchall()
    if not rows:
        print("pending-bills fixture national rows: none in this database")
        return
    if len(rows) > len(FIXTURE_LENDERS):
        raise RuntimeError(
            f"refusing: {len(rows)} rows match the fixture predicate, expected at "
            f"most {len(FIXTURE_LENDERS)} — ids {[r[0] for r in rows]}"
        )
    ids = [r[0] for r in rows]
    deleted = bind.execute(
        text("DELETE FROM loans WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ),
        {"ids": ids},
    ).rowcount
    total = sum(float(r[2] or 0) for r in rows)
    print(
        f"pending-bills fixture national rows: deleted {deleted} "
        f"(ids {ids}, KSh {total / 1e9:,.1f}bn); "
        "changes are in the current transaction, pending commit"
    )


def downgrade():
    # Not reversed. Putting the rows back would restore invented figures that
    # double count the BROP's own lines, which is the defect this removes. The
    # values are in the git fixture and in this docstring if they are wanted.
    pass
