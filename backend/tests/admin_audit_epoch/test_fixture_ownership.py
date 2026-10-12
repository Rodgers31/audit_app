"""Owned fixture guards refuse before any destructive connection or statement."""
from types import SimpleNamespace

import pytest

from tests.admin_audit_epoch import ephemeral_database as fixture

SAFE = "postgresql+psycopg2://batch10_mappings:batch10-inert-local@127.0.0.1:55522/batch10_mappings"


def test_failed_probe_close_still_attempts_independent_owned_probe():
    closed = []
    class FailingProbe:
        def close(self):
            raise OSError("controlled uncertain close")
    class HealthyProbe:
        def close(self):
            closed.append(True)
    with pytest.raises(RuntimeError, match="cleanup remains unverified"):
        fixture.close_owned_connections([FailingProbe(), HealthyProbe()])
    assert closed == [True]


@pytest.mark.parametrize("raw", [None, "", "sqlite:///owned.db",
    SAFE.replace("127.0.0.1", "localhost"), SAFE.replace("55522", "55545"),
    SAFE.replace("batch10-inert-local", "wrong"), SAFE + "?host=127.0.0.1",
    SAFE.replace("/batch10_mappings", "/batch12_audit_case_forged")])
def test_profile_refuses_unowned_targets(raw):
    with pytest.raises(Exception):
        fixture.profile(raw)


def test_ambient_redirect_refuses_even_exact_profile(monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "127.0.0.1")
    with pytest.raises(ValueError):
        fixture.profile(SAFE)


class NoDatabase:
    def connect(self):
        raise AssertionError("Unregistered resource reached database transport")

    def dispose(self):
        pass


def test_unregistered_database_drop_refuses_before_transport():
    value = fixture.EmptyTemplate.__new__(fixture.EmptyTemplate)
    value.created, value.original = {}, None
    value.url, value.control = SimpleNamespace(database="batch10_mappings"), NoDatabase()
    with pytest.raises(ValueError):
        value.drop("batch10_mappings", (1, "batch10_mappings", "123"))


@pytest.mark.parametrize("mode", [None, "false", 0, 1, float("nan")])
def test_direct_case_factory_refuses_nonboolean_mode(mode):
    with pytest.raises(ValueError):
        with fixture.EmptyTemplate.database(NoDatabase(), fixed_name=mode):
            raise AssertionError("Malformed name mode admitted")


def test_unregistered_engine_refuses_child_process_target():
    value = SimpleNamespace(url=fixture.profile(SAFE))
    with pytest.raises(ValueError):
        fixture.validate_created_engine(value)


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def one(self):
        return self.rows[0]

    def all(self):
        return self.rows


class Catalog:
    def __init__(self, row=(123, "batch10_mappings", "111"), *, actual_user="batch10_mappings", actual_database="batch10_mappings", state=(True, False)):
        self.row, self.actual_user, self.actual_database, self.state = row, actual_user, actual_database, state
        self.destructive = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def connect(self):
        return self

    def begin(self):
        return self

    def dispose(self):
        pass

    def execute(self, sql, params=None):
        value = str(sql)
        if "SELECT current_database(),current_user,current_schema()" in value:
            return Rows([(self.actual_database, self.actual_user, "public")])
        if "FROM pg_database WHERE datname=:name" in value:
            return Rows([self.row])
        if "SELECT singleton,certified" in value:
            return Rows([self.state])
        if value.startswith(("DROP DATABASE", "UPDATE public.admin_audit_storage")):
            self.destructive.append(value)
            return Rows([])
        raise AssertionError("Unexpected controlled catalog statement: " + value)

    def scalar(self, sql, params=None):
        value = str(sql)
        if value == "SELECT current_user":
            return self.actual_user
        if "SELECT version_num" in value:
            return "a611b12a0001"
        if "SELECT EXISTS" in value:
            return False
        raise AssertionError("Unexpected controlled scalar: " + value)


@pytest.mark.parametrize("row", [(0, "owner", "111"), (-1, "owner", "111"),
    (True, "owner", "111"), (123, "owner", None), (123, "owner", ""),
    (123, "owner", True), (123, "owner", "nan"), (123, "owner", "0")])
def test_identity_refuses_unverifiable_native_catalog_fields(row):
    with pytest.raises(RuntimeError):
        fixture.identity(Catalog(row), "owned", "owner")


def template_double(catalog, name="batch12_audit_template_inert"):
    value = fixture.EmptyTemplate.__new__(fixture.EmptyTemplate)
    value.url, value.control = fixture.profile(SAFE), catalog
    value.created, value.original = {name: (123, "batch10_mappings", "111")}, None
    return value


def test_refresh_refuses_replaced_registered_database_before_update(monkeypatch):
    catalog = Catalog((456, "batch10_mappings", "111"), actual_database="batch12_audit_template_inert")
    value = template_double(catalog)
    monkeypatch.setattr(fixture, "create_engine", lambda *a, **k: catalog)
    with pytest.raises(RuntimeError):
        value._refresh("batch12_audit_template_inert")
    assert catalog.destructive == []


def test_changed_control_login_refuses_registered_drop_before_effect():
    catalog = Catalog(actual_user="peer", actual_database="postgres")
    value = template_double(catalog)
    with pytest.raises(RuntimeError):
        value.drop("batch12_audit_template_inert", value.created["batch12_audit_template_inert"])
    assert catalog.destructive == []


def test_bool_expected_identity_cannot_alias_integer_database_oid():
    catalog = Catalog((1, "batch10_mappings", "111"), actual_database="postgres")
    value = template_double(catalog)
    value.created["batch12_audit_template_inert"] = catalog.row
    with pytest.raises(ValueError):
        value.drop("batch12_audit_template_inert", (True, "batch10_mappings", "111"))
    assert catalog.destructive == []


def test_registered_url_cannot_hide_changed_actual_connection(monkeypatch):
    catalog = Catalog(actual_database="peer")
    value = template_double(catalog, "batch10_mappings")
    catalog.url = value.url
    monkeypatch.setitem(fixture._LIVE, SAFE, (value, "batch10_mappings", catalog.row))
    with pytest.raises(RuntimeError):
        fixture.validate_created_engine(catalog)


def test_stale_live_registration_refuses_before_connection(monkeypatch):
    value = template_double(NoDatabase())
    value.created.clear()
    engine = SimpleNamespace(url=value.url, connect=NoDatabase().connect)
    monkeypatch.setitem(fixture._LIVE, SAFE, (value, "batch10_mappings", (123, "batch10_mappings", "111")))
    with pytest.raises(ValueError):
        fixture.validate_created_engine(engine)


def test_extra_storage_fields_are_not_an_empty_template_certificate(monkeypatch):
    monkeypatch.setattr(fixture, "head", lambda: "a611b12a0001")
    with pytest.raises(RuntimeError):
        fixture.empty_full_head(Catalog(state=(True, False, "unrecognized")))


def test_mapping_keys_are_not_native_identity_fields():
    with pytest.raises(RuntimeError):
        fixture.identity(Catalog({0: 123, 1: "owner", 2: "111"}), "owned", "owner")


def test_mapping_keys_are_not_empty_storage_booleans(monkeypatch):
    monkeypatch.setattr(fixture, "head", lambda: "a611b12a0001")
    with pytest.raises(RuntimeError):
        fixture.empty_full_head(Catalog(state={0: True, 1: False}))


def test_original_emptiness_read_refuses_changed_connection_before_drop(monkeypatch):
    control = Catalog(actual_database="postgres")
    original = Catalog(actual_database="peer")
    value = template_double(control)
    value.original = control.row
    monkeypatch.setattr(fixture, "create_engine", lambda *a, **k: original)
    with pytest.raises(RuntimeError):
        value.drop(value.url.database, value.original)
    assert control.destructive == []


def test_uncertain_create_name_is_retained_and_cleanup_is_explicit(capsys):
    value = template_double(NoDatabase())
    value.created.clear()
    value.pending = {"batch12_audit_case_uncertain"}
    with pytest.raises(RuntimeError, match="cleanup remains unverified"):
        value.close()
    assert value.pending == {"batch12_audit_case_uncertain"}
    assert '"cleanup": false' in capsys.readouterr().out


def test_close_checks_independent_resources_after_changed_identity(monkeypatch, capsys):
    value = template_double(NoDatabase())
    value.pending = set()
    value.created["batch12_audit_case_safe"] = (456, "batch10_mappings", "111")
    observed = []
    def drop(name, expected):
        observed.append(name)
        if "template" in name:
            raise RuntimeError("Changed identity; removal refused")
        value.created.pop(name)
    monkeypatch.setattr(value, "drop", drop)
    with pytest.raises(RuntimeError, match="cleanup remains unverified"):
        value.close()
    assert observed == ["batch12_audit_template_inert", "batch12_audit_case_safe"]
    assert list(value.created) == ["batch12_audit_template_inert"]
    assert '"cleanup": false' in capsys.readouterr().out
