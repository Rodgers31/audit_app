"""Worker lane's explicitly assigned disposable PostgreSQL fixture.

Never uses or changes the historical port62124 fixture, which may be leased to
another lane. Requires a separate explicit loopback55484 DSN.
"""
import os
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from social.models import SocialControls
from test_domain_postgres import migration
from test_connections_migration_postgres import upgrade


@pytest.fixture
def role_database():
    raw = os.environ['SOCIAL_GLOBAL_OWNER_TEST_DATABASE_URL']
    url = make_url(raw)
    if ('?' in raw or url.host != '127.0.0.1' or url.port != 55484
            or url.database != 'social_domain_test' or url.drivername not in ('postgresql','postgresql+psycopg2')):
        raise ValueError('Only assigned loopback55484/social_domain_test is allowed')
    url = url.set(drivername='postgresql+psycopg2', query={'hostaddr':'127.0.0.1'})
    schema, role = 'worker_b14_' + uuid4().hex, 'worker_b14_' + uuid4().hex
    admin = create_engine(url, pool_size=1, max_overflow=0)
    owner = create_engine(url, pool_size=2, max_overflow=0, connect_args={'options':'-csearch_path='+schema})
    worker = create_engine(url.set(username=role, password=None), pool_size=2,max_overflow=0,
                           connect_args={'options':'-csearch_path=pg_catalog,'+schema+',pg_temp'})
    with admin.begin() as conn:
        conn.execute(text('CREATE SCHEMA '+schema))
        conn.execute(text('CREATE ROLE '+role+' LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2'))
    try:
        with owner.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            migration().upgrade()
        upgrade(owner, current=True)
        with Session(owner) as db:
            db.add(SocialControls(id=1,publishing_enabled=False)); db.commit()
        yield owner,worker,schema,role
    finally:
        worker.dispose();owner.dispose()
        with admin.begin() as conn: conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        with admin.begin() as conn: conn.execute(text('DROP ROLE '+role))
        admin.dispose()
