"""stage1 3b: backfill publishable from the publication gate

Revision ID: 9f033e9c86d3
Revises: 6ce655115689
Create Date: 2026-08-29

Writes the gate's verdict into ``audits.publishable`` (and a machine-
readable ``quarantine_reason`` on withheld rows) so the column carries
what the API recomputes per request.

The rule is NOT copied here: this migration imports
``services.publication_gate.backfill_publishable_audits`` — the same
function the Layer-4 loader calls after every load. One definition,
three call sites. The import coupling is deliberate and safe: replaying
this revision on a fresh database touches an empty ``audits`` table, and
replaying it later applies the rule as it stands then, which is the
column's contract (it mirrors the gate, not a snapshot of it).

Other fact tables' ``publishable`` columns stay at their FALSE default:
no gate is defined for them yet, and the API does not read the column
for them either — backfilling a rule that does not exist would be a
second copy of nothing.
"""
import os
import sys

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f033e9c86d3'
down_revision = '6ce655115689'
branch_labels = None
depends_on = None

# Make backend/ importable when alembic runs from anywhere.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def upgrade():
    from sqlalchemy.orm import Session

    from services.publication_gate import backfill_publishable_audits

    session = Session(bind=op.get_bind())
    stats = backfill_publishable_audits(session)
    session.flush()
    print(
        f"publishable backfill: {stats['published']} published, "
        f"{stats['withheld']} withheld"
    )


def downgrade():
    # Restore the column's server default state: everything withheld until
    # something proves otherwise. (The API keeps recomputing the gate per
    # request, so no served output changes.)
    op.get_bind().execute(
        sa.text(
            "UPDATE audits SET publishable = false, quarantine_reason = NULL"
        )
    )
