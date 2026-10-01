"""Executable source-shaped controls for #301's detector boundaries."""
import pytest
from tests import test_no_zero_fallback_on_published_figure as zero
from tests import test_apis_no_invented_national_figures as figures
from tests import test_advertised_endpoints_are_served as endpoints


@pytest.mark.parametrize(
    "expr",
    [
        'f"{loan.interest_rate or 0:.2f}%"',
        "f\"Total missing funds: {d.get('missing_funds', 0)} KES\"",
        "f\"{float(getattr(row, 'amount', 0)):,.0f}\"",
    ],
)
def test_formatted_missing_figures_are_seen(expr):
    assert zero.find_zero_fallbacks('payload = {"summary": ' + expr + "}")


@pytest.mark.parametrize(
    "scan,first,second,marker",
    [
        (
            zero.find_zero_fallbacks,
            '"amount": d.get("amount", 0)',
            '"budget": d.get("budget", 0)',
            "zero-fallback-ok:",
        ),
        (
            figures.find_invented_figures,
            '"debt": 1234',
            '"budget": 5678',
            "figure-literal-ok:",
        ),
        (
            lambda s: endpoints.find_unserved_advertisements(s, set()),
            '"endpoints_a": "/a"',
            '"endpoints_b": "/b"',
            "endpoint-ok:",
        ),
    ],
)
def test_inline_suppression_does_not_cover_neighbor(scan, first, second, marker):
    source = (
        "payload = {\n    "
        + first
        + ", # "
        + marker
        + " sourced control\n    "
        + second
        + "\n}"
    )
    assert len(scan(source)) == 1
    assert len(scan(source.replace("sourced control", ""))) == 2


@pytest.mark.parametrize("guard", [figures, endpoints])
def test_sibling_guards_reach_root_and_shipping_backend(guard):
    paths = {p.relative_to(guard.REPO_ROOT).as_posix() for p in guard.SCANNED_MODULES}
    assert "backend/main.py" in paths
    assert "main_enterprise.py" in paths


@pytest.mark.parametrize(
    "source",
    [
        "row = Model(total_budget=1234)",
        'payload = {"debt": make_amount(1234)}',
        'payload = {"budget": d.get("budget", 1234)}',
    ],
)
def test_literals_in_publishing_calls_are_seen(source):
    assert figures.find_invented_figures(source)


@pytest.mark.parametrize(
    "source",
    [
        "budget = Column(Numeric(20, 2))",
        "budget = rows.limit(10).all()",
        "debt_ratio = round(debt/gdp*100, 2)",
        "debt = amount/1e9",
    ],
)
def test_schema_precision_query_limits_and_units_are_structure(source):
    assert figures.find_invented_figures(source) == []


from tests import test_no_route_reads_the_modelled_county_file as modelled


@pytest.mark.parametrize(
    "filename",
    ("enhanced_county_data", "official_county_budget_data", "ultimate_etl_results"),
)
@pytest.mark.parametrize(
    "imp,use",
    [
        ("from bootstrap import COUNTY_DATA_PATH as renamed", "renamed"),
        ("import bootstrap as b", "b.COUNTY_DATA_PATH"),
        ("from helper import renamed", "renamed"),
    ],
)
def test_a_gated_module_cannot_launder_a_raw_path(tmp_path, filename, imp, use):
    graph = modelled._tree(
        tmp_path,
        {
            "backend/bootstrap.py": f'COUNTY_DATA_PATH = "{filename}.json"\ndef initialize_reference_data():\n    return COUNTY_DATA_PATH\n',
            "backend/helper.py": "from bootstrap import COUNTY_DATA_PATH as renamed\n",
            "backend/routes.py": imp
            + '\n@app.get("/raw")\ndef raw():\n    return open('
            + use
            + ").read()\n",
        },
    )
    assert "backend/routes.py" in graph.offending_routes({"backend/bootstrap.py"})


def test_gate_is_only_the_named_reader_and_route_siblings_stay_visible(tmp_path):
    graph = modelled._tree(
        tmp_path,
        {
            "backend/bootstrap.py": 'PATH = "enhanced_county_data.json"\ndef initialize_reference_data():\n    return PATH\n@app.get("/raw")\ndef raw():\n    return open(PATH).read()\n',
            "backend/main.py": 'from bootstrap import initialize_reference_data\n@app.get("/safe")\ndef safe():\n    return initialize_reference_data()\n',
        },
    )
    assert graph.offending_routes({"backend/bootstrap.py"}) == {
        "backend/bootstrap.py": ["backend/bootstrap.py"]
    }


def test_mounted_starlette_and_websocket_surfaces_are_not_invisible():
    from fastapi import Depends, FastAPI, WebSocket
    from fastapi.testclient import TestClient
    from tests import test_write_routes_require_auth as auth

    probe = FastAPI()
    child = FastAPI()
    child.add_api_route("/open", lambda: {}, methods=["POST"])
    child.add_api_route(
        "/gated",
        lambda: {},
        methods=["POST"],
        dependencies=[Depends(auth.supabase_auth.require_admin)],
    )
    probe.mount("/nested", child)

    async def raw(request):
        from starlette.responses import JSONResponse

        return JSONResponse({"ran": True})

    probe.add_route("/raw", raw, methods=["POST"])

    @probe.websocket("/socket")
    async def socket(ws: WebSocket):
        await ws.accept()
        await ws.send_json({"ran": True})
        await ws.close()

    routes = auth._mounted_write_routes(probe)
    verdict = {
        (method, path): bool(
            auth.AUTH_DEPENDENCIES.intersection(auth._dependency_calls(dep))
        )
        for method, path, _, dep in routes
    }
    assert verdict == {
        ("POST", "/nested/open"): False,
        ("POST", "/nested/gated"): True,
        ("POST", "/raw"): False,
        ("WEBSOCKET", "/socket"): False,
    }
    with TestClient(probe) as client:
        assert client.post("/nested/open").status_code == 200
        assert client.post("/raw").json() == {"ran": True}
        with client.websocket_connect("/socket") as ws:
            assert ws.receive_json() == {"ran": True}


def test_a_random_body_is_not_populated_branch_evidence(caplog):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tests import test_model_responses_are_cacheable as cache

    probe = FastAPI()
    count = iter(range(100))

    @probe.get("/random")
    def random_body():
        return {"nonce": next(count)}

    fake = cache.FakeRedisClient()
    with TestClient(probe) as client:
        readings = [
            cache._sweep(client, fake, caplog, [probe.routes[-1]])["/random"]
            for _ in range(4)
        ]
    assert (
        _branch_reason(
            cache,
            readings[0],
            readings[2],
            readings[1],
            readings[3],
            readings[0],
            readings[1],
        )
        is not None
    )

    def answer(body):
        import json

        return (200, body, json.dumps(body), [], frozenset({"loans"}))

    populated = answer({"amount": 0, "source": "synthetic sourced zero"})
    empty = answer({"amount": None, "absent_reason": "not_in_source"})
    assert (
        _branch_reason(cache, populated, empty, populated, empty, populated, populated)
        is None
    )
    assert _branch_reason(cache, empty, empty, empty, empty, empty, empty) is not None
    if len(__import__("inspect").signature(cache._empty_branch_reason).parameters) > 2:
        assert cache._empty_branch_reason(populated, empty) is not None


@pytest.mark.parametrize(
    "source",
    [
        'payload = {"amount": f"{d.get(\'amount\', 0) / 1000:.2f}"}',
        'payload = {"amount": f"{f\'{d.get("amount", 0)}\'}"}',
        'def report():\n    return f"Budget: {value or 0}"',
        'payload={"summary": f"Missing funds: {value or 0}"}',
    ],
)
def test_formatted_arithmetic_nested_output_and_captions(source):
    assert zero.find_zero_fallbacks(source)


def test_format_spec_width_does_not_invent_the_amount():
    source = 'payload={"amount": f"{row.amount:{d.get(\'width\', 0)}}"}'
    assert zero.find_zero_fallbacks(source) == []


def test_two_figures_on_one_line_require_two_reasons():
    source = 'payload={"debt":1234,"budget":5678} # figure-literal-ok: sourced budget'
    findings = figures.find_invented_figures(source)
    assert len(findings) == 1 and "'debt'" in findings[0]


@pytest.mark.parametrize(
    "source",
    ["total_budget=Field(default=1234)", "row=Model(total_budget=Field(default=1234))"],
)
def test_field_defaults_are_measurements_not_schema_precision(source):
    assert figures.find_invented_figures(source)


@pytest.mark.parametrize(
    "route",
    [
        'import backend.bootstrap\n@app.get("/")\ndef route():\n    return open(backend.bootstrap.PATH).read()\n',
        'from bootstrap import raw\ndef unused():\n    from clean import raw\n    return raw()\n@app.get("/")\ndef route():\n    return raw()\n',
        'from wrapper import raw\n@app.get("/")\ndef route():\n    return raw()\n',
        'from bootstrap import raw\nregister=app.get("/")\n@register\ndef route():\n    return raw()\n',
    ],
)
def test_dotted_import_scopes_and_reexports_do_not_hide_readers(tmp_path, route):
    graph = modelled._tree(
        tmp_path,
        {
            "backend/bootstrap.py": 'PATH="enhanced_county_data.json"\ndef raw():\n    return open(PATH).read()\n',
            "backend/clean.py": "def raw():\n    return {}\n",
            "backend/wrapper.py": "from bootstrap import *\n",
            "backend/routes.py": route,
        },
    )
    assert "backend/routes.py" in graph.offending_routes({"backend/bootstrap.py"})


@pytest.mark.parametrize(
    "source",
    [
        "row=Model(total_budget=1e9)",
        'payload={"national_debt":1e12}',
        "gdp=Column(Numeric(20,2), default=1234)",
    ],
)
def test_unit_and_schema_context_cannot_hide_a_typed_amount(source):
    assert figures.find_invented_figures(source)


@pytest.mark.parametrize(
    "source",
    [
        'payload={"amount":f"{d.get(\'amount\',0)}"} # zero-fallback-ok: sourced counter zero',
        'payload={\n # zero-fallback-ok: sourced counter zero\n "amount":f"{d.get(\'amount\',0)}"\n}',
    ],
)
def test_a_reason_on_a_formatted_site_stays_local(source):
    assert zero.find_zero_fallbacks(source) == []
    assert zero.find_zero_fallbacks(source.replace("sourced counter zero", ""))


def test_a_pure_helper_beside_a_reader_does_not_read_the_file(tmp_path):
    graph = modelled._tree(
        tmp_path,
        {
            "backend/helper.py": 'PATH="enhanced_county_data.json"\ndef raw():\n    return open(PATH).read()\ndef safe():\n    return {}\n',
            "backend/routes.py": 'import helper\n@app.get("/")\ndef route():\n    return helper.safe()\n',
        },
    )
    assert graph.offending_routes(set()) == {}


def test_a_starlette_asgi_route_with_unrestricted_methods_is_visible():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.responses import JSONResponse
    from tests import test_write_routes_require_auth as auth

    class Raw:
        async def __call__(self, scope, receive, send):
            await JSONResponse({"ran": True})(scope, receive, send)

    probe = FastAPI()
    probe.add_route("/asgi", Raw())
    routes = auth._mounted_write_routes(probe)
    assert [(m, p) for m, p, _, _ in routes] == [("ANY", "/asgi")]
    assert not auth._dependency_calls(routes[0][3])
    with TestClient(probe) as client:
        assert client.post("/asgi").json() == {"ran": True}


def _branch_reason(cache, *controls):
    # Run the actual verdict on both historical and hardened signatures;
    # a red control must fail on behavior, not on an added parameter.
    from inspect import signature

    return cache._empty_branch_reason(
        *controls[: len(signature(cache._empty_branch_reason).parameters)]
    )


@pytest.mark.parametrize("incidental", [False, True])
def test_only_fixture_state_changes_can_demonstrate_a_data_branch(caplog, incidental):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import StaticPool
    from tests import test_model_responses_are_cacheable as cache

    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with engine.begin() as db:
        db.execute(text("CREATE TABLE entities (id INTEGER)"))
        db.execute(text("INSERT INTO entities VALUES (1)"))
    probe = FastAPI()
    counter = iter(range(100))

    @probe.get("/causal")
    def route():
        with engine.connect() as db:
            count = db.execute(text("SELECT count(*) FROM entities")).scalar_one()
        return {"count": next(counter) // 2 if incidental else count}

    fake = cache.FakeRedisClient()
    try:
        with TestClient(probe) as client:

            def read():
                return cache._sweep(client, fake, caplog, [probe.routes[-1]])["/causal"]

            seeded, seeded_repeat = read(), read()
            with engine.begin() as db:
                db.execute(text("DELETE FROM entities"))
            empty, empty_repeat = read(), read()
            with engine.begin() as db:
                db.execute(text("INSERT INTO entities VALUES (1)"))
            restored, restored_repeat = read(), read()
        verdict = _branch_reason(
            cache, seeded, empty, seeded_repeat, empty_repeat, restored, restored_repeat
        )
        assert (verdict is not None) == incidental
    finally:
        engine.dispose()


def test_thresholds_are_legal_until_used_as_a_published_measurement():
    threshold = (
        "debt_ratio_limit=55\nif observed_ratio > debt_ratio_limit:\n    alert=True\n"
    )
    assert figures.find_invented_figures(threshold) == []
    assert figures.find_invented_figures(
        threshold + 'payload={"debt_to_gdp":debt_ratio_limit}\n'
    )
    assert figures.find_invented_figures('payload={"budget_match":len(rows)==2}') == []
    assert (
        zero.find_zero_fallbacks(
            'payload={"amount":0,"source":"synthetic reported zero"}'
        )
        == []
    )


def test_private_unreferenced_amount_is_not_implicitly_exempt():
    # Another module can import even a private constant. No module-local
    # absence of callers is sufficient evidence to grant a suppression.
    assert figures.find_invented_figures("_TOTAL_DEBT=1234")


@pytest.mark.parametrize(
    "source",
    [
        "if publish({'national_debt':1234}) == True:\n    pass",
        "if publish(Model(total_budget=1234)) == True:\n    pass",
        "budget_threshold=publish({'national_debt':1234})\nif row.budget>budget_threshold:\n    pass",
        "budget_threshold=Model(total_budget=1234)\nif row.budget>budget_threshold:\n    pass",
    ],
)
def test_comparisons_cannot_hide_nested_publishing_calls(source):
    assert figures.find_invented_figures(source)


def test_enterprise_zero_counts_are_sql_group_counts_not_missing_source_defaults(
    tmp_path, monkeypatch
):
    import importlib.util
    import sqlite3
    import sys
    import types
    from fastapi.testclient import TestClient

    root = zero.REPO_ROOT

    def load(path, name):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    reports = load(root / "report_management_system.py", "test_s5_reports")
    manager = reports.KenyaReportManager.__new__(reports.KenyaReportManager)
    manager.db_path = str(tmp_path / "reports.sqlite")
    with sqlite3.connect(manager.db_path) as db:
        db.execute(
            "CREATE TABLE reports (source_agency TEXT, document_type TEXT, financial_year TEXT, is_cached BOOLEAN)"
        )
    provider = types.ModuleType("report_management_system")
    provider.KenyaReportManager = lambda: manager
    monkeypatch.setitem(sys.modules, "report_management_system", provider)
    enterprise = load(root / "main_enterprise.py", "test_s5_enterprise")
    with TestClient(enterprise.app, raise_server_exceptions=False) as client:

        def counts():
            response = client.get("/agencies/status")
            assert response.status_code == 200
            return {row["agency"]: row["document_count"] for row in response.json()}

        assert counts()["National Treasury"] == 0
        assert counts()["Kenya National Bureau of Statistics"] == 0
        with sqlite3.connect(manager.db_path) as db:
            db.execute(
                "INSERT INTO reports VALUES ('National Treasury','budget','2025',TRUE)"
            )
        assert counts()["National Treasury"] == 1
        assert counts()["Kenya National Bureau of Statistics"] == 0
        with sqlite3.connect(manager.db_path) as db:
            db.execute("DROP TABLE reports")
        assert client.get("/agencies/status").status_code == 500
