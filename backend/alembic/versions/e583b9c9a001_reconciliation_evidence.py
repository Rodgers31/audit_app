"""Tighten audited reconciliation evidence; retain history and private grants."""
from alembic import op
import sqlalchemy as sa

revision = "e583b9c9a001"
down_revision = "e572b8c9a001"
branch_labels = None
depends_on = None

# Frozen whitespace set, equal to Python 3.12/3.13 str.isspace(). Do not import
# runtime code into migration history. TRIM(X,Y) also preserves SQLite DDL.
_WHITESPACE = "\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
_CHECK = (
    "(reconciled_by IS NULL) = (reconciliation IS NULL) AND "
    "(reconciled_by IS NULL OR (released_at IS NOT NULL AND "
    "length(reconciled_by) <= 64 AND length(reconciliation) <= 4000 AND "
    f"length(trim(reconciled_by, '{_WHITESPACE}')) >= 1 AND "
    f"length(trim(reconciliation, '{_WHITESPACE}')) >= 1))"
)


def upgrade():
    # Existing invalid releases must be investigated, never repaired or deleted.
    # Replacing the validated CHECK scans retained history atomically. RLS,
    # grants, other CHECKs, receipts and the active-domain index stay untouched.
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("seeding_domain_claims") as batch:
            batch.drop_constraint("ck_seeding_claim_reconciliation", type_="check")
            batch.create_check_constraint("ck_seeding_claim_reconciliation", _CHECK)
    else:
        op.drop_constraint("ck_seeding_claim_reconciliation", "seeding_domain_claims", type_="check")
        op.create_check_constraint("ck_seeding_claim_reconciliation", "seeding_domain_claims", sa.text(_CHECK))


def downgrade():
    raise RuntimeError("Reconciliation evidence protection cannot be weakened; retain schema and history")
