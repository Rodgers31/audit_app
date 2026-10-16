"""Shared-schema policies do not grant SQL authority to a dedicated worker."""
import pytest
from sqlalchemy import text

from social.worker.role_contract import install_worker_role, verify_worker_role, WorkerRoleError
from worker_ownership_support import role_database


@pytest.mark.parametrize('command', ['SELECT USING(true)', 'UPDATE USING(true) WITH CHECK(true)', 'ALL USING(true) WITH CHECK(true)'])
def test_unrelated_public_policies_without_grants_do_not_block_worker(role_database, command):
    owner, worker, schema, role = role_database
    with owner.begin() as conn:
        conn.execute(text('CREATE TABLE unrelated_profile(id integer)'))
        conn.execute(text('ALTER TABLE unrelated_profile ENABLE ROW LEVEL SECURITY'))
        conn.execute(text('CREATE POLICY unrelated_user_policy ON unrelated_profile FOR ' + command))
    install_worker_role(owner, role, schema)
    verify_worker_role(worker, role, schema)
    with pytest.raises(Exception) as stopped:
        with worker.begin() as conn: conn.execute(text('SELECT * FROM unrelated_profile'))
    assert stopped.value.orig.pgcode == '42501'
    with owner.begin() as conn: conn.execute(text('GRANT SELECT ON unrelated_profile TO PUBLIC'))
    try:
        with pytest.raises(WorkerRoleError): verify_worker_role(worker, role, schema)
    finally:
        with owner.begin() as conn: conn.execute(text('REVOKE SELECT ON unrelated_profile FROM PUBLIC'))


@pytest.mark.parametrize('policy,recipient', [('unexpected_worker', 'worker'), ('scw_unexpected', 'PUBLIC')])
def test_unrelated_worker_or_reserved_policy_still_refuses(role_database, policy, recipient):
    owner, worker, schema, role = role_database
    with owner.begin() as conn:
        conn.execute(text('CREATE TABLE unrelated_profile(id integer)'))
        conn.execute(text('ALTER TABLE unrelated_profile ENABLE ROW LEVEL SECURITY'))
        conn.execute(text('CREATE POLICY ' + policy + ' ON unrelated_profile FOR SELECT TO ' + (role if recipient == 'worker' else recipient) + ' USING(true)'))
    with pytest.raises(WorkerRoleError): install_worker_role(owner, role, schema)
    with owner.connect() as conn:
        assert not conn.execute(text("SELECT has_table_privilege(:role,'social_controls','SELECT')"), {'role': role}).scalar_one()


def test_unrelated_public_statistics_view_still_refuses(role_database):
    owner, worker, schema, role = role_database
    with owner.begin() as conn:
        conn.execute(text('CREATE VIEW unrelated_query_statistics AS SELECT 1 AS query_count'))
        conn.execute(text('GRANT SELECT ON unrelated_query_statistics TO PUBLIC'))
    try:
        with pytest.raises(WorkerRoleError): install_worker_role(owner, role, schema)
    finally:
        with owner.begin() as conn: conn.execute(text('REVOKE SELECT ON unrelated_query_statistics FROM PUBLIC'))
