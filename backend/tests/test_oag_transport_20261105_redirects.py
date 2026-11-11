"""Regression for #914/r4485289328 at real HTTP/TLS and PostgreSQL seams."""
import hashlib
from pathlib import Path

import httpx
import pytest

from oag_transport_20261105_loopback import official_peer
from seeding.http_client import PdfDownloadError, SeedingHttpClient
from services.receipt_store import LocalReceiptStore
from test_oag_acquisition_origin import BODY, URL, ensure, receipt_rows, setup_source
from test_transport_recovery_contract import settings


@pytest.fixture(autouse=True)
def _no_outbound_network():
    # Replaces the inherited hostname guard for the controlled-DNS fixture.
    # official_peer refuses every other DNS name; the execution namespace has
    # no external route. No network marker excludes these from ordinary tests.
    yield


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("raise_status", [True, False])
@pytest.mark.parametrize("target", ["cross_origin", "internal", "same_origin"])
def test_pdf_redirect_never_contacts_target_or_retains_body(tmp_path, monkeypatch, status, raise_status, target):
    endpoints = {}
    def respond(handler):
        if handler.path == "/allowed.pdf":
            handler.send_response(status)
            handler.send_header("Location", {
                "cross_origin": "https://cross-origin.invalid/unsafe",
                "internal": endpoints["internal_url"],
                "same_origin": "/unsafe",
            }[target])
            handler.end_headers()
        else:
            handler.send_response(200)
            handler.end_headers()
            handler.wfile.write(BODY)

    store = LocalReceiptStore(tmp_path / "retained")
    destination = tmp_path / "last-good.pdf"
    destination.write_bytes(b"previous qualified edition")
    with official_peer(tmp_path, monkeypatch, respond=respond) as peer:
        endpoints.update(peer)
        raw = httpx.Client(verify=peer["trust"], trust_env=False, follow_redirects=True)
        with SeedingHttpClient(settings(tmp_path), client=raw, receipt_store=store) as client:
            with pytest.raises((PdfDownloadError, httpx.HTTPStatusError)):
                client.download_to_file(peer["url"] + "/allowed.pdf", destination,
                    max_seconds=2, max_bytes=4096, raise_for_status=raise_status)
            assert peer["foreign"] == [], "Refusal happened after the redirected HTTP request"
            assert client.download_receipt(peer["url"] + "/allowed.pdf") is None
        assert peer["seen"] == ["/allowed.pdf"]
        assert peer["foreign"] == []
        assert peer["lookups"] == ["www.oagkenya.go.ke"], "Redirect target was resolved before refusal"
    assert destination.read_bytes() == b"previous qualified edition"
    assert not list(tmp_path.glob("last-good.pdf.*.part"))
    assert not list((tmp_path / "retained").rglob("*"))


def test_direct_official_pdf_still_retains_identical_body_and_receipt(tmp_path, monkeypatch):
    def respond(handler):
        handler.send_response(200)
        handler.send_header("Content-Type", "application/pdf")
        handler.send_header("Content-Length", str(len(BODY)))
        handler.end_headers()
        handler.wfile.write(BODY)

    store = LocalReceiptStore(tmp_path / "retained")
    with official_peer(tmp_path, monkeypatch, respond=respond) as peer:
        url = peer["url"] + "/allowed.pdf"
        with SeedingHttpClient(settings(tmp_path), receipt_store=store,
                client=httpx.Client(verify=peer["trust"], trust_env=False, follow_redirects=True)) as client:
            assert client.download_to_file(url, tmp_path / "out.pdf", max_seconds=2, max_bytes=4096) == len(BODY)
            receipt = client.download_receipt(url)
        assert peer["seen"] == ["/allowed.pdf"] and peer["foreign"] == []
    assert (tmp_path / "out.pdf").read_bytes() == BODY
    assert receipt["request_url"] == receipt["response_url"] == url
    assert receipt["digest"] == hashlib.sha256(BODY).hexdigest()
    assert store.read(receipt["storage_key"]) == BODY


@pytest.mark.parametrize("target", ["cross_origin", "same_origin"])
def test_origin_refuses_redirect_before_target_dns_http_or_retention(db_session, tmp_path, monkeypatch, target):
    from seeding.domains.audits.acquisition import AuditOriginUnavailable

    configured, store, _, source, context, _ = setup_source(db_session, tmp_path)
    before_meta = dict(source.meta)
    scratch = tmp_path / "origin-scratch"
    scratch.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch))

    def respond(handler):
        if handler.path == httpx.URL(URL).path:
            handler.send_response(302)
            handler.send_header("Location", "https://cross-origin.invalid/unsafe" if target == "cross_origin" else "/unsafe")
            handler.end_headers()
        else:
            handler.send_response(200)
            handler.end_headers()
            handler.wfile.write(BODY)

    with official_peer(tmp_path, monkeypatch, respond=respond) as peer:
        with SeedingHttpClient(configured, receipt_store=store,
                client=httpx.Client(verify=peer["trust"], trust_env=False, follow_redirects=True)) as client:
            with pytest.raises(AuditOriginUnavailable):
                ensure(db_session, context, source, client, configured)
            assert peer["foreign"] == [], "Final origin refusal happened after a foreign HTTP request"
            assert client.download_receipt(URL) is None
        assert peer["seen"] == [httpx.URL(URL).path]
        assert peer["foreign"] == [], "Final origin refusal happened after a foreign HTTP request"
        assert peer["lookups"] == ["www.oagkenya.go.ke"]
    assert receipt_rows(db_session) == []
    assert source.meta == before_meta
    assert Path(source.file_path).read_bytes() == BODY
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize("path", ["wp_discovery", "listing_observation", "legacy_pdf"])
def test_other_audit_body_paths_refuse_foreign_redirect_before_contact(tmp_path, monkeypatch, path):
    from seeding.domains.audits import fetcher, observation

    def respond(handler):
        handler.send_response(302)
        handler.send_header("Location", "https://cross-origin.invalid/unsafe")
        handler.end_headers()

    store = LocalReceiptStore(tmp_path / "retained")
    with official_peer(tmp_path, monkeypatch, respond=respond) as peer:
        with SeedingHttpClient(settings(tmp_path), receipt_store=store,
                client=httpx.Client(verify=peer["trust"], trust_env=False, follow_redirects=True)) as client:
            if path == "wp_discovery":
                assert fetcher._discover_audit_pdfs_via_wp_api(client) == []
            elif path == "listing_observation":
                discovery, _ = observation.observe_listing(client)
                assert discovery.errors
            else:
                with pytest.raises(Exception):
                    fetcher._download_and_parse_audit_pdf(client, peer["url"] + "/audit.pdf", settings(tmp_path))
            assert peer["foreign"] == [], "An owned audit acquisition path fetched the foreign body"
            assert "cross-origin.invalid" not in peer["lookups"]
    assert not list((tmp_path / "retained").rglob("*"))


def test_county_discovery_in_real_domain_refuses_foreign_redirect(db_session, tmp_path, monkeypatch):
    from seeding.domains import audits
    from seeding.extractors.reconciliation import IncompleteExtraction

    configured, store, _, _, context, _ = setup_source(db_session, tmp_path)

    def respond(handler):
        handler.send_response(302)
        handler.send_header("Location", "https://cross-origin.invalid/unsafe")
        handler.end_headers()

    def held_parser(*args, **kwargs):
        raise IncompleteExtraction("Owned content hold after transport observation")

    monkeypatch.setattr("seeding.extractors.get_parser", lambda _: held_parser)
    monkeypatch.setattr(audits.fetcher, "_discover_audit_pdfs_via_wp_api", lambda *a, **k: [])
    with official_peer(tmp_path, monkeypatch, respond=respond) as peer:
        def client_factory(_):
            return SeedingHttpClient(configured, receipt_store=store,
                client=httpx.Client(verify=peer["trust"], trust_env=False, follow_redirects=True))
        monkeypatch.setattr(audits, "create_http_client", client_factory)
        result = audits.run(db_session, configured, context)
        assert result.errors
        assert peer["foreign"] == [], "County discovery bypassed the confined OAG body boundary"
        assert "cross-origin.invalid" not in peer["lookups"]
    assert receipt_rows(db_session) == []


@pytest.mark.parametrize("credential", ["authorization", "cookie", "auth_flow", "redirect_cookie"])
def test_approved_alias_redirect_cannot_forward_client_credentials(tmp_path, monkeypatch, credential):
    from seeding.domains.audits.transport import get_official_body

    observed = []

    def respond(handler):
        observed.append(dict(host=handler.headers["Host"], authorization=handler.headers.get("Authorization"),
            cookie=handler.headers.get("Cookie")))
        if handler.path == "/start":
            handler.send_response(302)
            handler.send_header("Location", "https://oagkenya.go.ke/alias")
            if credential == "redirect_cookie":
                handler.send_header("Set-Cookie", "session=owned-toy; Domain=.oagkenya.go.ke; Path=/; Secure")
            handler.end_headers()
        else:
            handler.send_response(200)
            handler.end_headers()
            handler.wfile.write(b"complete")

    store = LocalReceiptStore(tmp_path / "retained")
    headers = ({"Authorization": "Bearer owned-toy"} if credential == "authorization" else
               {"Cookie": "session=owned-toy"} if credential == "cookie" else {})
    auth = httpx.BasicAuth("owned-user", "owned-password") if credential == "auth_flow" else None
    with official_peer(tmp_path, monkeypatch, aliases=("oagkenya.go.ke",), respond=respond) as peer:
        with SeedingHttpClient(settings(tmp_path), receipt_store=store,
                client=httpx.Client(verify=peer["trust"], trust_env=False, follow_redirects=True,
                    headers=headers, auth=auth)) as client:
            with pytest.raises(ValueError, match="Credential-bearing"):
                get_official_body(client, peer["url"] + "/start")
        assert len(observed) == 1 and observed[0]["host"] == "www.oagkenya.go.ke"
        assert peer["seen"] == ["/start"]
        assert peer["lookups"] == ["www.oagkenya.go.ke"], "Alias target resolved before credential refusal"
        assert peer["foreign"] == []
    assert not list((tmp_path / "retained").rglob("*"))


@pytest.mark.parametrize("cross_host", [False, True])
def test_bounded_redirect_keeps_same_origin_credentials_and_anonymous_alias_controls(tmp_path, monkeypatch, cross_host):
    from seeding.domains.audits.transport import get_official_body

    observed = []

    def respond(handler):
        observed.append((handler.headers["Host"], handler.headers.get("Authorization")))
        if handler.path == "/start":
            handler.send_response(302)
            handler.send_header("Location", "https://oagkenya.go.ke/alias" if cross_host else "/alias")
            handler.end_headers()
        else:
            handler.send_response(200)
            handler.end_headers()
            handler.wfile.write(b"complete")

    headers = {} if cross_host else {"Authorization": "Bearer same-origin-owned-toy"}
    with official_peer(tmp_path, monkeypatch, aliases=("oagkenya.go.ke",), respond=respond) as peer:
        with SeedingHttpClient(settings(tmp_path),
                client=httpx.Client(verify=peer["trust"], trust_env=False, headers=headers)) as client:
            assert get_official_body(client, peer["url"] + "/start").content == b"complete"
        assert len(observed) == 2
        assert observed[-1][1] == (None if cross_host else "Bearer same-origin-owned-toy")
