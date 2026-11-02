"""Exact driver migration on owned PG; no arbitrary driver versions are admitted."""
from copy import deepcopy
import pytest
from conftest import tool, ROOT


def test_new_qualified_driver_can_complete_owned_inspection(config, credential):
    import psycopg2
    assert psycopg2.__version__.split()[0] == "2.9.13"
    result = tool.run(config, execute=True, credential=credential, root=ROOT)
    assert result["errors"] == []
    assert result["status"] == "OBSERVED_READ_CHECKS_ONLY"
    assert result["runtime"]["driver"] == "2.9.13"
    assert result["production_authorized"] is False
    assert result["safe_to_write"] is False


@pytest.mark.parametrize("version", ["2.9.12", "2.9.14", "3.0.0", "2.9.130", "unknown"])
def test_unqualified_driver_never_connects(config, credential, monkeypatch, version):
    import psycopg2
    monkeypatch.setattr(psycopg2, "__version__", version)
    monkeypatch.setattr(psycopg2, "connect", lambda **_: pytest.fail("unqualified driver connected"))
    result = tool._connection_run(config, credential, ROOT, tool.report())
    assert result["errors"] == ["DRIVER_UNSUPPORTED"]
    assert result["status"] == "REFUSED"
    assert result["observation"] is None


@pytest.mark.parametrize("version", ["2.9.12", "2.9.14", "3.0.0", "2.9.130", "unknown"])
def test_private_receipt_cannot_substitute_unqualified_driver(monkeypatch, version):
    parent = tool.report()
    child = deepcopy(parent)
    child["runtime"].update(driver=version, libpq=170006)
    child["errors"] = ["DRIVER_UNSUPPORTED"]
    with pytest.raises(tool.budget.EvidenceError, match="WORKER_REPORT_INVALID"):
        tool._validate_worker_report(child, parent, {})
