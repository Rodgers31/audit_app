"""Replay the auth-schema migrations on an owned, loopback-only PostgreSQL cluster.

No configured database URL or hosted account is read. Fixture grants model
Supabase's exposed-table defaults; the migrations themselves change no grants.
"""

import shutil
import subprocess
from pathlib import Path

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[3]
A = '00000000-0000-4000-8000-000000000001'
B = '00000000-0000-4000-8000-000000000002'


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    docker = shutil.which('docker')
    if not docker:
        pytest.skip('Docker and a cached postgres:17 image required')
    import time
    from uuid import uuid4
    name = 'oct24-security-' + uuid4().hex[:12]
    result = subprocess.run([docker, 'run', '--detach', '--pull=never', '--name', name,
        '--memory=192m', '--cpus=0.5', '--pids-limit=64', '-p', '127.0.0.1::5432',
        '-e', 'POSTGRES_PASSWORD=fixture', '-e', 'POSTGRES_USER=fixture_owner',
        '-e', 'POSTGRES_DB=fixture', 'postgres:17', '-c', 'max_connections=10',
        '-c', 'shared_buffers=16MB', '-c', 'work_mem=1MB', '-c', 'temp_file_limit=16384',
        '-c', 'max_parallel_workers=0', '-c', 'autovacuum=off'],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    container = result.stdout.strip()
    def connect():
        return psycopg2.connect(host='127.0.0.1', port=port, dbname='fixture',
            user='fixture_owner', password='fixture', connect_timeout=2,
            options='-c statement_timeout=2000 -c lock_timeout=1000')
    try:
        mapping = subprocess.check_output([docker, 'port', container, '5432/tcp'],
                                          text=True, timeout=5).strip()
        assert mapping.startswith('127.0.0.1:'), mapping
        port = int(mapping.rsplit(':', 1)[1])
        deadline = time.monotonic() + 20
        while True:
            try:
                ready = connect()
                ready.close()
                break
            except psycopg2.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        with connect() as db, db.cursor() as c:
            c.execute("CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;")
            c.execute("CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY, email text, raw_user_meta_data jsonb);")
            c.execute("CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub', true),'')::uuid $$;")
            c.execute((ROOT / 'supabase/migrations/20260227_user_features.sql').read_text())
            for migration in sorted((ROOT / 'supabase/migrations').glob('20261024_*.sql')):
                c.execute(migration.read_text())
            c.execute("GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;")
            c.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated, service_role;")
            c.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;")
            c.execute("INSERT INTO auth.users VALUES (%s,'one@example.invalid','{}'),(%s,'two@example.invalid','{}')", (A, B))
            c.execute("INSERT INTO newsletter_subscribers(email) VALUES ('private@example.invalid')")
        yield connect
    finally:
        subprocess.run([docker, 'rm', '--force', '--volumes', container],
                        check=True, capture_output=True, timeout=10)


@pytest.fixture
def caller(cluster):
    db = cluster()
    with db.cursor() as c:
        c.execute("SET ROLE authenticated")
        c.execute("SELECT set_config('request.jwt.claim.sub', %s, false)", (A,))
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def test_user_cannot_change_own_authorization_roles(caller):
    with caller.cursor() as c, pytest.raises(psycopg2.errors.InsufficientPrivilege):
        c.execute("UPDATE profiles SET roles=ARRAY['admin'] WHERE id=%s", (A,))


@pytest.mark.parametrize('roles', [['admin'], ['citizen', 'admin'], [], None])
def test_fallback_insert_cannot_supply_authorization_roles(cluster, roles):
    with cluster() as db, db.cursor() as c:
        c.execute('DELETE FROM profiles WHERE id=%s', (A,))
        c.execute('SET ROLE authenticated')
        c.execute("SELECT set_config('request.jwt.claim.sub', %s, false)", (A,))
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            c.execute('INSERT INTO profiles(id,email,roles) VALUES (%s,%s,%s)',
                      (A, 'one@example.invalid', roles))
        db.rollback()


def test_service_role_and_normal_profile_edits_still_work(cluster):
    with cluster() as db, db.cursor() as c:
        c.execute('SET ROLE service_role')
        c.execute("UPDATE profiles SET roles=ARRAY['admin'] WHERE id=%s", (A,))
        assert c.rowcount == 1
        c.execute('SET ROLE authenticated')
        c.execute("SELECT set_config('request.jwt.claim.sub', %s, false)", (A,))
        c.execute("UPDATE profiles SET display_name='Fixture Name' WHERE id=%s RETURNING roles", (A,))
        assert c.fetchone()[0] == ['admin']
        c.execute('SELECT id FROM profiles')
        assert c.fetchall() == [(A,)]
        db.rollback()


def test_citizen_fallback_insert_still_works(cluster):
    with cluster() as db, db.cursor() as c:
        c.execute('DELETE FROM profiles WHERE id=%s', (A,))
        c.execute('SET ROLE authenticated')
        c.execute("SELECT set_config('request.jwt.claim.sub', %s, false)", (A,))
        c.execute('INSERT INTO profiles(id,email) VALUES (%s,%s) RETURNING roles', (A, 'one@example.invalid'))
        assert c.fetchone()[0] == ['citizen']
        db.rollback()


@pytest.mark.parametrize('role', ['anon', 'authenticated'])
def test_newsletter_table_is_private_to_server(cluster, role):
    with cluster() as db, db.cursor() as c:
        c.execute('SET ROLE ' + role)  # fixed fixture roles only
        c.execute('SELECT email FROM newsletter_subscribers')
        assert c.fetchall() == [], 'browser role could read subscriber records'
        c.execute('UPDATE newsletter_subscribers SET confirmed=true')
        assert c.rowcount == 0
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            c.execute("INSERT INTO newsletter_subscribers(email) VALUES ('other@example.invalid')")
        db.rollback()


def test_service_role_retains_newsletter_access(cluster):
    with cluster() as db, db.cursor() as c:
        c.execute('SET ROLE service_role')
        c.execute('SELECT email FROM newsletter_subscribers')
        assert c.fetchall() == [('private@example.invalid',)]
        db.rollback()
