"""stage1 3d: restore the three users columns production never got

Found 2026-08-30 while rehearsing ``alembic stamp --purge`` on a pg_dump clone
of production. The rehearsal is what surfaced it — the stamp ASSERTS that
production matches the ``21d0394c1d6b`` baseline, it does not VERIFY it, so any
table where production had already drifted stays drifted afterwards.

``public.users`` has 6 columns; ``models.User`` declares 9::

    public.users (6): created_at, disabled, email, id, password_hash, roles
    models.User  (9): + display_name, email_verified, updated_at

This is a LIVE production defect, not a cosmetic one. SQLAlchemy selects every
mapped column, so ``db.query(User).filter(User.email == email).first()`` in
``supabase_auth.get_current_user`` (supabase_auth.py:273) raises::

    psycopg2.errors.UndefinedColumn: column users.display_name does not exist

i.e. every Supabase-authenticated request 500s. It has gone unnoticed because
``public.users`` holds 0 rows — Supabase's own ``auth.users`` (a separate table,
35 columns, different schema) handles sign-in, and this mirror table is only
written on a user's first authenticated API call, which therefore always fails.
``supabase_auth.py:279-281`` writes ``display_name`` and ``email_verified``
directly, so the insert could never have succeeded either.

SCOPE — deliberately three columns and nothing else.
``alembic revision --autogenerate`` against the migrated clone proposed **274**
operations: 71 ``drop_index`` + 71 ``create_index`` (renaming hand-tuned indexes
such as ``idx_alerts_unread`` and ``ix_audits_entity_period`` to alembic's
convention), 76 ``alter_column``, 21 ``drop_constraint``. Those are the
accumulated difference between a schema grown by hand over two years and one
generated from ``models.py`` — most are cosmetic, several would drop deliberate
performance indexes, and none of them is this bug. Reconciling that surface is
its own piece of work with its own review; see issue #137.
"""

import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger("alembic.stage1")

revision = "d1a7c9e40b12"
down_revision = "cdfb80379a29"
branch_labels = None
depends_on = None


# Column name -> the type models.User declares for it.
_COLUMNS = {
    "display_name": sa.Column("display_name", sa.String(length=120), nullable=True),
    "email_verified": sa.Column("email_verified", sa.Boolean(), nullable=True),
    "updated_at": sa.Column("updated_at", sa.DateTime(), nullable=True),
}


def _existing() -> set:
    """Columns ``public.users`` already has.

    Checked rather than assumed: a fresh database built from the baseline
    already HAS all three (the baseline was generated from ``models.py``),
    while production has none of them. The same migration has to be correct
    from both starting points, so it adds only what is missing instead of
    failing with DuplicateColumn on a clean install.
    """
    bind = op.get_bind()
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "select column_name from information_schema.columns "
                "where table_schema = 'public' and table_name = 'users'"
            )
        )
    }


def upgrade() -> None:
    existing = _existing()
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("users", column)

    # email_verified is declared with default=False on the model, which is a
    # Python-side default — it does not populate rows written by anything else
    # (or rows that predate the column). Backfill so the column is never NULL
    # for an existing user, and NULL cannot be mistaken for "unverified".
    if "email_verified" not in existing:
        op.execute("update users set email_verified = false where email_verified is null")


def downgrade() -> None:
    """Deliberately a no-op. Reported by review on PR #136.

    On a CLEAN replay the baseline ``21d0394c1d6b`` creates all three columns
    (``21d0394c1d6b:160,163``), so this migration's upgrade is a no-op and it
    owns nothing to drop. On PRODUCTION the baseline never ran and the upgrade
    did add them. A downgrade cannot tell the two apart — the runs are separate
    processes and nothing records which side created the column.

    So this takes the direction ``b3d8ab47bf3b`` already settled for
    ``confidence_score``: never drop. An extra column is harmless; a missing
    one is a runtime error (``column users.display_name does not exist`` is
    the bug this migration exists to fix), and a downgrade's job is to leave a
    WORKING ``cdfb80379a29`` schema on both paths.

    This is the second time this exact defect shipped — once as
    ``confidence_score``, once here, in the migration written to fix it. The
    invariant is now pinned by tests/test_review_findings_pr136.py rather than
    by remembering.
    """
    logger.info(
        "downgrade: leaving users.display_name/email_verified/updated_at in "
        "place — on a clean replay they are baseline-owned, and this migration "
        "cannot tell that case from the production one it was written for"
    )
