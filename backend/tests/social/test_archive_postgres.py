"""Owned PostgreSQL17: migrated schema, forced races and durable audit failure."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from social.contracts import ApproveCommand, VersionCommand
from social.models import SocialAuditEvent, SocialCommandReceipt, SocialControls, SocialPost, SocialPostTarget, SocialPublication
from social.service import SocialError, SocialService
from test_archive import archive, create
from test_domain_support import call, account
from test_queue_postgres import repository


def owned_url(value):
    message = 'Requires owned archive727 on loopback port 62727 with no query options'
    if not isinstance(value, str) or '?' in value:
        raise ValueError(message)
    from sqlalchemy.exc import ArgumentError
    try:
        url = make_url(value)
    except ArgumentError:
        raise ValueError(message) from None
    if (url.drivername not in {'postgresql', 'postgresql+psycopg2'} or url.host != '127.0.0.1'
            or url.port != 62727 or url.database != 'archive727' or url.username != 'archive727' or url.query):
        raise ValueError(message)
    return url.set(drivername='postgresql+psycopg2', query={'hostaddr': '127.0.0.1'})


@pytest.fixture(scope='module')
def archive_engine():
    value = os.getenv('B16_ARCHIVE_DATABASE_URL')
    if not value:
        pytest.skip('Supply the owned archive727 PostgreSQL17 fixture explicitly')
    root = create_engine(owned_url(value), hide_parameters=True)
    with root.begin() as conn:
        assert conn.scalar(text('select current_database()')) == 'archive727'
        assert conn.scalar(text('show server_version_num')).startswith('17')
        assert conn.scalar(text("select count(*) from pg_tables where schemaname='public'")) == 0, 'Owned fixture must start empty'
    engine = create_engine(owned_url(value), pool_size=6, max_overflow=0, hide_parameters=True,
        connect_args={'options': '-clock_timeout=5000 -cstatement_timeout=15000'})
    try:
        # Replay the pinned repository's complete migration chain, without env.py,
        # application boot or environment/credential discovery.
        from pathlib import Path
        scripts = ScriptDirectory(str(Path(__file__).parents[2] / 'alembic'))
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            for revision in reversed(list(scripts.walk_revisions(base='base', head='a705b15a0001'))):
                revision.module.upgrade()
        yield engine
    finally:
        engine.dispose()
        with root.begin() as conn:
            conn.execute(text('DROP SCHEMA public CASCADE'))
            conn.execute(text('CREATE SCHEMA public'))
        root.dispose()


@pytest.fixture
def pg(archive_engine):
    with archive_engine.begin() as conn:
        tables = conn.scalars(text("select tablename from pg_tables where schemaname=current_schema() and tablename like 'social_%'" )).all()
        conn.execute(text('TRUNCATE ' + ','.join('"' + t + '"' for t in tables) + ' CASCADE'))
    if hasattr(archive_engine, '_fixture_authority'):
        del archive_engine._fixture_authority
    return archive_engine


def test_fixture_refuses_unowned_targets():
    for value in (None, '', 'postgresql://archive727@remote:62727/archive727',
        'postgresql://archive727@127.0.0.1:62727/production',
        'postgresql://archive727@127.0.0.1:62727/archive727?host=remote'):
        with pytest.raises(ValueError): owned_url(value)


def seed(pg, approved=False):
    with Session(pg, expire_on_commit=False) as db:
        db.add(SocialControls(id=1, publishing_enabled=False)); db.commit()
        post = create(db, approved)
        if approved:
            body = ApproveCommand(expected_version=1, revision_id=post['revision_id'])
            post = call(db, body, lambda s: s.approve(UUID(post['id']), body), route='approve')[1]
        return post


def test_pg_same_key_concurrent_replay_and_restart(pg):
    post = seed(pg)
    key, start = uuid4(), Barrier(2)
    def run(_):
        with Session(pg, expire_on_commit=False) as db:
            start.wait(5)
            return archive(db, post, command_key=key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert results[0] == results[1]
    with Session(pg) as db:
        assert SocialService(db).detail(UUID(post['id'])) == results[0]
        assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action == 'post.archived')) == 1
        assert db.scalar(select(func.count()).select_from(SocialCommandReceipt)) == 2
        assert db.get(SocialControls, 1).publishing_enabled is False
        assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0


@pytest.mark.parametrize('first,second', [('archive','approve'), ('archive','schedule'), ('approve','archive'), ('schedule','archive')])
def test_pg_forced_archive_approval_schedule_ordering(pg, first, second):
    from social.contracts import PublishCommand
    post = seed(pg)
    # Add an owned destination without mutating the saved revision.
    with Session(pg, expire_on_commit=False) as db:
        from social.contracts import PatchPost, PostDocument
        a = account(db)
        document = PostDocument.model_validate({**post['document'], 'targets': [{'account_id':str(a.id), 'format':'text'}]})
        body = PatchPost(expected_version=1, document=document)
        post = call(db, body, lambda s: s.patch(UUID(post['id']), body), route='patch')[1]
    locked, release = Event(), Event()
    def command(action, hold=False):
        with Session(pg, expire_on_commit=False) as db:
            svc = SocialService(db, available_adapters={'facebook'})
            if action == 'archive': body = VersionCommand(expected_version=post['version'])
            else: body = PublishCommand(expected_version=post['version'], revision_id=post['revision_id'])
            def execute():
                if hold:
                    svc._locked(UUID(post['id']), body.expected_version)
                    locked.set(); assert release.wait(5)
                if action == 'archive': return svc.archive(UUID(post['id']), body)
                if action == 'schedule':
                    # Local inert queue request, no worker or network. Real publication
                    # checks execute; only this disposable fixture's control is enabled.
                    return svc.publish(UUID(post['id']), body)
                return svc.approve(UUID(post['id']), body)
            try:
                return svc.command(actor=uuid4(), route=action, key=uuid4(), body=body.model_dump(mode='json'), request_id=uuid4(), action=execute)[1]
            except SocialError as error:
                return error.code
    if first == 'schedule':
        with pg.begin() as conn: conn.execute(text('update social_controls set publishing_enabled=true'))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(command, first, True); assert locked.wait(5)
            b = pool.submit(command, second)
            release.set()
            first_result, second_result = a.result(5), b.result(5)
        assert isinstance(first_result, dict), first_result
        assert second_result == 'VERSION_CONFLICT'
        with Session(pg) as db:
            current = SocialService(db).detail(UUID(post['id']))
            assert current['editorial_state'] == ('archived' if first == 'archive' else 'approved')
    finally: release.set()


def test_pg_claim_commits_while_archive_waits_and_preserves_lease(pg):
    post = seed(pg, approved=True)
    with pg.begin() as conn:
        conn.execute(text("update social_post_targets set state='queued',next_action='publish',next_action_at=now()"))
        conn.execute(text('update social_controls set publishing_enabled=true'))
    repo = repository(pg)
    claimed, target_lock, release = Event(), Event(), Event()
    def after(conn, cursor, statement, params, context, many):
        if 'WITH due AS' in statement:
            claimed.set(); assert release.wait(5)
    def before(conn, cursor, statement, params, context, many):
        if 'social_post_targets' in statement and 'FOR UPDATE' in statement and 'WITH due AS' not in statement:
            target_lock.set()
    event.listen(pg, 'after_cursor_execute', after); event.listen(pg, 'before_cursor_execute', before)
    def do_archive():
        with Session(pg) as db:
            try: return archive(db, post)
            except SocialError as error: return error.code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(repo.claim_due); assert claimed.wait(5)
            b = pool.submit(do_archive); assert target_lock.wait(5)
            assert not b.done(); release.set()
            claim, result = a.result(5)[0], b.result(5)
        assert result == 'ARCHIVE_DELIVERY_ACTIVE'
        with Session(pg) as db:
            target = db.get(SocialPostTarget, UUID(claim.target_id))
            assert str(target.lease_token) == claim.token and target.state == 'claimed'
            assert db.get(SocialPost, UUID(post['id'])).archived_at is None
    finally:
        release.set(); event.remove(pg, 'after_cursor_execute', after); event.remove(pg, 'before_cursor_execute', before)


def test_pg_audit_database_failure_is_atomic(pg):
    post = seed(pg)
    with pg.begin() as conn:
        conn.execute(text("""CREATE FUNCTION fail_archive_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.action='post.archived' THEN RAISE EXCEPTION 'archive audit fixture failure'; END IF; RETURN NEW; END $$"""))
        conn.execute(text('CREATE TRIGGER fail_archive_audit BEFORE INSERT ON social_audit_events FOR EACH ROW EXECUTE FUNCTION fail_archive_audit()'))
    try:
        from sqlalchemy.exc import DBAPIError
        with Session(pg) as db:
            with pytest.raises(DBAPIError, match='archive audit fixture failure'): archive(db, post)
        with Session(pg) as db:
            current = db.get(SocialPost, UUID(post['id']))
            assert current.editorial_state == 'draft' and current.archived_at is None and current.row_version == 1
            assert db.scalar(select(func.count()).select_from(SocialCommandReceipt)) == 1
    finally:
        with pg.begin() as conn:
            conn.execute(text('DROP TRIGGER fail_archive_audit ON social_audit_events'))
            conn.execute(text('DROP FUNCTION fail_archive_audit()'))


@pytest.mark.parametrize('operation', ['suppress_audit', 'alter_audit', 'suppress_receipt', 'alter_receipt'])
def test_pg_suppressed_or_altered_required_evidence_rolls_back(pg, operation):
    post = seed(pg)
    audit = 'audit' in operation
    table = 'social_audit_events' if audit else 'social_command_receipts'
    condition = "NEW.action='post.archived'" if audit else "NEW.route_key LIKE 'archive/%'"
    alteration = "NEW.new_state='draft';" if audit else "NEW.response='{}'::jsonb;"
    behavior = 'RETURN NULL;' if operation.startswith('suppress') else alteration
    with pg.begin() as conn:
        conn.execute(text(f"""CREATE FUNCTION corrupt_archive_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF {condition} THEN {behavior} END IF; RETURN NEW; END $$"""))
        conn.execute(text(f'CREATE TRIGGER corrupt_archive_evidence BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION corrupt_archive_evidence()'))
    try:
        with Session(pg) as db:
            with pytest.raises(SocialError, match='ARCHIVE_AUDIT_FAILED' if audit else 'COMMAND_RECEIPT_FAILED'):
                archive(db, post)
        with Session(pg) as db:
            current = db.get(SocialPost, UUID(post['id']))
            assert current.editorial_state == 'draft' and current.archived_at is None and current.row_version == 1
            assert db.scalar(select(func.count()).select_from(SocialCommandReceipt)) == 1
            assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action=='post.archived')) == 0
    finally:
        with pg.begin() as conn:
            conn.execute(text(f'DROP TRIGGER corrupt_archive_evidence ON {table}'))
            conn.execute(text('DROP FUNCTION corrupt_archive_evidence()'))


def test_pg_archived_import_cannot_be_claimed_or_admitted(pg):
    """Defensive boundary for stale imported work, beyond normal archive eligibility."""
    from social.worker.repository import GateRejected
    post = seed(pg, approved=True)
    with pg.begin() as conn:
        conn.execute(text("update social_post_targets set state='queued',next_action='publish',next_action_at=now()"))
        conn.execute(text('update social_controls set publishing_enabled=true'))
    repo = repository(pg)
    claim = repo.claim_due()[0]
    with pg.begin() as conn:
        conn.execute(text("update social_posts set editorial_state='archived',archived_at=now()"))
    with pytest.raises(GateRejected, match='POST_ARCHIVED'):
        repo.begin_operation(claim, operation_id=uuid4(), operation='publish', publication_capable=True,
            mutating=True, safe_replay_class='requires_reconciliation', request_fingerprint='a'*64,
            checkpoint_input={})
    with pg.begin() as conn:
        assert conn.scalar(text('select count(*) from social_publish_attempts')) == 0
        conn.execute(text("update social_post_targets set lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,state='queued'"))
    assert repo.claim_due() == []


def test_pg_deferred_receipt_removal_cannot_commit_success(pg):
    post = seed(pg)
    with pg.begin() as conn:
        conn.execute(text("""CREATE FUNCTION remove_archive_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.route_key LIKE 'archive/%' THEN DELETE FROM social_command_receipts WHERE id=NEW.id; END IF; RETURN NEW; END $$"""))
        conn.execute(text('CREATE CONSTRAINT TRIGGER remove_archive_receipt AFTER INSERT ON social_command_receipts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION remove_archive_receipt()'))
    try:
        with Session(pg) as db:
            with pytest.raises(SocialError, match='COMMAND_RECEIPT_FAILED'): archive(db, post)
        with Session(pg) as db:
            current = db.get(SocialPost, UUID(post['id']))
            assert current.editorial_state == 'draft' and current.row_version == 1 and current.archived_at is None
            assert db.scalar(select(func.count()).select_from(SocialCommandReceipt)) == 1
            assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action=='post.archived')) == 0
    finally:
        with pg.begin() as conn:
            conn.execute(text('DROP TRIGGER remove_archive_receipt ON social_command_receipts'))
            conn.execute(text('DROP FUNCTION remove_archive_receipt()'))
