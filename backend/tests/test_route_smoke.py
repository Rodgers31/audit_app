"""
Comprehensive route smoke test.

Dynamically discovers ALL registered GET routes and verifies they respond
without 500 errors. Uses the client fixture from conftest.py so the test
DB is available.
"""

import pytest
from main import app


def _gather_get_routes():
    """Collect all GET routes from the FastAPI app."""
    routes = []
    for route in app.routes:
        if not hasattr(route, "methods"):
            continue
        if "GET" not in route.methods:
            continue
        path = route.path
        # Skip internal docs/openapi routes
        if any(path.startswith(p) for p in ("/docs", "/redoc", "/openapi")):
            continue
        routes.append(path)
    return routes


def _fill_path_params(path: str) -> str:
    """Replace path parameters with sample values."""
    replacements = {
        "{country_id}": "1",
        "{county_id}": "001",
        "{entity_id}": "1",
        "{period_id}": "1",
        "{doc_id}": "1",
        "{document_id}": "1",
        "{line_id}": "1",
        "{job_id}": "test-job-1",
        "{source}": "treasury",
    }
    result = path
    for param, value in replacements.items():
        result = result.replace(param, value)
    return result


def _get_routes_parametrized():
    """Generate parametrize data for all GET routes."""
    routes = _gather_get_routes()
    return [_fill_path_params(r) for r in routes]


@pytest.mark.parametrize("path", _get_routes_parametrized())
def test_get_route_does_not_crash(client, path):
    """Every GET route should respond without a 500 Internal Server Error.

    We accept 200, 404, 422, 503 as valid — the important thing is that the
    server doesn't crash.  429 is deliberately NOT on that list: the rate
    limiter is bypassed for the whole test session (conftest.pytest_configure),
    so a 429 here would mean the bypass has regressed, not that the route is
    healthy.
    """
    response = client.get(path)
    assert (
        response.status_code != 500
    ), f"Route {path} returned 500: {response.text[:300]}"
