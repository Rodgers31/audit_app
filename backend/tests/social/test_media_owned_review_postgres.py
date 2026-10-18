"""Recommended PostgreSQL regressions; fixture owner supplies isolated PG only."""
from uuid import uuid4
import pytest
from sqlalchemy import text,select
from sqlalchemy.orm import Session
from social.media import owned_writes
from social.media.models import SocialMediaWriteOwner
from social.media.service import MediaService
from social.service import SocialError
from test_media_owned_postgres import template,pg_owned
from test_media_support import ACTOR,intent

@pytest.mark.parametrize('table_owner,force,refuses',[(False,False,True),(False,True,True),(True,False,False),(True,True,True)],ids=['nonowner','nonowner-force','table-owner','table-owner-force'])
@pytest.mark.parametrize('previous',['on','off'])
def test_owner_census_refuses_filtered_roles_and_restores_setting(pg_owned,table_owner,force,refuses,previous):
    svc,io,engine=pg_owned
    grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4())
    with svc.db.begin():
        asset,upload=svc._rows(grant.asset.id)
        svc.db.get(SocialMediaWriteOwner,asset.id).state='closed'
    role='b17_census_'+uuid4().hex
    with engine.begin() as connection:
        connection.execute(text('CREATE ROLE '+role+' NOLOGIN NOSUPERUSER NOBYPASSRLS'))
        connection.execute(text('GRANT USAGE ON SCHEMA public TO '+role))
        connection.execute(text('GRANT SELECT ON social_media_write_owners,social_media_write_attempts TO '+role))
        if table_owner:connection.execute(text('ALTER TABLE social_media_write_owners OWNER TO '+role))
        if force:connection.execute(text('ALTER TABLE social_media_write_owners FORCE ROW LEVEL SECURITY'))
    try:
        with Session(engine,expire_on_commit=False) as db,db.begin():
            restricted=MediaService(db,svc.runtime)
            db.execute(text('SET LOCAL ROLE '+role))
            db.execute(text('SET LOCAL row_security = '+previous))
            if refuses:
                with pytest.raises(SocialError,match='MEDIA_WRITE_QUIESCENCE_UNCONFIRMED'):
                    owned_writes.owner(restricted,asset,upload)
            else:
                assert owned_writes.owner(restricted,asset,upload).state=='closed'
            assert db.scalar(text('SHOW row_security'))==previous
            assert db.scalar(text('SELECT 1'))==1
            assert db.scalar(text('SELECT current_user'))==role
            assert db.scalar(text('SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user')) is False
        with engine.begin() as connection:
            assert connection.scalar(text('SHOW row_security'))=='on'
            assert connection.scalar(text('SELECT count(*) FROM social_media_write_owners'))==1
    finally:
        with engine.begin() as connection:
            if table_owner:connection.execute(text('ALTER TABLE social_media_write_owners OWNER TO b17_media'))
            connection.execute(text('DROP OWNED BY '+role))
            connection.execute(text('DROP ROLE '+role))

def test_bypass_role_sees_force_rls_owner_without_changing_setting(pg_owned):
    svc,io,engine=pg_owned
    grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4())
    with svc.db.begin():
        asset,upload=svc._rows(grant.asset.id)
        svc.db.execute(text('ALTER TABLE social_media_write_owners FORCE ROW LEVEL SECURITY'))
        previous=svc.db.scalar(text('SHOW row_security'))
        assert owned_writes.owner(svc,asset,upload).asset_id==asset.id
        assert svc.db.scalar(text('SHOW row_security'))==previous

def test_unrelated_schema_owner_is_not_the_installed_table_owner(pg_owned):
    svc,io,engine=pg_owned
    grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4())
    with svc.db.begin():asset,upload=svc._rows(grant.asset.id)
    role='b17_schema_'+uuid4().hex
    schema='b17_empty_'+uuid4().hex
    with engine.begin() as connection:
        connection.execute(text('CREATE ROLE '+role+' NOLOGIN NOSUPERUSER NOBYPASSRLS'))
        connection.execute(text('CREATE SCHEMA '+schema+' AUTHORIZATION '+role))
        connection.execute(text('GRANT USAGE ON SCHEMA public TO '+role))
        connection.execute(text('GRANT SELECT ON public.social_media_write_owners TO '+role))
    try:
        with Session(engine,expire_on_commit=False) as db,db.begin():
            restricted=MediaService(db,svc.runtime)
            db.execute(text('SET LOCAL ROLE '+role))
            db.execute(text('SET LOCAL search_path = '+schema+',public'))
            with pytest.raises(SocialError,match='MEDIA_WRITE_QUIESCENCE_UNCONFIRMED'):
                owned_writes.owner(restricted,asset,upload)
            assert db.scalar(text('SHOW row_security'))=='on'
            assert db.scalar(text('SELECT 1'))==1
    finally:
        with engine.begin() as connection:
            connection.execute(text('DROP SCHEMA '+schema))
            connection.execute(text('DROP OWNED BY '+role))
            connection.execute(text('DROP ROLE '+role))
