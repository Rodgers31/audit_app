"""Optional digest grants remain explicit and private on real owned PostgreSQL."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text

from social.models import SocialControls
from social.worker.native_authority_schema import create_views, install_native_authority
from social.worker.role_contract import (
    WorkerRoleError, _views, install_worker_role, verify_worker_role,
)
from test_b83_generation_postgres import pg


LOCKED = 'social_native_source_authority'
SNAPSHOT = LOCKED + '_snapshot'


@pytest.fixture
def base_worker(pg):
    factory, owner = pg
    role = 'b119_native_' + uuid4().hex
    with factory.begin() as db:
        db.add(SocialControls(id=1, publishing_enabled=False))
    with owner.begin() as conn:
        conn.execute(text('CREATE ROLE ' + role + " LOGIN PASSWORD 'inert-local-only'"
                          ' NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE'
                          ' NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2'))
    worker = create_engine(owner.url.set(username=role, password='inert-local-only'),
                           pool_size=2, max_overflow=0)
    try:
        install_worker_role(owner, role)
        verify_worker_role(worker, role)
        yield owner, worker, role
    finally:
        worker.dispose()
        with owner.begin() as conn:
            conn.execute(text('DROP VIEW IF EXISTS public.' + LOCKED + ',public.' + SNAPSHOT))
            conn.execute(text('DROP OWNED BY ' + role))
            conn.execute(text('DROP ROLE ' + role))


@pytest.fixture
def native_worker(base_worker):
    owner, worker, role = base_worker
    install_native_authority(owner, role)
    verify_worker_role(worker, role)
    return owner, worker, role


def can_read(owner, role, view):
    with owner.begin() as conn:
        return conn.scalar(text('SELECT has_table_privilege(:role,:view,\'SELECT\')'),
                           {'role': role, 'view': 'public.' + view})


@pytest.mark.parametrize('entrypoint', ['verify', 'ordinary_install', 'native_install'])
@pytest.mark.parametrize('direct', [True, False])
def test_public_select_cannot_stand_in_for_direct_grant(native_worker, entrypoint, direct):
    owner, worker, role = native_worker
    with owner.begin() as conn:
        if not direct:
            conn.execute(text('REVOKE SELECT ON public.' + LOCKED + ' FROM ' + role))
        conn.execute(text('GRANT SELECT ON public.' + LOCKED + ' TO PUBLIC'))
    assert can_read(owner, role, LOCKED) is True  # Prove effective inherited access exists.
    with pytest.raises(WorkerRoleError, match='WORKER_ROLE_UNAVAILABLE'):
        if entrypoint == 'verify':
            verify_worker_role(worker, role)
        elif entrypoint == 'ordinary_install':
            install_worker_role(owner, role)
        else:
            install_native_authority(owner, role)
    # Refusal must not hide the drift by revoking another principal's grant.
    with owner.begin() as conn:
        assert conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_class c,"
                                " LATERAL aclexplode(c.relacl) a"
                                " WHERE c.oid='public." + LOCKED + "'::regclass AND a.grantee=0)"))


@pytest.mark.parametrize('view', [LOCKED, SNAPSHOT])
@pytest.mark.parametrize('privilege', ['SELECT', 'UPDATE', 'MAINTAIN', 'SELECT (authority_fingerprint)'])
def test_native_definition_validation_rejects_any_public_acl(native_worker, view, privilege):
    owner, worker, role = native_worker
    with owner.begin() as conn:
        conn.execute(text('GRANT ' + privilege + ' ON public.' + view + ' TO PUBLIC'))
    with pytest.raises(WorkerRoleError, match='WORKER_ROLE_UNAVAILABLE'):
        with owner.begin() as conn:
            _views(conn, 'public')


@pytest.mark.parametrize('prior_install', [False, True])
def test_ordinary_install_never_admits_optional_digest_grant(base_worker, prior_install):
    owner, worker, role = base_worker
    if prior_install:
        install_native_authority(owner, role)
        with owner.begin() as conn:
            conn.execute(text('REVOKE SELECT ON public.' + LOCKED + ' FROM ' + role))
    else:
        with owner.begin() as conn:
            create_views(conn)
    assert can_read(owner, role, LOCKED) is False
    install_worker_role(owner, role)
    verify_worker_role(worker, role)
    assert can_read(owner, role, LOCKED) is False, 'Ordinary installer expanded optional native authority'
    assert can_read(owner, role, SNAPSHOT) is False
    # Only the separately selected installer can grant this already-existing port.
    install_native_authority(owner, role)
    verify_worker_role(worker, role)
    assert can_read(owner, role, LOCKED) is True
    assert can_read(owner, role, SNAPSHOT) is False


def test_default_reinstall_preserves_healthy_explicit_native_profile(native_worker):
    owner, worker, role = native_worker
    install_worker_role(owner, role)
    install_native_authority(owner, role)
    verify_worker_role(worker, role)
    assert can_read(owner, role, LOCKED) is True
    assert can_read(owner, role, SNAPSHOT) is False


@pytest.mark.parametrize('view,privilege', [
    (LOCKED, 'SELECT WITH GRANT OPTION'),
    (SNAPSHOT, 'SELECT'),
    (SNAPSHOT, 'SELECT (authority_fingerprint)'),
])
def test_worker_snapshot_or_delegable_grant_remains_forbidden(native_worker, view, privilege):
    owner, worker, role = native_worker
    clause = privilege.replace(' WITH GRANT OPTION', '')
    suffix = ' WITH GRANT OPTION' if privilege.endswith(' WITH GRANT OPTION') else ''
    with owner.begin() as conn:
        conn.execute(text('GRANT ' + clause + ' ON public.' + view + ' TO ' + role + suffix))
    with pytest.raises(WorkerRoleError):
        verify_worker_role(worker, role)
    with pytest.raises(WorkerRoleError):
        install_native_authority(owner, role)


def test_partial_column_port_is_not_a_complete_optional_profile(native_worker):
    owner, worker, role = native_worker
    with owner.begin() as conn:
        conn.execute(text('REVOKE SELECT ON public.' + LOCKED + ' FROM ' + role))
        conn.execute(text('GRANT SELECT (authority_fingerprint) ON public.' + LOCKED + ' TO ' + role))
    assert can_read(owner, role, LOCKED) is False
    with pytest.raises(WorkerRoleError):
        verify_worker_role(worker, role)
    with pytest.raises(WorkerRoleError):
        install_worker_role(owner, role)


def test_role_membership_cannot_supply_optional_select(native_worker):
    owner, worker, role = native_worker
    parent = 'b119_parent_' + uuid4().hex
    with owner.begin() as conn:
        conn.execute(text('CREATE ROLE ' + parent))
        conn.execute(text('GRANT SELECT ON public.' + LOCKED + ' TO ' + parent))
        conn.execute(text('GRANT ' + parent + ' TO ' + role))
    try:
        with pytest.raises(WorkerRoleError):
            verify_worker_role(worker, role)
        with pytest.raises(WorkerRoleError):
            install_native_authority(owner, role)
    finally:
        with owner.begin() as conn:
            conn.execute(text('REVOKE ' + parent + ' FROM ' + role))
            conn.execute(text('DROP OWNED BY ' + parent))
            conn.execute(text('DROP ROLE ' + parent))


@pytest.mark.parametrize('entrypoint', ['verify', 'ordinary_install', 'native_install'])
@pytest.mark.parametrize('view,privilege', [
    (LOCKED, 'SELECT'), (SNAPSHOT, 'SELECT'),
    (LOCKED, 'SELECT (authority_fingerprint)'), (SNAPSHOT, 'SELECT (authority_fingerprint)'),
])
def test_unrelated_role_native_acl_drift_refuses(native_worker, entrypoint, view, privilege):
    owner, worker, role = native_worker
    other = 'b119_other_' + uuid4().hex
    with owner.begin() as conn:
        conn.execute(text('CREATE ROLE ' + other))
        conn.execute(text('GRANT ' + privilege + ' ON public.' + view + ' TO ' + other))
    try:
        with pytest.raises(WorkerRoleError):
            if entrypoint == 'verify':
                verify_worker_role(worker, role)
            elif entrypoint == 'ordinary_install':
                install_worker_role(owner, role)
            else:
                install_native_authority(owner, role)
        # Existing ACL drift is refused, never silently repaired by revocation.
        with owner.begin() as conn:
            assert conn.scalar(text("SELECT has_column_privilege(:role,:view,'authority_fingerprint','SELECT')"),
                               {'role': other, 'view': 'public.' + view}) is True
    finally:
        with owner.begin() as conn:
            conn.execute(text('DROP OWNED BY ' + other))
            conn.execute(text('DROP ROLE ' + other))


def test_new_views_strip_only_their_inherited_default_acl(base_worker):
    owner, worker, role = base_worker
    other = 'b119_default_' + uuid4().hex
    with owner.begin() as conn:
        conn.execute(text('CREATE ROLE ' + other))
        conn.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ' + other))
        before = conn.scalar(text("SELECT defaclacl::text FROM pg_default_acl"
                                  " WHERE defaclrole=current_user::regrole AND defaclnamespace='public'::regnamespace"
                                  " AND defaclobjtype='r'"))
        assert other in before  # The hostile default applies to this actual owner.
    try:
        install_native_authority(owner, role)
        verify_worker_role(worker, role)
        assert can_read(owner, role, LOCKED) is True
        assert can_read(owner, role, SNAPSHOT) is False
        assert can_read(owner, other, LOCKED) is False
        assert can_read(owner, other, SNAPSHOT) is False
        with owner.begin() as conn:
            assert conn.scalar(text("SELECT defaclacl::text FROM pg_default_acl"
                                    " WHERE defaclrole=current_user::regrole AND defaclnamespace='public'::regnamespace"
                                    " AND defaclobjtype='r'")) == before
    finally:
        with owner.begin() as conn:
            conn.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM ' + other))
            conn.execute(text('DROP OWNED BY ' + other))
            conn.execute(text('DROP ROLE ' + other))


def test_redundant_worker_column_acl_is_not_the_single_table_grant(native_worker):
    owner, worker, role = native_worker
    with owner.begin() as conn:
        conn.execute(text('GRANT SELECT (authority_fingerprint) ON public.' + LOCKED + ' TO ' + role))
    with pytest.raises(WorkerRoleError):
        verify_worker_role(worker, role)


def test_explicit_install_requires_observed_select_and_rolls_back_without_it(base_worker):
    owner, worker, role = base_worker
    suppressed = []

    def no_grant(conn, cursor, statement, parameters, context, executemany):
        # Execute every catalog/DDL/verification operation on real PostgreSQL,
        # but simulate the grant step having no effect. Role verification alone
        # can accept the base profile, so installation needs its own postcondition.
        if statement.startswith('GRANT SELECT ON public.' + LOCKED + ' TO '):
            suppressed.append(statement)
            return 'SELECT 1', {}
        return statement, parameters

    event.listen(owner, 'before_cursor_execute', no_grant, retval=True)
    try:
        with pytest.raises(WorkerRoleError):
            install_native_authority(owner, role)
    finally:
        event.remove(owner, 'before_cursor_execute', no_grant)
    assert len(suppressed) == 1
    with owner.begin() as conn:
        assert conn.scalar(text("SELECT to_regclass('public." + LOCKED + "')")) is None
        assert conn.scalar(text("SELECT to_regclass('public." + SNAPSHOT + "')")) is None
    verify_worker_role(worker, role)
