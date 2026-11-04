"""Narrow Stage A row capsule; no CLI, credentials, object writes or restore port.

Caller owns authorization, the read-only snapshot, exact object capture and
custody. This is data closure for one first retained upload/manual initial draft,
not a backup certificate. Refuse broader history instead of silently omitting it.
"""
from datetime import datetime
from decimal import Decimal
from dataclasses import asdict
from functools import wraps
import json
import hashlib
import re
from pathlib import Path
import tempfile
from uuid import UUID

from sqlalchemy import and_, func, inspect, MetaData, or_, select, Table, text
from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..contracts import canonical_hash
from ..models import (SocialAuditEvent, SocialCommandReceipt, SocialMediaAsset,
    SocialPost, SocialPostRevision, SocialRevisionAsset)
from .models import (SocialMediaBudget, SocialMediaDeletion, SocialMediaUpload,
    SocialMediaWriteAttempt, SocialMediaWriteOwner)
from .retention import scope

MAX_ROWS = 64
MAX_ROWS_BYTES = 131072
MODELS = (SocialMediaAsset, SocialMediaUpload, SocialMediaBudget,
    SocialMediaWriteOwner, SocialMediaWriteAttempt, SocialMediaDeletion,
    SocialPost, SocialPostRevision, SocialRevisionAsset,
    SocialAuditEvent, SocialCommandReceipt)

# Stage A restores into an isolated SOCIAL schema, not an existing application
# database. This reviewed inventory is deliberately not inferred from a caller's
# ORM registry or prefix. Every present table must be empty; only the exact
# current migration marker may contain data. New tables/revisions need review.
TARGET_SCHEMA_REVISION = 'a756b20a0001'
EMPTY_TARGET_TABLES = frozenset({
    'social_posts', 'social_post_revisions', 'social_media_assets',
    'social_revision_assets', 'social_accounts', 'social_publications',
    'social_post_targets', 'social_publish_attempts', 'social_audit_events',
    'social_command_receipts', 'social_controls', 'social_worker_heartbeats',
    'social_credentials', 'social_oauth_flows', 'social_media_uploads',
    'social_media_budgets', 'social_media_write_owners', 'social_media_write_attempts',
    'social_media_deletions', 'social_privacy_ownership', 'social_privacy_receipts',
    'social_privacy_request_variants', 'social_privacy_plans', 'social_privacy_decisions',
    'social_privacy_executions', 'social_privacy_execution_events',
    'social_generation_controls', 'social_source_cursors', 'social_source_events',
    'social_automation_rule_versions', 'social_shadow_decisions',
    'social_policy_operating_evidence', 'social_authorized_policy_snapshots',
    'social_policy_selection', 'social_policy_decisions',
    'social_platform_oauth_flows', 'social_platform_credentials',
    'social_platform_connection_budgets', 'social_platform_budgets',
    'social_platform_event_inbox', 'social_render_jobs', 'social_metric_collections',
    'social_metric_observations', 'social_worker_runtime_ownership',
    'social_worker_runtime_history',
})
TARGET_SERIAL_SEQUENCES = {
    'social_generation_controls_id_seq': 'social_generation_controls',
    'social_policy_selection_id_seq': 'social_policy_selection',
}


class RecoveryScopeError(ValueError):
    def __init__(self):
        super().__init__('MEDIA_RECOVERY_SCOPE_UNPROVEN')


def _require(condition):
    if not condition:
        raise RecoveryScopeError()


def _scope_input(function):
    """Normalize malformed bounded input, without hiding DB or IO failures.

    Restore's savepoint and custody readers' finally blocks unwind before this
    outer boundary translates an ordinary parser/shape error. Interrupts and
    operational failures retain their separate meanings.
    """
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
            raise RecoveryScopeError() from None
    return guarded


@_scope_input
def _decode_json(raw):
    """One strict decoder for rows and historical embedded JSON alike."""
    _require(type(raw) in (str, bytes))
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(RecoveryScopeError()))


def _json_default(value):
    if isinstance(value, (UUID, datetime, Decimal)):
        return str(value)
    raise RecoveryScopeError()


@_scope_input
def encode_rows(rows):
    """Bound all DB/history bytes; payloads and outer custody manifest are extra."""
    _require(type(rows) is dict and set(rows) == {m.__tablename__ for m in MODELS})
    _require(all(type(v) is list for v in rows.values()))
    count = sum(len(v) for v in rows.values())
    _require(1 <= count <= MAX_ROWS)
    data = json.dumps(rows, default=_json_default, sort_keys=True,
        separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    _require(len(data) <= MAX_ROWS_BYTES)
    return data


@_scope_input
def verify_stage_a_payloads(rows, payloads):
    """Refuse a missing/corrupt copy; ledger/fence metadata never substitutes.

    Feed bytes read back from custody, independently of the capture's memory.
    This verifies the bounded payload identities only, not custody or history.
    """
    encode_rows(rows)
    assets, uploads = rows['social_media_assets'], rows['social_media_uploads']
    _require(len(assets) == 1 and len(uploads) == 1)
    asset, upload = assets[0], uploads[0]
    _require(type(asset) is dict and type(upload) is dict)
    size, digest = asset.get('byte_size'), asset.get('sha256')
    _require(type(size) is int and 1 <= size <= 262144
        and type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None)
    keys = [asset.get('storage_key'), upload.get('quarantine_key')]
    _require(all(type(k) is str and k for k in keys) and len(set(keys)) == 2)
    _require(type(payloads) is dict and set(payloads) == set(keys))
    _require(all(type(data) is bytes and len(data) == size
        and hashlib.sha256(data).hexdigest() == digest for data in payloads.values()))


@_scope_input
def capture_stage_a_payloads(rows, storage):
    """Read two conditionally identified copies; caller separately qualifies writers.

    Does not establish a global object snapshot against privileged/off-system
    writers. Use while the qualified conditional-only writer envelope holds.
    The permanent pair remains present and fully charged; no writes are issued.
    """
    encode_rows(rows)
    _require(len(rows['social_media_assets']) == 1 and len(rows['social_media_uploads']) == 1)
    asset, upload = rows['social_media_assets'][0], rows['social_media_uploads'][0]
    # Validate ALL metadata used below before the first storage-port call. A
    # typed refusal after reading the quarantine copy is already too late.
    _require(type(asset) is dict and type(upload) is dict)
    size, digest = asset.get('byte_size'), asset.get('sha256')
    _require(type(size) is int and 1 <= size <= 262144
        and type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None
        and type(asset.get('mime_type')) is str and asset['mime_type'] == 'image/jpeg')
    codec = asset.get('codec_metadata')
    _require(type(codec) is dict and type(codec.get('storage_etag')) is str
        and 1 <= len(codec['storage_etag']) <= 1024
        and (codec.get('storage_version') is None or type(codec['storage_version']) is str
            and 1 <= len(codec['storage_version']) <= 1024))
    keys = (upload.get('quarantine_key'), asset.get('storage_key'))
    _require(all(type(key) is str and 1 <= len(key) <= 1024 for key in keys)
        and len(set(keys)) == 2)
    _require(type(asset.get('storage_provider')) is str and asset['storage_provider']
        and type(asset.get('bucket')) is str and asset['bucket'])
    fence = upload.get('retained_write_fence')
    _require(type(fence) is str and 1 <= len(fence) <= 4096)
    marker = _decode_json(fence)
    _require(type(marker) is dict and set(marker) == {
        'version', 'scope_hash', 'quarantine_etag', 'original_etag'})
    _require(type(marker['version']) is int and marker['version'] == 1
        and type(marker['scope_hash']) is str and re.fullmatch('[0-9a-f]{64}', marker['scope_hash']) is not None
        and type(marker['quarantine_etag']) is str and 1 <= len(marker['quarantine_etag']) <= 1024
        and marker['original_etag'] == codec['storage_etag'])
    _require(asset['storage_provider'] == storage.provider and asset['bucket'] == storage.bucket)
    quarantine_etag = marker['quarantine_etag']
    snapshots, payloads = {}, {}
    with tempfile.TemporaryDirectory(prefix='media-custody-') as directory:
        for index, key in enumerate(keys):
            observed = storage.head(key)
            _require(observed.size == asset['byte_size'] and observed.mime_type == asset['mime_type'])
            if index == 0:
                _require(observed.etag == quarantine_etag)
            if index == 1:
                _require(observed.etag == asset['codec_metadata']['storage_etag']
                    and observed.version == asset['codec_metadata'].get('storage_version')
                    and observed.sha256 == asset['sha256'])
            path = Path(directory) / str(index)
            storage.download(key, observed, path, asset['byte_size'])
            snapshots[key], payloads[key] = observed, path.read_bytes()
        verify_stage_a_payloads(rows, payloads)
        _require(all(storage.head(key) == snapshots[key] for key in keys))
    return payloads, {key: asdict(value) for key, value in snapshots.items()}


def _require_pg_auxiliary_state(connection, schema):
    """Observe only the selected schema and this connection's temporary state.

    The two SERIAL counters are legitimate migration infrastructure only while
    pristine and attached to their reviewed id columns. Never reset a counter
    or read another session's temporary namespace to manufacture emptiness.
    """
    _require(not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_class '
        'WHERE relnamespace=pg_my_temp_schema())')))
    _require(not connection.scalar(text('''SELECT EXISTS(SELECT 1 FROM pg_inherits i
        JOIN pg_class child ON child.oid=i.inhrelid
        JOIN pg_namespace child_ns ON child_ns.oid=child.relnamespace
        JOIN pg_class parent ON parent.oid=i.inhparent
        JOIN pg_namespace parent_ns ON parent_ns.oid=parent.relnamespace
        WHERE child_ns.nspname=:schema OR parent_ns.nspname=:schema)'''), {'schema': schema}))
    _require(not connection.scalar(text('''SELECT EXISTS(SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND c.relkind='v')'''), {'schema': schema}))
    sequences = list(connection.execute(text('''SELECT c.oid,c.relname,
        c.relowner=current_user::regrole,has_sequence_privilege(c.oid,'SELECT'),
        s.seqstart,s.seqincrement,s.seqmin,s.seqmax,s.seqcache,s.seqcycle
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_sequence s ON s.seqrelid=c.oid WHERE n.nspname=:schema
        ORDER BY c.relname LIMIT 3'''), {'schema': schema}))
    _require(len(sequences) <= len(TARGET_SERIAL_SEQUENCES))
    quote = connection.dialect.identifier_preparer.quote_identifier
    for sequence in sequences:
        oid, name = sequence[:2]
        _require(name in TARGET_SERIAL_SEQUENCES and sequence[2:4] == (True, True)
            and sequence[4:] == (1, 1, 1, 2147483647, 1, False))
        relation = quote(schema) + '.' + quote(TARGET_SERIAL_SEQUENCES[name])
        _require(connection.scalar(text("SELECT pg_get_serial_sequence(:relation,'id')::regclass::oid"),
            {'relation': relation}) == oid)
        _require(connection.exec_driver_sql('SELECT last_value,is_called FROM '
            + quote(schema) + '.' + quote(name)).one() == (1, False))


def _require_empty_target(connection):
    """Count every stored relation in the resolved, caller-owned target schema.

    No credential/history bodies are read and no rows are removed. Unknown,
    inherited, foreign, materialized or unobservable storage is outside Stage A.
    The caller still separately qualifies migrated DDL, ACLs and OS isolation.
    """
    try:
        catalog = inspect(connection)
        if connection.dialect.name == 'postgresql':
            _require(connection.scalar(text('SHOW row_security')) == 'off')
            schema = connection.scalar(text('SELECT current_schema()'))
            _require(type(schema) is str and not schema.startswith('pg_')
                and schema != 'information_schema')
            _require(connection.scalar(text('SELECT nspowner=current_user::regrole '
                'FROM pg_namespace WHERE nspname=:schema'), {'schema': schema}) is True)
            names = list(connection.execute(text('''SELECT c.relname,c.relkind,
                c.relispartition,c.relowner=current_user::regrole,
                has_table_privilege(c.oid,'SELECT') FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema
                AND c.relkind IN ('r','p','f','m') ORDER BY c.relname LIMIT 257'''), {'schema': schema}))
            _require(0 < len(names) <= 256 and all(row[1:] == ('r', False, True, True) for row in names))
            _require_pg_auxiliary_state(connection, schema)
            # Prove unqualified insert/readback names resolve into THIS schema;
            # another search_path schema or temporary shadow must not be used.
            for model in MODELS:
                _require(connection.scalar(text('''SELECT n.nspname FROM pg_class c
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE c.oid=to_regclass(:name)'''), {'name': model.__tablename__}) == schema)
            names = [row[0] for row in names]
            _require(set(names) <= EMPTY_TARGET_TABLES | {'alembic_version'})
            quote = connection.dialect.identifier_preparer.quote_identifier
            # Hold the census against concurrent writers until the caller ends
            # its transaction. Never discover emptiness then admit later rows.
            for name in names:
                connection.exec_driver_sql('LOCK TABLE ONLY ' + quote(schema) + '.'
                    + quote(name) + ' IN SHARE ROW EXCLUSIVE MODE')
            # A new inheritance edge could appear between the earlier catalog
            # read and lock acquisition. Recheck while selected relations are
            # held; an empty outside child must not escape the refusal.
            _require_pg_auxiliary_state(connection, schema)
        else:
            schema = 'main'
            _require({row[1] for row in connection.exec_driver_sql('PRAGMA database_list')}
                <= {'main', 'temp'})
            _require(connection.exec_driver_sql('SELECT count(*) FROM sqlite_temp_master').scalar_one() == 0)
            _require(not catalog.get_view_names(schema=schema))
            # Reflection hides sqlite_ tables by default. Imported sequence or
            # statistics rows are also unknown target state; never ignore them.
            names = list(connection.exec_driver_sql("SELECT name FROM main.sqlite_master "
                "WHERE type='table' ORDER BY name").scalars())
        _require(0 < len(names) <= 256 and {m.__tablename__ for m in MODELS} <= set(names))
        _require(set(names) <= EMPTY_TARGET_TABLES | {'alembic_version'})
        metadata = MetaData()
        for name in names:
            table = Table(name, metadata, schema=schema, autoload_with=connection, resolve_fks=False)
            if name == 'alembic_version':
                _require(set(table.columns.keys()) == {'version_num'})
                _require(list(connection.scalars(select(table.c.version_num))) == [TARGET_SCHEMA_REVISION])
            else:
                _require(connection.scalar(select(func.count()).select_from(table)) == 0)
    except SQLAlchemyError:
        # Permission, reflection and RLS errors mean the target was not proven
        # empty. The restore savepoint will roll back even when the caller
        # catches this typed refusal and commits its enclosing transaction.
        raise RecoveryScopeError() from None


@_scope_input
def restore_stage_a_rows(connection, raw):
    """Insert only into an empty, caller-owned isolated social schema.

    Never creates a connection or schema, truncates/replaces rows, or reads
    credentials. Caller must enforce OS network isolation and custody authority.
    Full application schemas are outside the explicit Stage A table inventory.
    A logical insert is not full PostgreSQL schema/ACL or remote-R2 recovery.
    """
    _require(connection.in_transaction() and connection.dialect.name in {'sqlite', 'postgresql'})
    if connection.dialect.name == 'sqlite' and not connection.connection.driver_connection.in_transaction:
        # A first SAVEPOINT would otherwise commit independently of the caller's
        # still-virtual SQLAlchemy transaction on SQLite's legacy driver.
        connection.exec_driver_sql('BEGIN')
    with connection.begin_nested():
        _restore_stage_a_rows(connection, raw)


def _restore_stage_a_rows(connection, raw):
    if connection.dialect.name == 'postgresql':
        _require(connection.scalar(text('SHOW row_security')) == 'off')
    _require(type(raw) is bytes and 1 <= len(raw) <= MAX_ROWS_BYTES)
    rows = _decode_json(raw)
    encode_rows(rows)
    _require(len(rows['social_media_assets']) == 1 and len(rows['social_media_uploads']) == 1
        and len(rows['social_posts']) == 1)
    _require_empty_target(connection)
    if connection.dialect.name == 'sqlite':
        connection.exec_driver_sql('PRAGMA defer_foreign_keys=ON')
    else:
        connection.exec_driver_sql('SET CONSTRAINTS ALL DEFERRED')
    for model in MODELS:
        table = model.__table__
        for row in rows[table.name]:
            _require(type(row) is dict and set(row) == set(table.columns.keys()))
            values = dict(row)
            for column in table.columns:
                value = values[column.name]
                if value is not None:
                    if isinstance(column.type, Uuid):
                        _require(type(value) is str)
                        values[column.name] = UUID(value)
                    elif isinstance(column.type, DateTime):
                        _require(type(value) is str)
                        values[column.name] = datetime.fromisoformat(value)
            connection.execute(table.insert().values(**values))
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('SET CONSTRAINTS ALL IMMEDIATE')
    # The inserted records must pass the same complete semantic closure checks
    # before the caller can commit. A ready asset alone must never be usable.
    asset_row, post_row = rows['social_media_assets'][0], rows['social_posts'][0]
    with Session(bind=connection, expire_on_commit=False) as db, db.begin():
        stored = _stage_a_rows(db, UUID(asset_row['created_by']),
            UUID(asset_row['id']), UUID(post_row['id']))
        _require(encode_rows(stored) == encode_rows(rows))
    # This exact insert/readback still does not certify custody or object state.


def _require_incoming_closure(db, rows):
    """Discover actual FK dependants, including tables absent from ORM imports.

    Count rather than read unknown child bodies. Any incoming row omitted from
    this bounded slice refuses capture, including another post's self-reference.
    Non-FK intent/side ledgers still require the separately reviewed inventory.
    """
    connection = db.connection()
    catalog = inspect(connection)
    parents = set(rows)
    metadata = MetaData()
    if connection.dialect.name == 'postgresql':
        # Resolve exactly the relations used by the unqualified ORM reads, then
        # find incoming FKs across ALL schemas, including non-ORM side ledgers.
        regclasses = ','.join("to_regclass('" + name + "')" for name in sorted(parents))
        relations = list(db.execute(text('SELECT c.relname,n.nspname FROM pg_class c '
            'JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid IN (' + regclasses + ')')))
        _require(len(relations) == len(parents) and len({r[1] for r in relations}) == 1
            and not any(r[1].startswith('pg_') for r in relations))
        parent_schema = relations[0][1]
        foreign_keys = list(db.execute(text('''SELECT child.relname AS name,
            ns.nspname AS schema, parent.relname AS parent,
            ARRAY(SELECT a.attname FROM unnest(f.conkey) WITH ORDINALITY k(attnum,n)
                JOIN pg_attribute a ON a.attrelid=f.conrelid AND a.attnum=k.attnum ORDER BY k.n) AS local,
            ARRAY(SELECT a.attname FROM unnest(f.confkey) WITH ORDINALITY k(attnum,n)
                JOIN pg_attribute a ON a.attrelid=f.confrelid AND a.attnum=k.attnum ORDER BY k.n) AS remote
            FROM pg_constraint f JOIN pg_class child ON child.oid=f.conrelid
            JOIN pg_namespace ns ON ns.oid=child.relnamespace
            JOIN pg_class parent ON parent.oid=f.confrelid
            WHERE f.contype='f' AND f.confrelid IN (''' + regclasses + ')')).mappings())
    else:
        parent_schema = None
        foreign_keys = [{'name': name, 'schema': None, 'parent': f['referred_table'],
            'local': f['constrained_columns'], 'remote': f['referred_columns']}
            for name in catalog.get_table_names() for f in catalog.get_foreign_keys(name)
            if f['referred_table'] in parents]
    _require(len(foreign_keys) <= 256)
    for foreign_key in foreign_keys:
        name, schema, parent = (foreign_key[k] for k in ('name', 'schema', 'parent'))
        child = Table(name, metadata, schema=schema, autoload_with=connection, resolve_fks=False)
        local, remote = foreign_key['local'], foreign_key['remote']
        for parent_row in rows[parent]:
            values = [parent_row[c] for c in remote]
            if any(v is None for v in values):
                continue
            predicate = and_(*(child.c[c] == v for c, v in zip(local, values)))
            actual = db.scalar(select(func.count()).select_from(child).where(predicate))
            expected = sum(all(str(row[c]) == str(v) for c, v in zip(local, values))
                for row in rows.get(name, []) if schema == parent_schema)
            _require(actual == expected)


@_scope_input
def capture_stage_a_rows(db, actor_id, asset_id, post_id):
    """Read the dependency-closed *first* intake inside caller's stable snapshot.

    PostgreSQL requires an already active REPEATABLE READ READ ONLY transaction.
    No transaction or isolation mode is silently created or changed here. SQLite
    is supported for inert local rehearsal only; its schema is not PG acceptance.
    Whole-media counts guard shared budgets. Any second intake, historical
    revision, source/account dependency, owner/deletion history or publication
    exceeds this deliberately narrow protocol and must be separately scoped.
    """
    _require(all(type(v) is UUID for v in (actor_id, asset_id, post_id)))
    _require(db.in_transaction())
    dialect = db.get_bind().dialect.name
    _require(dialect in {'postgresql', 'sqlite'})
    if dialect == 'postgresql':
        _require(db.scalar(text('SHOW transaction_read_only')) == 'on')
        _require(db.scalar(text('SHOW transaction_isolation')) == 'repeatable read')
        _require(db.scalar(text('SHOW row_security')) == 'off')

    return _stage_a_rows(db, actor_id, asset_id, post_id)


def _stage_a_rows(db, actor_id, asset_id, post_id):
    asset = db.get(SocialMediaAsset, asset_id, populate_existing=True)
    upload = db.get(SocialMediaUpload, asset_id, populate_existing=True)
    post = db.get(SocialPost, post_id, populate_existing=True)
    _require(asset is not None and upload is not None and post is not None)
    _require(type(asset.codec_metadata) is dict)
    _require(db.scalar(select(func.count()).select_from(SocialMediaAsset)) == 1)
    _require(db.scalar(select(func.count()).select_from(SocialMediaUpload)) == 1)
    _require(asset.created_by == actor_id == upload.actor_id == post.created_by)
    _require(asset.parent_asset_id is None and asset.state == 'ready'
        and asset.deleted_at is None and asset.lease_token is None
        and asset.lease_expires_at is None)
    _require(asset.mime_type == 'image/jpeg' and (asset.width, asset.height) == (1080, 1080)
        and type(asset.byte_size) is int and 1 <= asset.byte_size <= 262144)
    _require(upload.write_protocol == 'conditional_create_v1'
        and upload.version == 2 and upload.grant_epoch >= 1
        and upload.grant_settled_epoch == 0 and upload.finalization_epoch == 1
        and upload.finalization_settled == 1 and upload.pending_released == 1
        and upload.reservation_released == 0 and upload.quarantine_cleaned == 0
        and upload.fenced_copies == 0 and upload.declared_size == asset.byte_size
        and upload.reserved_bytes == 2 * asset.byte_size
        and upload.write_quiescence_receipt_hash is None)
    _require(type(upload.completion_key) is UUID
        and isinstance(upload.grant_expires_at, datetime)
        and upload.declared_mime_type == asset.mime_type
        and upload.completion_hash == canonical_hash({'expected_version': 1})
        and upload.request_hash == canonical_hash({'filename': asset.original_filename,
            'declared_mime_type': upload.declared_mime_type,
            'declared_size': upload.declared_size, 'alt_text': asset.default_alt_text}))
    _require(asset.storage_key == f'ready/{asset_id}/original'
        and upload.quarantine_key == f'quarantine/{actor_id}/{asset_id}/source')
    _require(type(upload.retained_write_fence) is str and 1 <= len(upload.retained_write_fence) <= 4096)
    marker = _decode_json(upload.retained_write_fence)
    _require(type(marker) is dict and set(marker) == {
        'version', 'scope_hash', 'quarantine_etag', 'original_etag'})
    _require(type(marker['version']) is int and marker['version'] == 1
        and marker['scope_hash'] == scope(asset, upload)
        and type(marker['quarantine_etag']) is str and bool(marker['quarantine_etag'])
        and marker['original_etag'] == asset.codec_metadata.get('storage_etag'))
    _require(post.origin_type == 'manual' and post.creation_method == 'admin'
        and post.editorial_state == 'draft' and post.row_version == 1
        and post.source_event_id is None and post.duplicated_from_id is None
        and post.replaces_post_id is None and post.archived_at is None)
    revisions = list(db.scalars(select(SocialPostRevision).where(SocialPostRevision.post_id == post_id)))
    _require(len(revisions) == 1)
    revision = revisions[0]
    _require(type(revision.document) is dict
        and type(revision.document.get('master')) is dict
        and type(revision.document['master'].get('media')) is list
        and all(type(item) is dict for item in revision.document['master']['media']))
    _require(revision.id == post.current_revision_id and revision.revision_no == 1
        and revision.created_by == actor_id and revision.generator_metadata is None
        and revision.evidence_snapshot == {'references': []} and revision.document.get('targets') == []
        and revision.content_hash == canonical_hash({'document': revision.document,
            'evidence_snapshot': revision.evidence_snapshot}))
    refs = list(db.execute(select(SocialRevisionAsset.revision_id,
        SocialRevisionAsset.asset_id).where(or_(SocialRevisionAsset.asset_id == asset_id,
            SocialRevisionAsset.revision_id == revision.id))))
    _require(refs == [(revision.id, asset_id)])
    _require([m.get('asset_id') for m in revision.document['master']['media']] == [str(asset_id)])
    budgets = list(db.scalars(select(SocialMediaBudget)))
    _require(len(budgets) == 2 and {b.scope for b in budgets} == {'global', f'actor:{actor_id}'})
    _require(all(b.bytes_used == upload.reserved_bytes and b.pending_count == 0 for b in budgets))

    # Zero matching rows are explicit required observations, not missing tables.
    for model in (SocialMediaWriteOwner, SocialMediaWriteAttempt, SocialMediaDeletion):
        _require(db.scalar(select(func.count()).select_from(model)) == 0)
    # Refuse post dependencies beyond the initial manual draft, even if an
    # unrelated caller inserted them without advancing its editorial state.
    from ..models import SocialPublication
    _require(db.scalar(select(func.count()).select_from(SocialPublication).where(
        SocialPublication.post_id == post_id)) == 0)

    predicates = {
        SocialMediaAsset: SocialMediaAsset.id == asset_id,
        SocialMediaUpload: SocialMediaUpload.asset_id == asset_id,
        SocialMediaBudget: SocialMediaBudget.scope.in_(['global', f'actor:{actor_id}']),
        SocialMediaWriteOwner: SocialMediaWriteOwner.asset_id == asset_id,
        SocialMediaWriteAttempt: SocialMediaWriteAttempt.asset_id == asset_id,
        SocialMediaDeletion: SocialMediaDeletion.asset_id == asset_id,
        SocialPost: SocialPost.id == post_id,
        SocialPostRevision: SocialPostRevision.post_id == post_id,
        SocialRevisionAsset: SocialRevisionAsset.asset_id == asset_id,
        SocialAuditEvent: or_(SocialAuditEvent.post_id == post_id,
            SocialAuditEvent.details['asset_id'].as_string() == str(asset_id)),
        SocialCommandReceipt: SocialCommandReceipt.resource_id.in_([asset_id, post_id]),
    }
    rows = {}
    for model in MODELS:
        table = model.__table__
        rows[table.name] = [dict(row) for row in db.execute(select(table).where(
            predicates[model]).order_by(*table.primary_key.columns).limit(MAX_ROWS + 1)).mappings()]
    audits = rows[SocialAuditEvent.__tablename__]
    _require(len(audits) == 6 and all(a['account_id'] is None and a['target_id'] is None
        and a['post_id'] in (None, post_id)
        and a['actor_id'] == actor_id and a['actor_kind'] == 'admin' for a in audits))
    _require({'media.upload_initiated', 'media.inspection_started', 'media.inspection_ready',
        'media.retention_verification_started', 'media.retained_fence_verified',
        'post.created'} == {a['action'] for a in audits})
    receipts = rows[SocialCommandReceipt.__tablename__]
    _require(len(receipts) == 1 and receipts[0]['resource_id'] == post_id
        and receipts[0]['http_status'] == 201)
    receipt = receipts[0]
    _require(receipt['actor_key'] == str(actor_id)
        and receipt['route_key'] == 'POST /api/v1/admin/social/posts'
        and type(receipt['response']) is dict and receipt['response'].get('id') == str(post_id)
        and receipt['response'].get('revision_id') == str(revision.id)
        and type(receipt['response'].get('version')) is int and receipt['response']['version'] == 1)
    _require_incoming_closure(db, rows)
    encode_rows(rows)  # Enforce total closure cap before returning any bytes.
    return rows
