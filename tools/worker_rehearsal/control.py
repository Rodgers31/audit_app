"""Privileged control of the exclusively owned internal rehearsal database.

Never accepts a DSN/host: the host, login and database namespace are fixed here.
Fixture seeding uses existing native domain helpers. The resident worker gets
only its actual restricted login and uses real HTTP/TLS and botocore clients.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

PREFIX = 'b15_worker_'


def owned_database(database):
    if type(database) is not str or not re.fullmatch(PREFIX + '[a-z_]{1,24}', database):
        raise ValueError('Owned database name required')


def engine(database, worker=False):
    owned_database(database)
    user = 'b15_worker' if worker else 'postgres'
    return create_engine(f'postgresql+psycopg2://{user}@b15-worker-db:5432/{database}',
                         pool_size=1, max_overflow=0)


def initialize(database):
    owned_database(database)
    from alembic.config import Config
    from alembic import command
    from social.worker.role_contract import install_worker_role, verify_worker_role
    admin = create_engine('postgresql+psycopg2://postgres@b15-worker-db:5432/postgres',
                          isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(text('CREATE DATABASE ' + database))
    admin.dispose()
    os.environ['DATABASE_URL'] = f'postgresql+psycopg2://postgres@b15-worker-db:5432/{database}'
    command.upgrade(Config('/app/alembic.ini'), 'head')
    owner = engine(database)
    with owner.begin() as conn:
        conn.execute(text('CREATE SCHEMA stats'))
        conn.execute(text('REVOKE ALL ON SCHEMA stats FROM PUBLIC'))
        conn.execute(text('CREATE EXTENSION pg_stat_statements WITH SCHEMA stats'))
        conn.execute(text('REVOKE ALL ON ALL TABLES IN SCHEMA stats FROM PUBLIC'))
        conn.execute(text('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA stats FROM PUBLIC'))
    from social.models import SocialControls
    with Session(owner) as db:
        db.add(SocialControls(id=1, publishing_enabled=False))
        db.commit()
    install_worker_role(owner, 'b15_worker', 'public')
    actual = engine(database, worker=True)
    verify_worker_role(actual, 'b15_worker', 'public')
    actual.dispose()
    owner.dispose()
    return dict(initialized=True, migration='a545b14a0001')


def seed(database, image=False):
    owned_database(database)
    import pytest
    from social.connections.config import load_config
    from test_native_worker_postgres import prepare, registration
    from test_native_meta_adapters import Graph
    from test_media_support import FakeStorage
    from test_domain_support import call, draft_body
    from social.contracts import ApproveCommand, PublishCommand
    from social.models import SocialAccount
    owner = engine(database)
    patch = pytest.MonkeyPatch()
    try:
        if image:
            from dataclasses import replace
            from PIL import Image
            from endpoints import image_object
            original_new = Image.new
            patch.setattr(Image, 'new', lambda mode, size, *args, **kwargs:
                          image_object() if size == (320, 320) else original_new(mode, size, *args, **kwargs))
            original_head = FakeStorage.head
            def head(storage, key):
                snapshot = original_head(storage, key)
                return replace(snapshot, etag='"' + snapshot.etag + '"')
            patch.setattr(FakeStorage, 'head', head)
        with Session(owner) as db:
            existing = db.query(SocialAccount).first() is not None
        if existing:
            if image:
                raise ValueError('Seed the image first; later text uses the same owned Page')
            reg = registration(owner, load_config(os.environ), FakeStorage(), Graph())
            with Session(owner, expire_on_commit=False) as db:
                account = db.query(SocialAccount).filter_by(platform='facebook').one()
                body = draft_body((account,))
                _, created = call(db, body, lambda s: s.create(body), adapters=reg.adapters)
                approve = ApproveCommand(expected_version=created['version'], revision_id=created['revision_id'])
                _, approved = call(db, approve, lambda s: s.approve(UUID(created['id']), approve), adapters=reg.adapters)
                publish = PublishCommand(expected_version=approved['version'], revision_id=approved['revision_id'])
                _, accepted = call(db, publish, lambda s: s.publish(UUID(created['id']), publish), adapters=reg.adapters)
                target = UUID(accepted['targets'][0]['id'])
            asyncio.run(reg.close())
        else:
            _, target = prepare(owner, load_config(os.environ), Graph(), patch, image=image)
        result = dict(target_id=str(target), image=image)
        if image:
            with owner.connect() as conn:
                paths = conn.execute(text("""
                    SELECT '/' || a.bucket || '/' || a.storage_key
                    FROM social_post_targets t
                    JOIN social_publications p ON p.id=t.publication_id
                    JOIN social_revision_assets r ON r.revision_id=p.revision_id
                    JOIN social_media_assets a ON a.id=r.asset_id
                    WHERE t.id=:target AND a.state='ready'
                """), {'target': target}).scalars().all()
                external_id = conn.execute(text("""SELECT a.external_account_id
                    FROM social_post_targets t JOIN social_accounts a ON a.id=t.account_id
                    WHERE t.id=:target"""), {'target': target}).scalar_one()
            if len(paths) != 1:
                raise RuntimeError('Exactly one target-bound ready image required')
            version = load_config(os.environ).graph_version
            result['media_paths'] = list(paths)
            result['provider_paths'] = [f'/{version}/{external_id}/{kind}' for kind in ('feed', 'photos')]
        return result
    finally:
        patch.undo()
        owner.dispose()


def census(database):
    owned_database(database)
    owner = engine(database)
    try:
        with owner.connect() as conn:
            value = {}
            for table in ('social_worker_runtime_ownership', 'social_worker_runtime_history',
                          'social_worker_heartbeats', 'social_post_targets', 'social_publish_attempts'):
                # Each namespace is a fresh owned case, with a small fixed workload.
                value[table] = [dict(row) for row in conn.execute(text('SELECT * FROM ' + table)).mappings()]
            value['statements'] = [dict(row) for row in conn.execute(text('''
                SELECT query,sum(calls)::bigint AS calls,sum(rows)::bigint AS rows,
                       sum(total_exec_time) AS total_exec_time FROM stats.pg_stat_statements
                WHERE userid=(SELECT oid FROM pg_roles WHERE rolname='b15_worker')
                  AND dbid=(SELECT oid FROM pg_database WHERE datname=current_database())
                GROUP BY query ORDER BY query''')).mappings()]
            value['connections'] = conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND usename='b15_worker'")).scalar_one()
        return value
    finally:
        owner.dispose()


def release(database, receipt_path):
    owned_database(database)
    from social.worker.ownership import RuntimeAuthority, release_authority, AuthorityLost
    owner = engine(database)
    restricted = engine(database, worker=True)
    try:
        receipt = json.loads(Path(receipt_path).read_text())
        proof = receipt['release_proof']
        authority = RuntimeAuthority(UUID(proof['owner_id']), proof['generation'])
        # A malformed proof cannot release; the restricted login cannot release.
        for connection, candidate in ((owner, dict(proof, process_joined=False)), (restricted, proof)):
            try:
                release_authority(connection, authority, candidate)
            except Exception:
                with owner.connect() as conn:
                    if conn.execute(text('SELECT count(*) FROM social_worker_runtime_ownership')).scalar_one() != 1:
                        raise RuntimeError('Refused release lost ownership')
            else:
                raise RuntimeError('Unsafe release was accepted')
        # Fail after the release-history INSERT, in the same actual transaction.
        # Both history and ownership must roll back together.
        with owner.begin() as conn:
            conn.execute(text("CREATE FUNCTION b15_release_abort() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'b15 owned rollback control'; END $$"))
            conn.execute(text('CREATE TRIGGER b15_release_abort BEFORE DELETE ON social_worker_runtime_ownership FOR EACH ROW EXECUTE FUNCTION b15_release_abort()'))
        try:
            try:
                release_authority(owner, authority, proof)
            except Exception as error:
                if getattr(getattr(error, 'orig', None), 'pgcode', None) != 'P0001' or 'b15 owned rollback control' not in str(error.orig):
                    raise RuntimeError('Expected owned release rollback trigger did not fire') from None
                with owner.connect() as conn:
                    if conn.execute(text('SELECT count(*) FROM social_worker_runtime_ownership')).scalar_one() != 1:
                        raise RuntimeError('Rollback lost owner')
                    if conn.execute(text("SELECT count(*) FROM social_worker_runtime_history WHERE event='released'")).scalar_one() != 0:
                        raise RuntimeError('Rollback left release history')
            else:
                raise RuntimeError('Release persistence control did not execute')
        finally:
            with owner.begin() as conn:
                conn.execute(text('DROP TRIGGER b15_release_abort ON social_worker_runtime_ownership'))
                conn.execute(text('DROP FUNCTION b15_release_abort()'))
        release_authority(owner, authority, proof)
        with owner.connect() as conn:
            if conn.execute(text('SELECT count(*) FROM social_worker_runtime_ownership')).scalar_one() != 0:
                raise RuntimeError('Privileged release failed')
            if conn.execute(text("SELECT count(*) FROM social_worker_runtime_history WHERE event='released'")).scalar_one() != 1:
                raise RuntimeError('Release history absent')
        try:
            release_authority(owner, authority, proof)
        except AuthorityLost:
            pass  # Exact stale owner replay is expected to refuse.
        else:
            raise RuntimeError('Stale release accepted')
        return dict(released=True, invalid_refused=True, worker_refused=True, stale_refused=True,
                    transaction_rollback_preserved=True)
    finally:
        restricted.dispose()
        owner.dispose()


def contender(database):
    owned_database(database)
    from social.worker.ownership import acquire_authority, AuthorityLost
    owner = engine(database)
    try:
        with owner.connect() as conn:
            held = conn.execute(text('SELECT owner_id,generation FROM social_worker_runtime_ownership')).one()
            history = conn.execute(text('SELECT count(*) FROM social_worker_runtime_history')).scalar_one()
        try:
            acquire_authority(owner, uuid4(), 'owned-retained-contender')
        except AuthorityLost as error:
            if str(error) != 'GLOBAL_WORKER_OWNED':
                raise
        else:
            raise RuntimeError('Retained owner admitted contender')
        with owner.connect() as conn:
            if conn.execute(text('SELECT owner_id,generation FROM social_worker_runtime_ownership')).one() != held:
                raise RuntimeError('Contender changed owner')
            if conn.execute(text('SELECT count(*) FROM social_worker_runtime_history')).scalar_one() != history:
                raise RuntimeError('Contender changed history')
        return dict(contender_refused=True, owner_id=str(held.owner_id), generation=held.generation)
    finally:
        owner.dispose()


if __name__ == '__main__':
    mode, database, *extra = sys.argv[1:]
    if not re.fullmatch(PREFIX + '[a-z_]{1,24}', database):
        raise ValueError('Owned namespace required')
    functions = {'init': initialize, 'seed': seed, 'census': census, 'release': release, 'contender': contender}
    if mode == 'seed':
        result = seed(database, image=extra == ['image'])
    else:
        result = functions[mode](database, *extra)
    result['optimization'] = sys.flags.optimize
    print('CONTROL_JSON:' + json.dumps(result, default=str, allow_nan=False), flush=True)
