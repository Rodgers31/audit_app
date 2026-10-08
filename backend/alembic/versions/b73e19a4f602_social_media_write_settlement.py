"""Durable upload grants and once-only pending accounting; no runtime enablement."""
from alembic import op
import sqlalchemy as sa

revision = 'b73e19a4f602'
down_revision = 'a42b86e1d310'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('social_media_uploads', sa.Column('grant_renewal_deadline', sa.DateTime(timezone=True)))
    op.add_column('social_media_uploads', sa.Column('grant_epoch', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('social_media_uploads', sa.Column('grant_expires_at', sa.DateTime(timezone=True)))
    op.add_column('social_media_uploads', sa.Column('grant_settled_epoch', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('social_media_uploads', sa.Column('write_quiescence_receipt_hash', sa.String(64)))
    op.add_column('social_media_uploads', sa.Column('pending_released', sa.Integer(), nullable=False, server_default='0'))
    # Old signing was not tracked. Even rows whose old cleanup released quota
    # carry an unknown historical browser grant; do not fabricate settlement.
    # Legacy pending decrements occurred exactly when version became >1 or the
    # reservation was released. An archived version1 may have failed DELETE.
    op.execute(sa.text("""
        UPDATE social_media_uploads
        SET grant_epoch=1, grant_settled_epoch=0, grant_expires_at=NULL,
            grant_renewal_deadline=LEAST(created_at + interval '300 seconds', expires_at, clock_timestamp()),
            pending_released=CASE WHEN version>1 OR reservation_released=1 THEN 1 ELSE 0 END
    """))
    op.alter_column('social_media_uploads', 'grant_renewal_deadline', nullable=False)
    op.create_check_constraint('ck_social_media_grant_bounds', 'social_media_uploads',
        'grant_epoch >= 0 AND grant_settled_epoch >= 0 AND grant_settled_epoch <= grant_epoch AND pending_released IN (0,1)')


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text('LOCK TABLE social_media_uploads IN ACCESS EXCLUSIVE MODE'))
    if bind.execute(sa.text('SELECT EXISTS (SELECT 1 FROM social_media_uploads LIMIT 1)')).scalar():
        raise RuntimeError('Social media grant history exists; reconcile and export before removing settlement schema')
    op.drop_constraint('ck_social_media_grant_bounds', 'social_media_uploads', type_='check')
    for name in ('pending_released', 'write_quiescence_receipt_hash', 'grant_settled_epoch',
                 'grant_expires_at', 'grant_epoch', 'grant_renewal_deadline'):
        op.drop_column('social_media_uploads', name)
