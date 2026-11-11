"""The publisher feed may use UTF-16. XML declarations cannot grant authority."""
import pytest

from seeding import native_report_authority as authority
from seeding import oag_report_catalogue as catalogue


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
@pytest.mark.parametrize("doctype", [False, True])
def test_oag_catalogue_rejects_dtd_before_resolving_title(monkeypatch, encoding, doctype):
    feed = catalogue.catalogue_url("FY 2023/24")
    url = "https://www.oagkenya.go.ke/owned-fixture.pdf"
    title = "AUDITOR-GENERAL'S REPORT ON COUNTY GOVERNMENTS - COUNTY EXECUTIVES 2023/2024"
    dtd = f'<!DOCTYPE rss [<!ENTITY doc_title "{title}">]>' if doctype else ""
    entry_title = "&doc_title;" if doctype else title
    xml = f"""<?xml version="1.0"?>{dtd}
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel><title>2023-2024 County Government Audit Reports - Office of the Auditor-General</title>
<atom:link href="{feed}" rel="self" type="application/rss+xml"/>
<item><title>{entry_title}</title><link>{url}</link>
<pubDate>Sun, 01 Nov 2026 00:00:00 +0000</pubDate>
<guid isPermaLink="false">https://www.oagkenya.go.ke/?post_type=dlp_document&amp;p=1</guid></item>
</channel></rss>"""
    monkeypatch.setattr(authority, "retained_body", lambda *args: xml.encode(encoding))
    monkeypatch.setattr(authority, "_capture", lambda receipt, **kw: kw["catalogue"])
    cover = (
        "AUDITOR-GENERAL'S REPORT ON COUNTY GOVERNMENTS FOR THE YEAR "
        "2023/2024 VOLUME 1 COUNTY EXECUTIVES"
    )
    result, reason = catalogue.capture_catalogue_report(
        {"request_url": url, "digest": "0" * 64},
        {"request_url": feed, "response_url": feed},
        [(1, cover)],
    )
    if doctype:
        assert result is None and reason == "native_report_date_or_scope_unavailable"
    else:
        assert reason is None and result["title"] == title
