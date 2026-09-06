"""clear the modelled county metrics from entity.meta

Revision ID: ce6ed007f696
Revises: a7e2b91c4f38
Create Date: 2026-09-05

``enhanced_county_data.json`` wrote thirteen modelled figures into every
county's ``entity.meta["metrics"]`` and a second copy of seven of them under
``entity.meta["financial_metrics"]``. Production still holds them: Baringo's
``budget_2025`` is its census population times KSh 4,500, its
``debt_outstanding`` is exactly 15% of that, its ``pending_bills`` exactly 8%,
and its ``financial_health_score`` is the 75.0 that 40 counties share.

Every one of those figures now has a publisher behind it — Controller of
Budget, Treasury BROP, KNBS census, Auditor-General — or is deliberately
withheld for having none, and none of them reaches an API response any more.
This deletes them, for two reasons:

1. Stored-but-unserved is one endpoint away from served. The values are
   indistinguishable from measurements once they are in the database, and the
   next reader of ``entity.meta`` has no way to tell.
2. The bootstrap census that watches this fixture measures supersession
   against the DATABASE, deliberately, so that it cannot be talked out of a
   verdict by a declaration. While the figures sit in ``entity.meta`` it goes
   on reporting the file live — correctly — for numbers no reader can see,
   which points the staleness gate at the wrong file.

The rule is not copied here: this imports the same
``bootstrap.purge_modelled_county_metrics`` the seed's own tests exercise, so
there is one definition of "what this fixture modelled" rather than two that
can drift. ``county_code`` survives it — an identifier, not a claim about
money, and ``/search`` reads it out of the same dict.

Replaying this on a fresh database touches an empty ``entities`` table, and
the seed no longer writes what it removes, so a re-run has nothing to find.
"""
import os
import sys

from alembic import op

# revision identifiers, used by Alembic.
revision = "ce6ed007f696"
down_revision = "a7e2b91c4f38"
branch_labels = None
depends_on = None

# Make backend/ importable when alembic runs from anywhere.
_BACKEND_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def upgrade():
    from sqlalchemy.orm import Session

    from bootstrap import purge_modelled_county_metrics

    session = Session(bind=op.get_bind())
    stats = purge_modelled_county_metrics(session)
    session.flush()
    print(
        f"modelled county metrics cleared: {stats['entities_changed']} counties, "
        f"{stats['metric_fields_removed']} metric field(s), "
        f"{stats['meta_keys_removed']} meta key(s)"
    )


def downgrade():
    # Nothing to restore. The values were modelled by a fixture that is still
    # in the repository, so a downgrade that wanted them back would re-run the
    # seed rather than have this migration re-derive them from nothing — and
    # re-deriving them is exactly what the upgrade exists to stop. No served
    # output changes either way: every endpoint that used to read these keys
    # now reads a sourced table.
    pass
