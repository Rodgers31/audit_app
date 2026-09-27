"""A pending-bills attempt must preserve CBIRR bytes banked by another domain."""
from types import SimpleNamespace

import pytest
from seeding import cob_cbirr, pdf_download
from seeding.domains.pending_bills import fetcher
from seeding.http_client import PdfDownloadError
from tests.test_cbirr_download import settings, EDITION_URL
from tests.test_pdf_resume import WHOLE, _FakeClient, _FakeStream, _client_wrapper


def prepare(monkeypatch, settings, fake):
    client = _client_wrapper(fake)
    monkeypatch.setattr(client, "get", lambda *a, **kw: SimpleNamespace(text="listing"))
    monkeypatch.setattr(fetcher, "year_end_cbirr_links", lambda text: [EDITION_URL])
    monkeypatch.setattr(pdf_download, "probe_fingerprint", lambda *a, **kw: "Final 5")
    cob_cbirr._FINGERPRINTS.clear()
    # Stop at the parser boundary: assert the actual cached bytes presented to it.
    from seeding import pdf_parsers

    seen = []

    class Parser:
        def __init__(self, path):
            seen.append(path.read_bytes())

        def parse(self):
            return []

    monkeypatch.setattr(pdf_parsers, "CbirrYearEndPayablesParser", Parser)
    monkeypatch.setattr(fetcher, "check_county_payables_entries", lambda *a: None)
    monkeypatch.setattr(fetcher, "county_payables_payload", lambda *a: {"tested": True})
    settings.live_pdf_fetch_enabled = True
    settings.parse_cache_enabled = False
    return client, seen


def test_pending_bills_resumes_other_domains_interrupted_download(
    settings, monkeypatch
):
    interrupted = _FakeClient(lambda rng: _FakeStream(WHOLE, fail_after=200))
    client, _ = prepare(monkeypatch, settings, interrupted)
    with pytest.raises(PdfDownloadError):
        cob_cbirr.download_cbirr(client, EDITION_URL, settings)
    part = pdf_download._part_path(settings.cache_path / "pdfs", EDITION_URL)
    banked = part.stat().st_size
    assert banked > 0

    def resume(rng):
        return _FakeStream(WHOLE[banked:] if rng else WHOLE, status=206 if rng else 200)

    downloader = _FakeClient(resume)
    client, seen = prepare(monkeypatch, settings, downloader)
    assert fetcher.fetch_county_payables_payload(client, settings) == {"tested": True}
    assert downloader.ranges == [f"bytes={banked}-"]
    assert seen == [WHOLE]


def test_pending_bills_reissue_uses_new_bytes(settings, monkeypatch):
    client, _ = prepare(
        monkeypatch, settings, _FakeClient(lambda rng: _FakeStream(WHOLE))
    )
    cob_cbirr.download_cbirr(client, EDITION_URL, settings)
    replacement = WHOLE.replace(b"x", b"y")
    downloader = _FakeClient(lambda rng: _FakeStream(replacement))
    client, seen = prepare(monkeypatch, settings, downloader)
    monkeypatch.setattr(pdf_download, "probe_fingerprint", lambda *a, **kw: "Final 6")
    fetcher.fetch_county_payables_payload(client, settings)
    assert downloader.ranges == [None]
    assert seen == [replacement]
