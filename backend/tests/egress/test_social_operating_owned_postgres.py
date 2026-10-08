"""Optional SQL execution on this scope's disposable server, never shared ports."""
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts/verification'))
import social_operating_collect as collector

pytestmark=pytest.mark.skipif(os.environ.get('SOCIAL_OPERATING_OWNED_PG') != '61281',
    reason='Requires scope-owned PostgreSQL at private loopback port 61281')


class PrivateFixture(tuple):
    def __repr__(self):
        return '<scope-owned PostgreSQL fixture>'


@pytest.fixture(scope='module')
def owned_database():
    import psycopg2
    admin=psycopg2.connect(host='127.0.0.1',hostaddr='127.0.0.1',port=61281,dbname='postgres',
        user='postgres',password='disposable-egress-fixture',connect_timeout=2)
    admin.autocommit=True
    database='social_operating_owned_fixture'
    with admin.cursor() as cursor:
        cursor.execute('CREATE DATABASE '+database)
        cursor.execute("CREATE ROLE egress_reader LOGIN PASSWORD 'owned-reader-fixture'")
        cursor.execute('GRANT pg_read_all_stats TO egress_reader')
        cursor.execute('REVOKE CREATE,TEMP ON DATABASE '+database+' FROM PUBLIC')
    fixture=psycopg2.connect(host='127.0.0.1',hostaddr='127.0.0.1',port=61281,dbname=database,
        user='postgres',password='disposable-egress-fixture',connect_timeout=2)
    fixture.autocommit=True
    with fixture.cursor() as cursor:
        cursor.execute('CREATE EXTENSION pg_stat_statements')
        cursor.execute('CREATE TABLE private_fixture (value integer)')
        cursor.execute('CREATE SCHEMA pgx_fixture')
        cursor.execute('CREATE TABLE pgx_fixture.private_fixture (value integer)')
        cursor.execute('SELECT 17 AS owned_fixture_marker'); cursor.fetchall()
        cursor.execute("SELECT oid FROM pg_database WHERE datname=current_database()")
        oid=cursor.fetchone()[0]
        cursor.execute("SELECT userid,queryid,toplevel FROM public.pg_stat_statements WHERE dbid=%s AND query='SELECT $1 AS owned_fixture_marker' LIMIT 2",(oid,))
        shapes=cursor.fetchall()
        assert len(shapes)==1
    try:
        yield PrivateFixture((fixture,database,oid,shapes[0]))
    finally:
        fixture.close()
        with admin.cursor() as cursor:
            cursor.execute('DROP DATABASE '+database)
            cursor.execute('DROP ROLE egress_reader')
        admin.close()


def capture(owned_database,tmp_path,missing=False,idle_timeout=None):
    import psycopg2
    admin,database,oid,shape=owned_database
    cert=tmp_path/'ca.crt'; cert.write_text('TEST_DRIVER_ONLY')
    credentials=tmp_path/'credentials.json'
    credentials.write_text(json.dumps({'user':'egress_reader','password':'owned-reader-fixture','sslrootcert':str(cert)}))
    credentials.chmod(0o600)
    config={'schema_version':1,'project_id':'a'*20,'database_name':database,'expected_database_oid':oid,
            'stats_schema':'public','queries':[{'userid':shape[0],'queryid':0 if missing else shape[1],'toplevel':shape[2]}]}
    connections=[]
    def connect(**values):
        # Explicitly labelled injected test transport. No assertion that fixture
        # loopback traffic is authenticated production TLS or billed egress.
        connection=psycopg2.connect(host='127.0.0.1',hostaddr='127.0.0.1',port=61281,dbname=database,
            user=values['user'],password=values['password'],connect_timeout=2,
            application_name=values['application_name'],options=values['options'])
        if idle_timeout is not None:
            connection.autocommit=True
            with connection.cursor() as cursor:
                cursor.execute('SET idle_in_transaction_session_timeout TO %s',(idle_timeout,))
        connections.append(connection)
        return connection
    result=collector.collect(config,credential_file=credentials,execute=True,connect=connect)
    assert len(connections)==1 and connections[0].closed
    assert result['production_authorized'] is False
    return result


def test_actual_least_privilege_statistics_sql_and_cleanup(owned_database,tmp_path):
    result=capture(owned_database,tmp_path)
    assert result['status']=='OBSERVED_COUNTERS_ONLY',result['unknowns']
    assert result['session_observation']=='INJECTED_TEST_DRIVER'
    assert result['snapshot']['entries'][0]['calls']>=1
    assert result['snapshot']['entries'][0]['stats_since'] is not None
    assert result['snapshot']['info_before']['stats_reset']==result['snapshot']['info_after']['stats_reset']


def test_actual_missing_allowlisted_query_remains_partial(owned_database,tmp_path):
    result=capture(owned_database,tmp_path,missing=True)
    assert result['status']=='PARTIAL_OBSERVATION'
    assert result['unknowns']==['ALLOWLISTED_QUERY_MISSING']


@pytest.mark.parametrize('grant,revoke',[
    ('GRANT INSERT ON private_fixture TO egress_reader','REVOKE INSERT ON private_fixture FROM egress_reader'),
    ('GRANT CREATE ON SCHEMA public TO egress_reader','REVOKE CREATE ON SCHEMA public FROM egress_reader'),
    ('ALTER ROLE egress_reader BYPASSRLS','ALTER ROLE egress_reader NOBYPASSRLS'),
    ('ALTER ROLE egress_reader CREATEDB','ALTER ROLE egress_reader NOCREATEDB'),
    ('GRANT INSERT(value) ON private_fixture TO egress_reader','REVOKE INSERT(value) ON private_fixture FROM egress_reader'),
    ('GRANT UPDATE(value) ON private_fixture TO egress_reader','REVOKE UPDATE(value) ON private_fixture FROM egress_reader'),
    ('GRANT CREATE ON SCHEMA pgx_fixture TO egress_reader','REVOKE CREATE ON SCHEMA pgx_fixture FROM egress_reader'),
    ('GRANT INSERT ON pgx_fixture.private_fixture TO egress_reader','REVOKE INSERT ON pgx_fixture.private_fixture FROM egress_reader'),
])
def test_actual_reader_escalation_refused(owned_database,tmp_path,grant,revoke):
    admin=owned_database[0]
    with admin.cursor() as cursor: cursor.execute(grant)
    try:
        result=capture(owned_database,tmp_path)
        assert result['status']=='BLOCKED' and result['unknowns']==['PRIVILEGED_READER_REFUSED']
    finally:
        with admin.cursor() as cursor: cursor.execute(revoke)


def test_relation_ownership_is_refused_even_with_revoked_dml(owned_database,tmp_path):
    admin=owned_database[0]
    with admin.cursor() as cursor:
        cursor.execute('ALTER TABLE private_fixture OWNER TO egress_reader')
        cursor.execute('REVOKE ALL ON private_fixture FROM egress_reader')
    try:
        result=capture(owned_database,tmp_path)
        assert result['status']=='BLOCKED' and result['unknowns']==['PRIVILEGED_READER_REFUSED']
    finally:
        with admin.cursor() as cursor: cursor.execute('ALTER TABLE private_fixture OWNER TO postgres')


@pytest.mark.parametrize('owner',['egress_reader','owned_sequence_role'])
def test_sequence_ownership_including_inherited_role_is_refused(owned_database,tmp_path,owner):
    admin=owned_database[0]
    with admin.cursor() as cursor:
        if owner=='owned_sequence_role':
            cursor.execute('CREATE ROLE owned_sequence_role')
            cursor.execute('GRANT owned_sequence_role TO egress_reader')
        cursor.execute('CREATE SEQUENCE owned_sequence_fixture')
        cursor.execute('ALTER SEQUENCE owned_sequence_fixture OWNER TO '+owner)
        cursor.execute('REVOKE ALL ON SEQUENCE owned_sequence_fixture FROM '+owner)
    try:
        result=capture(owned_database,tmp_path)
        assert result['status']=='BLOCKED' and result['unknowns']==['PRIVILEGED_READER_REFUSED']
    finally:
        with admin.cursor() as cursor:
            cursor.execute('DROP SEQUENCE owned_sequence_fixture')
            if owner=='owned_sequence_role': cursor.execute('DROP ROLE owned_sequence_role')


@pytest.mark.parametrize('privilege,expected',[('USAGE','BLOCKED'),('UPDATE','BLOCKED'),('SELECT','OBSERVED_COUNTERS_ONLY')])
def test_sequence_write_privileges_are_refused_but_select_remains_read_only(owned_database,tmp_path,privilege,expected):
    admin=owned_database[0]
    with admin.cursor() as cursor:
        cursor.execute('CREATE SEQUENCE owned_sequence_fixture')
        cursor.execute('GRANT '+privilege+' ON SEQUENCE owned_sequence_fixture TO egress_reader')
    try:
        result=capture(owned_database,tmp_path)
        assert result['status']==expected
        if expected=='BLOCKED': assert result['unknowns']==['PRIVILEGED_READER_REFUSED']
    finally:
        with admin.cursor() as cursor: cursor.execute('DROP SEQUENCE owned_sequence_fixture')


@pytest.mark.parametrize('timeout',['0','4s','10s'])
def test_idle_transaction_timeout_is_read_back_before_statistics(owned_database,tmp_path,timeout):
    result=capture(owned_database,tmp_path,idle_timeout=timeout)
    assert result['status']=='BLOCKED' and result['unknowns']==['SESSION_GUARDS_MISMATCH']
