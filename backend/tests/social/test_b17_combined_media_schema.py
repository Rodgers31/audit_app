"""Existing owned-writer behavior on the full, audit-descendant native head."""
import pytest
from sqlalchemy import text

from test_media_owned_postgres import template, pg_owned  # noqa: F401
from test_media_owned_postgres import test_pg_owned_positive_durable_audit_replay_and_immutable_history as recovery
from test_media_owned_review_postgres import test_owner_census_refuses_filtered_roles_and_restores_setting as census
from test_media_owned_review import test_exact_admitted_attempt_can_acknowledge_after_disable as acknowledge

pytestmark = pytest.mark.parametrize('template', ['current'], indirect=True)


def test_current_head_has_both_mapping_and_private_history(pg_owned):
    _, _, engine = pg_owned
    with engine.connect() as connection:
        mapping = connection.scalar(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='etl_dispatch_commands'::regclass AND conname='ck_etl_dispatch_mapping'"))
        assert "opendata" in mapping
        for name in ('social_media_write_owners', 'social_media_write_attempts'):
            assert connection.scalar(text('SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)'), {'name': name})
            assert not connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_class c, "
                "LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a "
                "WHERE c.oid=CAST(:name AS regclass) AND a.grantee=0)"), {'name': name})


def test_current_head_recovery_replay_and_immutable_history(pg_owned, monkeypatch):
    recovery(pg_owned, monkeypatch)


@pytest.mark.parametrize('table_owner,force,refuses', [(False,False,True), (False,True,True), (True,False,False), (True,True,True)])
@pytest.mark.parametrize('previous', ['on', 'off'])
def test_current_head_role_census_and_setting_restoration(pg_owned, table_owner, force, refuses, previous):
    census(pg_owned, table_owner, force, refuses, previous)


@pytest.mark.parametrize('kind,state', [('grant','not_issued'), ('grant','issued'), ('finalize','completed')])
@pytest.mark.parametrize('closed', [False, True])
def test_current_head_exact_late_acknowledgement(pg_owned, monkeypatch, kind, state, closed):
    acknowledge(pg_owned[:2], monkeypatch, kind, state, closed)
