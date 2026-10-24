"""Explicit existing audit-reader graph; never alter production memberships."""
import pytest

from conftest import tool


@pytest.fixture
def role_profile(owner, config):
    with owner.cursor() as c:
        c.execute("SELECT rolname FROM pg_roles WHERE oid=10")
        assert c.fetchone() == (
            "supabase_admin",
        ), "Explicit owned PG fixture must use the provider-style bootstrap role"
    created = False
    try:
        with owner.cursor() as c:
            c.execute("DROP SCHEMA audit_preflight_v2 CASCADE")
            c.execute("CREATE ROLE audit_log_reader NOLOGIN")
            created = True
            c.execute("GRANT SELECT ON private_sentinel TO audit_log_reader")
            c.execute(
                "GRANT audit_log_reader,b71_preflight_reader TO postgres WITH ADMIN TRUE, INHERIT FALSE, SET FALSE"
            )
            c.execute(
                "GRANT audit_log_reader TO b71_preflight_reader WITH ADMIN FALSE, INHERIT TRUE, SET TRUE GRANTED BY postgres"
            )
            c.execute("SELECT oid FROM pg_roles WHERE rolname='audit_log_reader'")
            group = c.fetchone()[0]
            c.execute("SELECT oid FROM pg_roles WHERE rolname='supabase_admin'")
            grantor = c.fetchone()[0]
        yield dict(audit_log_role_oid=group, admin_grantor_oid=grantor)
    finally:
        if created:
            with owner.cursor() as c:
                c.execute("ROLLBACK")
                c.execute("RESET ROLE")
                c.execute("DROP SCHEMA IF EXISTS audit_preflight_v2 CASCADE")
                c.execute(
                    "REVOKE audit_log_reader FROM b71_preflight_reader GRANTED BY postgres"
                )
                c.execute("REVOKE audit_log_reader,b71_preflight_reader FROM postgres")
                c.execute("REVOKE SELECT ON private_sentinel FROM audit_log_reader")
                c.execute("DROP ROLE audit_log_reader")
                c.execute(tool.contract.installation_sql("b71_preflight_reader"))


def install_profile(owner, config, profile):
    with owner.cursor() as c:
        c.execute(
            tool.contract.installation_sql("b71_preflight_reader", role_profile=profile)
        )
        c.execute(
            tool.contract.INTERFACE_SQL,
            tool.contract.interface_parameters(config["database"]["role_oid"], profile),
        )
        row = c.fetchone()
    config["interface"].update(
        namespace_oid=row[0],
        function_oid=row[1],
        owner_oid=row[2],
        role_profile=profile,
    )


def test_pinned_existing_graph_installs_and_runs(
    owner, config, credential, role_profile
):
    with owner.cursor() as c:
        c.execute(
            "SELECT roleid,member,grantor,admin_option,inherit_option,set_option FROM pg_auth_members ORDER BY roleid,member,grantor"
        )
        before = c.fetchall()
        c.execute(
            "SELECT relacl FROM pg_class WHERE oid='public.private_sentinel'::regclass"
        )
        acl = c.fetchone()
    install_profile(owner, config, role_profile)
    with owner.cursor() as c:
        c.execute(
            "SELECT roleid,member,grantor,admin_option,inherit_option,set_option FROM pg_auth_members ORDER BY roleid,member,grantor"
        )
        assert c.fetchall() == before
        c.execute(
            "SELECT relacl FROM pg_class WHERE oid='public.private_sentinel'::regclass"
        )
        assert c.fetchone() == acl
        c.execute(
            "SELECT has_table_privilege('b71_preflight_reader','public.private_sentinel','SELECT')"
        )
        assert c.fetchone() == (True,)
    result = tool.run(config, execute=True, credential=credential)
    assert result["status"] == "OBSERVED_READ_CHECKS_ONLY", result
    assert result["worker_cleanup"]["group_absent"] is True
    assert "PRIVATE-RECORD" not in tool.budget.canonical(result).decode()


def test_default_empty_profile_still_refuses_membership(owner, role_profile):
    with owner.cursor() as c:
        with pytest.raises(Exception, match="PREFLIGHT_.*REFUSED"):
            c.execute(tool.contract.installation_sql("b71_preflight_reader"))
        c.execute("ROLLBACK")
        c.execute("SELECT to_regnamespace('audit_preflight_v2')")
        assert c.fetchone() == (None,)


@pytest.mark.parametrize(
    "bad", [True, False, {}, [], 0, "profile", {"audit_log_role_oid": 1}]
)
def test_profile_builder_rejects_malformed(bad):
    with pytest.raises(ValueError):
        tool.contract.installation_sql("b71_preflight_reader", role_profile=bad)


@pytest.mark.parametrize("key", ["audit_log_role_oid", "admin_grantor_oid"])
@pytest.mark.parametrize("bad", [True, None, 0, -1, 2**32, 1.0, "123", float("nan")])
def test_profile_config_rejects_malformed_oid(config, key, bad):
    profile = dict(audit_log_role_oid=123, admin_grantor_oid=124)
    profile[key] = bad
    config["interface"]["role_profile"] = profile
    with pytest.raises(tool.budget.EvidenceError):
        tool.check_config(config)


def test_profile_key_required(config):
    config["interface"].pop("role_profile", None)
    with pytest.raises(tool.budget.EvidenceError):
        tool.check_config(config)


@pytest.mark.parametrize("key", ["audit_log_role_oid", "admin_grantor_oid"])
@pytest.mark.parametrize("alias", ["owner", "reader"])
def test_profile_oid_aliases_refuse(config, key, alias):
    profile = dict(audit_log_role_oid=123, admin_grantor_oid=124)
    profile[key] = (
        config["interface"]["owner_oid"]
        if alias == "owner"
        else config["database"]["role_oid"]
    )
    config["interface"]["role_profile"] = profile
    with pytest.raises(tool.budget.EvidenceError, match="ROLE_PROFILE_REFUSED"):
        tool.check_config(config)


DRIFT = [
    (
        "GRANT b71_preflight_reader TO postgres WITH ADMIN FALSE",
        "GRANT b71_preflight_reader TO postgres WITH ADMIN TRUE",
    ),
    (
        "GRANT b71_preflight_reader TO postgres WITH INHERIT TRUE",
        "GRANT b71_preflight_reader TO postgres WITH INHERIT FALSE",
    ),
    (
        "GRANT b71_preflight_reader TO postgres WITH SET TRUE",
        "GRANT b71_preflight_reader TO postgres WITH SET FALSE",
    ),
    (
        "GRANT audit_log_reader TO postgres WITH ADMIN FALSE",
        "GRANT audit_log_reader TO postgres WITH ADMIN TRUE",
    ),
    (
        "GRANT audit_log_reader TO postgres WITH INHERIT TRUE",
        "GRANT audit_log_reader TO postgres WITH INHERIT FALSE",
    ),
    (
        "GRANT audit_log_reader TO postgres WITH SET TRUE",
        "GRANT audit_log_reader TO postgres WITH SET FALSE",
    ),
    (
        "GRANT audit_log_reader TO b71_preflight_reader WITH ADMIN TRUE GRANTED BY postgres",
        "GRANT audit_log_reader TO b71_preflight_reader WITH ADMIN FALSE GRANTED BY postgres",
    ),
    (
        "GRANT audit_log_reader TO b71_preflight_reader WITH INHERIT FALSE GRANTED BY postgres",
        "GRANT audit_log_reader TO b71_preflight_reader WITH INHERIT TRUE GRANTED BY postgres",
    ),
    (
        "GRANT audit_log_reader TO b71_preflight_reader WITH SET FALSE GRANTED BY postgres",
        "GRANT audit_log_reader TO b71_preflight_reader WITH SET TRUE GRANTED BY postgres",
    ),
    (
        "GRANT audit_log_reader TO b71_preflight_reader",
        "REVOKE audit_log_reader FROM b71_preflight_reader GRANTED BY supabase_admin",
    ),
    ("ALTER ROLE audit_log_reader LOGIN", "ALTER ROLE audit_log_reader NOLOGIN"),
    (
        "ALTER ROLE audit_log_reader CREATEROLE",
        "ALTER ROLE audit_log_reader NOCREATEROLE",
    ),
    ("ALTER ROLE audit_log_reader NOINHERIT", "ALTER ROLE audit_log_reader INHERIT"),
    (
        "ALTER ROLE audit_log_reader RENAME TO b73_renamed_group",
        "ALTER ROLE b73_renamed_group RENAME TO audit_log_reader",
    ),
    (
        "CREATE ROLE b73_extra; GRANT b71_preflight_reader TO b73_extra",
        "REVOKE b71_preflight_reader FROM b73_extra; DROP ROLE b73_extra",
    ),
    (
        "CREATE ROLE b73_extra; GRANT b73_extra TO b71_preflight_reader",
        "REVOKE b73_extra FROM b71_preflight_reader; DROP ROLE b73_extra",
    ),
    (
        "CREATE ROLE b73_extra; GRANT b73_extra TO audit_log_reader",
        "REVOKE b73_extra FROM audit_log_reader; DROP ROLE b73_extra",
    ),
    (
        "CREATE ROLE b73_extra; GRANT audit_log_reader TO b73_extra",
        "REVOKE audit_log_reader FROM b73_extra; DROP ROLE b73_extra",
    ),
]


@pytest.mark.parametrize(
    "sql,undo", DRIFT, ids=[f"drift-{n}" for n in range(len(DRIFT))]
)
def test_runtime_refuses_profile_drift(
    owner, config, credential, role_profile, sql, undo
):
    install_profile(owner, config, role_profile)
    with owner.cursor() as c:
        c.execute(sql)
    try:
        result = tool.run(config, execute=True, credential=credential)
        assert result["status"] == "REFUSED" and result["observation"] is None, result
    finally:
        with owner.cursor() as c:
            c.execute(undo)


@pytest.mark.parametrize(
    "sql,undo", DRIFT, ids=[f"drift-{n}" for n in range(len(DRIFT))]
)
def test_installer_refuses_profile_drift_atomically(owner, role_profile, sql, undo):
    with owner.cursor() as c:
        c.execute(sql)
        try:
            with pytest.raises(
                Exception, match="PREFLIGHT_(ROLE_GRAPH|READER_ACCESS)_REFUSED"
            ):
                c.execute(
                    tool.contract.installation_sql(
                        "b71_preflight_reader", role_profile=role_profile
                    )
                )
            c.execute("ROLLBACK")
            c.execute("SELECT to_regnamespace('audit_preflight_v2')")
            assert c.fetchone() == (None,)
        finally:
            c.execute("ROLLBACK")
            c.execute(undo)
