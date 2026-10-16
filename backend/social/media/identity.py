"""Exact allocated object identities; malformed history requires inspection."""
from uuid import UUID

from sqlalchemy import String, cast, func

from ..models import SocialMediaAsset
from .models import SocialMediaUpload


def object_identity_matches(asset, upload):
    return (
        type(asset.id) is UUID and type(upload.actor_id) is UUID
        and asset.id == upload.asset_id
        and upload.quarantine_key == f'quarantine/{upload.actor_id}/{asset.id}/source'
        and asset.storage_key == f'ready/{asset.id}/original'
    )


def _uuid_text(column, dialect):
    identity = cast(column, String)
    if dialect == 'sqlite':
        # SQLite's UUID bind representation is hex; object keys use UUID text.
        return (func.substr(identity, 1, 8) + '-' + func.substr(identity, 9, 4)
                + '-' + func.substr(identity, 13, 4) + '-'
                + func.substr(identity, 17, 4) + '-' + func.substr(identity, 21, 12))
    return identity


def object_identity_conditions(dialect):
    """Filter before LIMIT, then recheck locked ORM rows before object I/O."""
    asset = _uuid_text(SocialMediaAsset.id, dialect)
    actor = _uuid_text(SocialMediaUpload.actor_id, dialect)
    return [
        SocialMediaUpload.quarantine_key == 'quarantine/' + actor + '/' + asset + '/source',
        SocialMediaAsset.storage_key == 'ready/' + asset + '/original',
    ]
