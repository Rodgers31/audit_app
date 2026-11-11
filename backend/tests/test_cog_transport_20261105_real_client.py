"""Actual DNS/connect/TLS/body recovery and ORM writes over owned local peers.

Synthetic names exercise identity and outage preservation, never publisher
freshness. The execution namespace has no external route or production access.
"""
import copy
from datetime import datetime, timedelta, timezone
import socket
import ssl
import time

import httpx
import pytest

from models import SourceDocument
from oag_transport_20261105_loopback import official_peer
from seeding.config import SeedingSettings
from seeding.extractors.cog_governors import DEPUTIES_SOURCE_URL, KENYAN_COUNTIES, SOURCE_URL
from seeding.http_client import SeedingHttpClient
from seeding.types import DomainRunContext
from test_cog_governors import _synthetic, page
from test_county_officials_deputies import counties

ROSTER = page([(_synthetic(c), c) for c in KENYAN_COUNTIES]).encode()
DEPUTIES = page([(_synthetic(c).replace("Mwangi", "Wanjiru"), c) for c in KENYAN_COUNTIES]).encode()


@pytest.fixture(autouse=True)
def _no_outbound_network():
    # official_peer supplies a deny-by-default DNS map for the real transport.
    yield


def configuration(tmp_path):
    return SeedingSettings(_env_file=None, storage_path=tmp_path, http_cache_enabled=False,
        rate_limit="1000/sec", max_retries=3, retry_backoff=.001, timeout_seconds=.15)


def send_body(handler, body):
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


@pytest.mark.parametrize("failure", ["dns", "connect", "body_interrupted", "body_timeout"])
def test_actual_client_recovers_and_stores_exact47_distinct_identities_and_separate_deputies(
        db_session, counties, tmp_path, monkeypatch, failure):
    import seeding.domains.county_officials as domain

    attempts = []

    def respond(handler):
        attempts.append(handler.path)
        if len(attempts) == 1 and failure == "body_interrupted":
            handler.send_response(200)
            handler.send_header("Content-Length", str(len(ROSTER) + 10))
            handler.end_headers()
            handler.wfile.write(b"partial")
            handler.wfile.flush()
            handler.connection.shutdown(socket.SHUT_WR)
            return
        if len(attempts) == 1 and failure == "body_timeout":
            handler.send_response(200)
            handler.send_header("Content-Length", str(len(ROSTER)))
            handler.end_headers()
            handler.wfile.flush()
            time.sleep(.35)
            handler.wfile.write(ROSTER)
            return
        send_body(handler, ROSTER if handler.path == "/current-governors/" else DEPUTIES)

    configured = configuration(tmp_path)
    with official_peer(tmp_path, monkeypatch, host="cog.go.ke", respond=respond) as peer:
        dns = socket.getaddrinfo
        dns_attempts = []
        # Hold an owned, non-listening port to get a real ECONNREFUSED without
        # contacting any other process, then remove it with this fixture.
        with socket.socket() as closed_peer:
            closed_peer.bind(("127.0.0.1", 0))
            refused_port = closed_peer.getsockname()[1]

            def recover_dns(host, port, *args, **kwargs):
                if host in ("cog.go.ke", b"cog.go.ke"):
                    dns_attempts.append(host)
                    if len(dns_attempts) == 1:
                        if failure == "dns":
                            raise socket.gaierror(socket.EAI_AGAIN, "owned temporary DNS failure")
                        if failure == "connect":
                            return dns("127.0.0.1", refused_port, *args, **kwargs)
                return dns(host, port, *args, **kwargs)

            monkeypatch.setattr(socket, "getaddrinfo", recover_dns)
            client = SeedingHttpClient(configured,
                client=httpx.Client(verify=peer["trust"], trust_env=False, follow_redirects=True))
            monkeypatch.setattr(domain, "create_http_client", lambda _: client)
            result = domain.run(db_session, configured, DomainRunContext(None, False))
            db_session.commit()
        assert not result.errors
        assert result.items_processed == 47
        assert set(counties) == set(KENYAN_COUNTIES) and len(counties) == 47
        assert len({row.meta["governor"].casefold() for row in counties.values()}) == 47
        assert len({row.meta["deputy_governor"].casefold() for row in counties.values()}) == 47
        for county, row in counties.items():
            assert row.meta["governor"] == _synthetic(county).removeprefix("H.E ")
            assert row.meta["deputy_governor"] == _synthetic(county).removeprefix("H.E ").replace("Mwangi", "Wanjiru")
            assert row.meta["governor_provenance"]["source_url"] == SOURCE_URL
            assert row.meta["deputy_governor_provenance"]["source_url"] == DEPUTIES_SOURCE_URL
        docs = {d.url: d for d in db_session.query(SourceDocument).all()}
        assert set(docs) == {SOURCE_URL, DEPUTIES_SOURCE_URL}
        for url, body in [(SOURCE_URL, ROSTER), (DEPUTIES_SOURCE_URL, DEPUTIES)]:
            receipt = docs[url].meta["response_receipt"]
            assert receipt["request_url"] == receipt["response_url"] == url
            assert client.receipt_store.read(receipt["storage_key"]) == body
        assert result.metadata["source_status"] == dict(
            state="live", fixture_used=False, governors_observed=47, deputies_state="live")
        assert attempts[-1] == "/current-deputy-governors/"
        assert len(attempts) == (3 if failure.startswith("body_") else 2)
        assert len(dns_attempts) == 3
        assert peer["foreign"] == []


@pytest.mark.parametrize("failure", ["dns", "tls", "interruption"])
def test_outage_keeps_last_good_names_timestamps_and_known_age(
        db_session, counties, tmp_path, monkeypatch, failure):
    import seeding.domains.county_officials as domain

    stamp = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    for county, row in counties.items():
        row.meta = dict(governor=county + " Previous", deputy_governor=county + " Deputy",
            governor_provenance={"fetched_at": stamp}, deputy_governor_provenance={"fetched_at": stamp})
    db_session.commit()
    before = {name: copy.deepcopy(row.meta) for name, row in counties.items()}

    def respond(handler):
        handler.send_response(200)
        handler.send_header("Content-Length", str(len(ROSTER) + 1))
        handler.end_headers()
        handler.wfile.write(b"partial")
        handler.connection.shutdown(socket.SHUT_WR)

    configured = configuration(tmp_path)
    with official_peer(tmp_path, monkeypatch, host="cog.go.ke", respond=respond) as peer:
        dns = socket.getaddrinfo
        attempts = []

        def observed_dns(host, port, *args, **kwargs):
            if host in ("cog.go.ke", b"cog.go.ke"):
                attempts.append(host)
                if failure == "dns":
                    raise socket.gaierror(socket.EAI_AGAIN, "owned sustained DNS outage")
            return dns(host, port, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", observed_dns)
        trust = ssl.create_default_context() if failure == "tls" else peer["trust"]
        client = SeedingHttpClient(configured, client=httpx.Client(verify=trust, trust_env=False))
        monkeypatch.setattr(domain, "create_http_client", lambda _: client)
        result = domain.run(db_session, configured, DomainRunContext(None, False))
        db_session.commit()
        assert len(attempts) == (1 if failure == "tls" else configured.max_retries)
        assert len(peer["seen"]) == (configured.max_retries if failure == "interruption" else 0)
    assert result.errors and result.items_processed == result.items_updated == 0
    assert {name: row.meta for name, row in counties.items()} == before
    assert db_session.query(SourceDocument).count() == 0
    status = result.metadata["source_status"]
    assert status["state"] == "unavailable" and status["fixture_used"] is False
    assert status["stored_governors_retained"] == status["dated_stored_governors"] == 47
    assert status["newest_age_seconds"] >= 10 * 86400
