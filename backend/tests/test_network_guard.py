"""Positive control for the outbound-network guard in conftest.

The guard exists because eight tests were quietly calling real government and
IFI hosts (api.worldbank.org, treasury.go.ke, cob.go.ke, centralbank.go.ke,
knbs.or.ke, oagkenya.go.ke, imf.org).  Those calls sit inside the seeders'
try/except blocks, so they never failed loudly — they just made the suite's
result depend on the network and on WAF mood.

A block nobody proves is a block nobody has.  These tests prove it blocks, that
it is not over-broad, and that the documented opt-out works.
"""

import httpx
import pytest
import requests

# A host the seeders really do call, so the test fails for the right reason.
REAL_HOST = "https://api.worldbank.org/v2/country/KEN"


def test_outbound_httpx_is_blocked_by_default():
    with pytest.raises(httpx.ConnectError, match="outbound network is disabled"):
        httpx.get(REAL_HOST)


def test_outbound_requests_is_blocked_by_default():
    with pytest.raises(requests.exceptions.ConnectionError, match="outbound network is disabled"):
        requests.get(REAL_HOST, timeout=5)


def test_guard_does_not_break_the_test_client(client):
    """The guard must not touch loopback — TestClient traffic still works."""
    assert client.get("/health/live").status_code == 200


@pytest.mark.network
def test_the_network_marker_lifts_the_block():
    """The opt-out has to actually opt out.

    Asserted white-box (the transport is the unpatched original) rather than by
    making a real call, so the suite stays hermetic even while proving that the
    escape hatch works.
    """
    assert httpx.HTTPTransport.handle_request.__name__ != "_sync", (
        "@pytest.mark.network did not lift the conftest network guard"
    )
