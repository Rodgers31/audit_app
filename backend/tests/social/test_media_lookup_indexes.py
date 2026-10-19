"""Reverse lookup contract also applies to SQLite-created media fixtures."""
from sqlalchemy import inspect

from test_media_support import media_db


LOOKUPS = {
    'social_revision_assets': ['asset_id', 'revision_id'],
    'social_media_assets': ['parent_asset_id'],
}


def assert_lookup_indexes(connection):
    for table, columns in LOOKUPS.items():
        indexes = inspect(connection).get_indexes(table)
        assert any(i['column_names'][:len(columns)] == columns and not i['unique'] for i in indexes), (table, indexes)


def test_metadata_reverse_media_lookups_have_leading_indexes(media_db):
    assert_lookup_indexes(media_db.bind)
