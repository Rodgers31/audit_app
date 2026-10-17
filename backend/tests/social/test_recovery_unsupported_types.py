"""Owned local PostgreSQL: unsupported schema semantics cannot certify restore."""
import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine,text
from social.recovery_database import capture_database,DatabaseRecoveryError

@pytest.fixture
def owned_database():
    if os.environ.get('B15_REVIEW_RECOVERY_PG')!='1':pytest.skip('Explicit owned loopback55420 opt-in required')
    admin=create_engine('postgresql://postgres@127.0.0.1:55420/postgres',isolation_level='AUTOCOMMIT')
    name='review_'+uuid4().hex
    with admin.connect() as c:c.execute(text('CREATE DATABASE '+name))
    engine=create_engine('postgresql://postgres@127.0.0.1:55420/'+name)
    try:yield engine
    finally:
        engine.dispose()
        with admin.connect() as c:c.execute(text('DROP DATABASE '+name))
        admin.dispose()

@pytest.mark.parametrize('definition',[
    'CREATE DOMAIN app.positive AS integer CHECK(VALUE>0)',
    'CREATE TYPE app.structured AS (amount integer)',
    'CREATE TYPE app.interval_type AS RANGE(subtype=integer)',
])
def test_uninventoried_user_types_refuse_complete_schema_claim(owned_database,definition):
    with owned_database.begin() as c:
        c.execute(text('CREATE SCHEMA app'))
        c.execute(text('CREATE TABLE app.records(id integer)'))
        c.execute(text(definition))
    with pytest.raises(DatabaseRecoveryError):capture_database(owned_database,schema='app',signing_key=b'k'*32,backup_sha256='a'*64)


@pytest.mark.parametrize('definition,column_type',[
    ('CREATE DOMAIN other.positive AS integer CHECK(VALUE>0)','other.positive'),
    ('CREATE DOMAIN other.positive AS integer CHECK(VALUE>0)','other.positive[]'),
    ("CREATE TYPE other.kind AS ENUM('one','two')",'other.kind'),
    ('CREATE TYPE other.structured AS (value integer)','other.structured[]'),
])
def test_external_semantic_column_type_dependency_cannot_hide(owned_database,definition,column_type):
    with owned_database.begin() as c:
        c.execute(text('CREATE SCHEMA app'))
        c.execute(text('CREATE SCHEMA other'))
        c.execute(text(definition))
        c.execute(text('CREATE TABLE app.records(id integer, amount '+column_type+')'))
    with pytest.raises(DatabaseRecoveryError):capture_database(owned_database,schema='app',signing_key=b'k'*32,backup_sha256='a'*64)
