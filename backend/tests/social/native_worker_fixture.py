"""Owned current-schema PostgreSQL login with explicitly installed digest port."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from social.models import SocialControls
from social.worker.role_contract import install_worker_role, verify_worker_role
from social.worker.native_authority_schema import install_native_authority

@pytest.fixture
def restricted(pg):
 factory,owner=pg;role='b118_worker_'+uuid4().hex
 with factory.begin()as db:db.add(SocialControls(id=1,publishing_enabled=False))
 with owner.begin()as conn:conn.execute(text('CREATE ROLE '+role+" LOGIN PASSWORD 'inert-local-only' NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2"))
 worker=create_engine(owner.url.set(username=role,password='inert-local-only'),pool_size=2,max_overflow=0)
 try:
  install_worker_role(owner,role)
  install_native_authority(owner,role)
  install_native_authority(owner,role) # complete installation is idempotent
  verify_worker_role(worker,role)
  yield factory,owner,worker,role
 finally:
  worker.dispose()
  with owner.begin()as conn:
   conn.execute(text('DROP VIEW IF EXISTS social_native_source_authority,social_native_source_authority_snapshot'))
   conn.execute(text('DROP OWNED BY '+role));conn.execute(text('DROP ROLE '+role))
