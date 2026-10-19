"""Index retained media usage and parent-dependency lookups without changing data."""
from alembic import op

revision = 'a756b20a0001'
down_revision = 'e621b17a0001'
branch_labels = None
depends_on = None


def upgrade():
    # Transactional DDL: a lock/statement failure rolls back both indexes.
    # The operator supplies bounded timeouts; no concurrent/autocommit DDL.
    op.create_index('ix_social_revision_asset_lookup', 'social_revision_assets', ['asset_id', 'revision_id'])
    op.create_index('ix_social_asset_parent', 'social_media_assets', ['parent_asset_id'])


def downgrade():
    op.drop_index('ix_social_asset_parent', table_name='social_media_assets')
    op.drop_index('ix_social_revision_asset_lookup', table_name='social_revision_assets')
