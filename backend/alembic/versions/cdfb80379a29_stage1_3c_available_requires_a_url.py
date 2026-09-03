"""stage1 3c: AVAILABLE requires a url

Revision ID: cdfb80379a29
Revises: 9f033e9c86d3
Create Date: 2026-08-29

``status='AVAILABLE'`` with ``url IS NULL`` is availability nobody ever
checked — the audit found 48 such documents behind published figures
(113 across the whole table on the production clone, 2026-08-29).

DECISION: fix the rows first, then add the constraint VALID — not
``NOT VALID`` with a deferred validation. Reasons:

* Nothing in the API reads ``status`` (grep-verified: zero read
  consumers outside the seeding pipeline), so re-statusing the rows
  changes no served output.
* A ``NOT VALID`` constraint would let the 113 false AVAILABLE claims
  live on indefinitely; the entire point of the column contract is that
  AVAILABLE means "bytes landed and were hashed".
* The rows lose nothing: the prior status is recorded in
  ``metadata.status_before_3c`` and the Layer-2 fetcher promotes any of
  them back to AVAILABLE the moment a real fetch lands.

The violating rows become FAILED ("no URL was ever recorded; nothing was
fetched"), which is what is true of them.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cdfb80379a29'
down_revision = '9f033e9c86d3'
branch_labels = None
depends_on = None

CONSTRAINT = "ck_source_documents_available_has_url"


def upgrade():
    bind = op.get_bind()
    fixed = bind.execute(
        sa.text(
            """
            UPDATE source_documents
            SET status = 'FAILED',
                metadata = coalesce(metadata, '{}'::jsonb)
                           || jsonb_build_object('status_before_3c', status::text)
            WHERE status = 'AVAILABLE'
              AND (url IS NULL OR length(trim(url)) = 0)
            """
        )
    ).rowcount
    print(f"3c: {fixed} AVAILABLE-without-url document(s) re-statused to FAILED")

    op.create_check_constraint(
        CONSTRAINT,
        "source_documents",
        "status != 'AVAILABLE' OR (url IS NOT NULL AND length(trim(url)) > 0)",
    )


def downgrade():
    op.drop_constraint(CONSTRAINT, "source_documents", type_="check")
    op.get_bind().execute(
        sa.text(
            """
            UPDATE source_documents
            SET status = 'AVAILABLE',
                metadata = metadata - 'status_before_3c'
            WHERE metadata ->> 'status_before_3c' = 'AVAILABLE'
            """
        )
    )
