"""Legacy source checkers may discover links, never invent financial records."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]


def load(relative):
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "relative, class_name, method",
    [
        ("etl_test_runner.py", "SimpleKenyaETL", "run_full_pipeline"),
        (
            "comprehensive_kenya_etl.py",
            "ComprehensiveKenyaETL",
            "run_comprehensive_pipeline",
        ),
    ],
)
@pytest.mark.parametrize("status", [200, 503, "timeout"])
def test_link_checks_never_become_financial_extractions(
    monkeypatch, relative, class_name, method, status
):
    module = load(relative)
    html = b'<title>Owned source control</title><a href="/budget.pdf">Budget audit report</a>'

    def get(*args, **kwargs):
        if status == "timeout":
            raise requests.Timeout("owned failure")
        return SimpleNamespace(status_code=status, content=html)

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests.Session, "get", get)
    if hasattr(module, "time"):
        monkeypatch.setattr(module.time, "sleep", lambda _: None)
    checker = getattr(module, class_name)()
    result = getattr(checker, method)()
    assert result["detailed_results"]["entities_found"] == []
    assert result["detailed_results"]["documents_fetched"] == 0
    assert result["financial_data"] is None
    assert result["financial_data_status"] == "not_extracted"
    assert "budget_allocation_total" not in result
    assert "spending_total" not in result
    assert "data_quality_score" not in result
    expected_sources = 2 if class_name == "SimpleKenyaETL" else 4
    assert result["sources_tested"] == expected_sources
    assert result["sources_accessible"] == (expected_sources if status == 200 else 0)
    assert result["errors_encountered"] == (0 if status == 200 else expected_sources)
    assert result["pipeline_status"] == (
        "source_checks_completed" if status == 200 else "source_checks_failed"
    )
    treasury = result["detailed_results"]["sources_checked"][0]
    if status == 200:
        assert treasury["page_title"] == "Owned source control"
        links = treasury.get("sample_pdfs") or [
            d["url"] for d in treasury["budget_documents"]
        ]
        assert links[0].endswith("/budget.pdf")
    # A second run measures a new batch, rather than certifying stale success.
    assert getattr(checker, method)()["sources_tested"] == expected_sources


def test_direct_mock_entrypoints_are_retired():
    for relative, class_name, method in [
        ("etl_test_runner.py", "SimpleKenyaETL", "extract_sample_budget_data"),
        (
            "comprehensive_kenya_etl.py",
            "ComprehensiveKenyaETL",
            "extract_comprehensive_entities",
        ),
    ]:
        checker = getattr(load(relative), class_name)()
        with pytest.raises(AttributeError):
            getattr(checker, method)()
    with pytest.raises(AttributeError):
        load("tools/alternative_sources.py").get_mock_comprehensive_data()


def test_unused_mock_app_cannot_be_imported():
    with pytest.raises(FileNotFoundError):
        load("backend/main_simple.py")


def test_ultimate_caller_preserves_observations_without_quality_or_finance(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    module = load("ultimate_kenya_etl.py")
    checker = module.UltimateKenyaETL()
    monkeypatch.setattr(
        requests.Session,
        "get",
        lambda *a, **k: SimpleNamespace(
            status_code=200,
            content=b'<title>Owned success</title><a href="/budget.pdf">Budget</a>',
        ),
    )
    result = checker.run_ultimate_collection()
    assert result["comprehensive_data"] is None
    assert result["financial_data_status"] == "not_extracted"
    assert result["combined_summary"]["total_sources_attempted"] == 5
    assert result["combined_summary"]["total_sources_working"] == 5
    assert "final_quality_score" not in result["combined_summary"]
    assert (
        result["primary_sources"]["treasury"]["budget_documents"][0]["url"]
        == "https://treasury.go.ke/budget.pdf"
    )
    monkeypatch.setattr(
        requests.Session,
        "get",
        lambda *a, **k: SimpleNamespace(status_code=503, content=b""),
    )
    failed = checker.run_ultimate_collection()
    assert failed["combined_summary"]["total_sources_working"] == 0
    assert failed["combined_summary"]["errors_encountered"] == 5
    assert failed["pipeline_status"] == "source_checks_failed"
    assert failed["comprehensive_data"] is None


@pytest.mark.parametrize(
    "entry",
    [
        "etl_test_runner.py",
        "comprehensive_kenya_etl.py",
        "ultimate_kenya_etl.py",
        "demo_complete_system.sh",
    ],
)
@pytest.mark.parametrize("response", ["200", "503", "timeout", "malformed"])
def test_real_cli_accounts_for_failure_and_writes_only_observations(
    tmp_path, entry, response
):
    import subprocess

    # The wrapper replaces HTTP only. It executes the real __main__/shell path.
    wrapper = tmp_path / "owned-python"
    wrapper.write_text(
        f"#!{sys.executable}\n"
        "import os, runpy, sys, time\n"
        "time.sleep = lambda _: None\n"
        "from types import SimpleNamespace\n"
        "import requests\n"
        "def get(*a, **k):\n"
        "    mode = os.environ['OWNED_RESPONSE']\n"
        "    if mode == 'timeout': raise requests.Timeout('owned CLI failure')\n"
        "    if mode == 'malformed': return None\n"
        "    return SimpleNamespace(status_code=int(mode), content=b'<title>Owned CLI</title><a href=\"/budget.pdf\">Budget</a>')\n"
        "requests.get = requests.Session.get = get\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "target = sys.argv.pop(1)\n"
        "if target == '-': exec(compile(sys.stdin.read(), '<summary>', 'exec'))\n"
        "else: sys.argv[0] = target; runpy.run_path(target, run_name='__main__')\n"
    )
    wrapper.chmod(0o700)
    output = tmp_path / "owned-observations.json"
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OWNED_RESPONSE": response,
        "PYTHON": str(wrapper),
    }
    command = (
        ["/bin/bash", str(ROOT / entry), str(output)]
        if entry.endswith(".sh")
        else [str(wrapper), str(ROOT / entry), "--output", str(output)]
    )
    proc = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=15
    )
    assert proc.returncode == (0 if response == "200" else 1), proc.stderr
    body = json.loads(output.read_text())
    finance = body.get("financial_data", body.get("comprehensive_data"))
    assert finance is None
    assert body["financial_data_status"] == "not_extracted"
    assert body["pipeline_status"] == (
        "source_checks_completed" if response == "200" else "source_checks_failed"
    )
    errors = body.get(
        "errors_encountered", body.get("combined_summary", {}).get("errors_encountered")
    )
    assert errors == (
        0
        if response == "200"
        else {
            "etl_test_runner.py": 2,
            "comprehensive_kenya_etl.py": 4,
            "ultimate_kenya_etl.py": 5,
            "demo_complete_system.sh": 2,
        }[entry]
    )
    assert "quality_score" not in output.read_text()
    assert "budget_allocation" not in output.read_text()
    assert "COMPLETE SUCCESS" not in proc.stdout
    if entry.endswith(".sh"):
        if response == "200":
            assert "Sources checked: 2" in proc.stdout
            assert "Discovered link (not downloaded): /budget.pdf" in proc.stdout
        else:
            assert (
                "Sources checked:" not in proc.stdout
            )  # shell stops at failed checker


@pytest.mark.parametrize(
    "response", [b"", b"<title>Empty documents</title>", b'{"budget":9999}', None]
)
def test_successful_homepage_is_not_evidence_of_a_financial_observation(
    monkeypatch, response
):
    module = load("etl_test_runner.py")
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: SimpleNamespace(status_code=200, content=response),
    )
    result = module.SimpleKenyaETL().run_full_pipeline()
    assert result["financial_data"] is None
    assert result["detailed_results"]["entities_found"] == []
    assert result["detailed_results"]["documents_fetched"] == 0
    if response is not None:
        assert result["sources_accessible"] == 2
        assert (
            result["detailed_results"]["sources_checked"][0]["pdf_documents_found"] == 0
        )
    else:
        assert result["errors_encountered"] == 2
