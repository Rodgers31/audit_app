"""Separate owned PostgreSQL report lane; never the coordinator's port/DB."""
from dataclasses import replace
import os
import secrets
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.operator import prepare_reconciliation
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import Base
from test_media_support import ACTOR, ENDPOINT, FakeStorage, intent, png


@pytest.fixture
def operator_pg():
    dsn = os.environ.get('SOCIAL_MEDIA_OPERATOR_TEST_DATABASE_URL')
    if not dsn: pytest.skip('separately owned operator PostgreSQL lane is not assigned')
    target = urlsplit(dsn)
    if (target.scheme not in {'postgresql+psycopg', 'postgresql+psycopg2'} or target.hostname != '127.0.0.1' or target.port != 62249
            or target.username != 'media490' or target.password or target.path != '/media_operator_test'
            or target.query or target.fragment):
        raise ValueError('Refused an unassigned media operator test database')
    schema = 'media490_' + secrets.token_hex(8)
    engine = create_engine(dsn, pool_size=2, max_overflow=1, hide_parameters=True)
    with engine.begin() as conn: conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    @event.listens_for(engine, 'connect')
    def scope(conn, record):
        with conn.cursor() as cursor: cursor.execute(f'SET search_path TO "{schema}"')
        conn.commit()
    engine.dispose()
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name.startswith('social_')])
    config = MediaConfig(enabled=True, endpoint=ENDPOINT, bucket='media-test', access_key='fake', secret_key='fake')
    runtime = MediaRuntime(config, FakeStorage(), LocalInspector(config))
    try:
        with Session(engine, expire_on_commit=False) as db:
            yield MediaService(db, runtime)
    finally:
        with engine.begin() as conn: conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        engine.dispose()


def test_pg_report_executes_read_only_and_compares_exact_actor_ledger(operator_pg):
    svc = operator_pg
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    statements = []
    def trace(conn, cursor, statement, *args): statements.append(statement)
    event.listen(svc.db.bind, 'before_cursor_execute', trace)
    try: report = prepare_reconciliation(svc)
    finally: event.remove(svc.db.bind, 'before_cursor_execute', trace)
    assert statements[0] == 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'
    assert len([statement for statement in statements if statement.startswith('SELECT')]) == 3
    assert report.uploads[0].asset_id == grant.asset.id
    assert report.reason_codes == () and report.actor_ledger_discrepancies == 0
    assert report.ledger_reserved_bytes == report.upload_reserved_bytes == 2 * len(png())
    with svc.db.begin(): svc.db.get(SocialMediaBudget, 'actor:' + str(ACTOR)).pending_count += 1
    assert prepare_reconciliation(svc).actor_ledger_discrepancies == 1


def test_pg_repeatable_report_does_not_mix_aggregate_and_newer_page(operator_pg):
    svc = operator_pg
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    changed = []
    def race(conn, cursor, statement, *args):
        if changed or not statement.startswith('SELECT coalesce(sum(social_media_uploads.reserved_bytes)'): return
        changed.append(True)
        with Session(svc.db.bind) as other, other.begin():
            other.get(SocialMediaUpload, grant.asset.id).grant_epoch += 1
            other.get(SocialMediaUpload, grant.asset.id).reserved_bytes += 1
            other.get(SocialMediaBudget, 'global').bytes_used += 1
            other.get(SocialMediaBudget, 'actor:' + str(ACTOR)).bytes_used += 1
    event.listen(svc.db.bind, 'after_cursor_execute', race)
    try: first = prepare_reconciliation(svc)
    finally: event.remove(svc.db.bind, 'after_cursor_execute', race)
    assert changed == [True]
    assert first.uploads[0].grant_epoch == 1 and first.uploads[0].reserved_bytes == first.upload_reserved_bytes == first.ledger_reserved_bytes
    second = prepare_reconciliation(svc)
    assert second.uploads[0].grant_epoch == 2
    assert second.uploads[0].reserved_bytes == second.upload_reserved_bytes == first.upload_reserved_bytes + 1
