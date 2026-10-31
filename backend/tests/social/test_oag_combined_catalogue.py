"""Owned PDF covers paired to the retained genuine OAG feed shape.

These small PDFs are synthetic. Full genuine PDFs have separate acceptance
receipts; no test downloads a source or enables generation/publishing.
"""
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

import httpx
import pytest

from seeding.native_report_authority import capture_pdf_report
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response
from test_audit_report_editions import pdf

FEED = 'https://www.oagkenya.go.ke/document-category/2023-2024-county-government-audit-reports/feed/'
EXECUTIVE = 'https://www.oagkenya.go.ke/wp-content/uploads/2025/02/GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf'
ASSEMBLY = 'https://www.oagkenya.go.ke/wp-content/uploads/2025/02/GREEN-BOOK-ASSEMBLIES-2024-FINAL-01-April-2025-KLB.pdf'
FIXTURES = Path(__file__).parents[1] / 'fixtures/oag'


def input_pair(tmp_path, *, kind='executives', change=None, cover=None, cover_note=None):
    url = EXECUTIVE if kind == 'executives' else ASSEMBLY
    root = ET.fromstring((FIXTURES / 'county-audit-catalogue-2023-24.xml').read_bytes())
    item = next(item for item in root.findall('channel/item') if url.rsplit('/', 1)[-1] in item.findtext('link'))
    if change:
        change(root, item)
    rss = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    title = cover or ("AUDITOR-GENERAL'S REPORT ON THE COUNTY GOVERNMENTS FOR THE YEAR 2023-2024 "
                      + ('VOLUME 1 - COUNTY EXECUTIVES' if kind == 'executives' else 'VOLUME II: COUNTY ASSEMBLIES'))
    # The existing helper's absent-day line is an actual title-page qualifier
    # here; remove it so this synthetic page has the genuine complete heading.
    body = pdf(title, '').replace(b'Signed by the Auditor-General', b' ' * len(b'Signed by the Auditor-General'))
    if cover_note is not None:
        from test_native_publisher_metadata import pdf_document
        body = pdf_document([title, cover_note])
    path = tmp_path / 'volume.pdf'; path.write_bytes(body)
    store = LocalReceiptStore(tmp_path / 'receipts')
    def receipt(content, request_url, content_type, source_kind):
        return capture_response(httpx.Response(200, content=content, headers={'content-type': content_type},
            request=httpx.Request('GET', request_url)), store, source_kind=source_kind)
    return path, receipt(body, url, 'application/pdf', 'pdf'), receipt(rss, FEED, 'application/rss+xml', 'rss')


@pytest.mark.parametrize('kind', ['executives', 'assemblies'])
def test_exact_combined_cover_and_dated_entry_qualify_availability_only(tmp_path, kind):
    path, source, feed = input_pair(tmp_path, kind=kind)
    authority, reason = capture_pdf_report(path, source, domain='audits', publisher_receipt=feed)
    assert reason is None and authority is not None
    value = authority.value
    assert value['published_on'] is None
    assert value['evidence_kind'] == 'publisher_catalogue' and value['catalogued_on'] == '2025-02-21'
    assert value['period'] == 'FY 2023/24' and value['catalogue_authority']['institution'] == kind
    assert value['entity'] == 'County Governments of Kenya: County ' + kind.title()


def change_feed(case):
    def change(root, item):
        channel = root.find('channel')
        if case == 'duplicate_item': channel.append(deepcopy(item))
        elif case == 'duplicate_day': item.append(deepcopy(item.find('pubDate')))
        elif case == 'missing_day': item.remove(item.find('pubDate'))
        elif case == 'short_year': item.find('pubDate').text = 'Fri, 21 Feb 25 05:51:28 +0000'
        elif case == 'wrong_weekday': item.find('pubDate').text = 'Mon, 21 Feb 2025 05:51:28 +0000'
        elif case == 'missing_offset': item.find('pubDate').text = 'Fri, 21 Feb 2025 05:51:28'
        elif case == 'future_day': item.find('pubDate').text = 'Thu, 21 Feb 2030 05:51:28 +0000'
        elif case == 'wrong_link': item.find('link').text = '/unrelated.pdf'
        elif case == 'wrong_institution': item.find('title').text = item.findtext('title').replace('Executives', 'Assemblies')
        elif case == 'wrong_period': item.find('title').text = item.findtext('title').replace('2023/2024', '2022/2023')
        elif case == 'qualified_title': item.find('title').text += ' (Draft)'
        elif case == 'wrong_guid': item.find('guid').text = 'https://unrelated.invalid/?post_type=dlp_document&p=20311'
        elif case == 'wrong_channel': channel.find('title').text = 'Office of the Auditor-General'
        elif case == 'wrong_self': channel.find('{http://www.w3.org/2005/Atom}link').set('href', FEED.replace('2023', '2022'))
        elif case == 'no_items':
            for entry in channel.findall('item'): channel.remove(entry)
        else: raise AssertionError('Unknown hostile fixture')
    return change


@pytest.mark.parametrize('case', ['duplicate_item', 'duplicate_day', 'missing_day', 'short_year',
    'wrong_weekday', 'missing_offset', 'future_day', 'wrong_link', 'wrong_institution', 'wrong_period',
    'qualified_title', 'wrong_guid', 'wrong_channel', 'wrong_self', 'no_items'])
def test_ambiguous_or_unbound_catalogue_cannot_supply_authority(tmp_path, case):
    path, source, feed = input_pair(tmp_path, change=change_feed(case))
    authority, reason = capture_pdf_report(path, source, domain='audits', publisher_receipt=feed)
    assert authority is None and reason == 'native_report_date_or_scope_unavailable'


@pytest.mark.parametrize('cover', [
    "AUDITOR-GENERAL'S REPORT ON THE COUNTY GOVERNMENTS FOR THE YEAR 2023-2024 VOLUME 2 - COUNTY EXECUTIVES",
    "AUDITOR-GENERAL'S REPORT ON THE COUNTY GOVERNMENTS FOR THE YEAR 2024-2025 VOLUME 1 - COUNTY EXECUTIVES",
    "AUDITOR-GENERAL'S REPORT ON THE COUNTY GOVERNMENTS FOR THE YEAR 2023-2024 VOLUME 1 - COUNTY CORPORATIONS",
    "AUDITOR-GENERAL'S REPORT ON THE COUNTY GOVERNMENTS FOR THE YEAR 2023-2024 VOLUME 1 - COUNTY EXECUTIVES FIRST QUARTER",
])
def test_independent_cover_scope_is_not_inferred_from_listing(tmp_path, cover):
    path, source, feed = input_pair(tmp_path, cover=cover)
    assert capture_pdf_report(path, source, domain='audits', publisher_receipt=feed)[0] is None


@pytest.mark.parametrize('note', ['COUNTY ASSEMBLIES - 2023-2024', 'COUNTY EXECUTIVES: 2022/2023'])
def test_punctuation_cannot_hide_conflicting_cover_scope(tmp_path, note):
    path, source, feed = input_pair(tmp_path, cover_note=note)
    authority, reason = capture_pdf_report(path, source, domain='audits', publisher_receipt=feed)
    assert authority is None and reason == 'native_report_date_or_scope_unavailable'


@pytest.mark.parametrize('kind', ['executives', 'assemblies'])
@pytest.mark.parametrize('broken', [None, 'title_volume', 'title_period', 'title_kind', 'qualified_title'])
def test_reviewed_green_book_catalogue_spelling_keeps_independent_scope(tmp_path, kind, broken):
    volume = 1 if kind == 'executives' else 2
    cover = ("REPORT OF THE AUDITOR-GENERAL ON THE COUNTY GOVERNMENTS FOR THE YEAR 2022/2023 "
             + f'VOLUME {volume} - COUNTY {kind.upper()}')
    path, _, _ = input_pair(tmp_path, kind=kind, cover=cover)
    root = ET.fromstring((FIXTURES / 'county-audit-catalogue-2022-23.xml').read_bytes())
    item = next(i for i in root.findall('channel/item') if kind.upper() in i.findtext('link'))
    url = 'https://www.oagkenya.go.ke' + item.findtext('link').split('#')[0]
    if broken == 'title_volume': item.find('title').text = item.findtext('title').replace(str(volume), str(3-volume), 1)
    if broken == 'title_period': item.find('title').text = item.findtext('title').replace('2022-2023', '2023-2024')
    if broken == 'title_kind': item.find('title').text = item.findtext('title').replace(kind.title(), 'Assemblies' if kind == 'executives' else 'Executives')
    if broken == 'qualified_title': item.find('title').text += ' Draft'
    feed_url = FEED.replace('2023-2024', '2022-2023')
    store = LocalReceiptStore(tmp_path / 'green-book-receipts')
    def capture(body, address, mime):
        return capture_response(httpx.Response(200, content=body, headers={'content-type': mime},
            request=httpx.Request('GET', address)), store, source_kind='pdf' if mime == 'application/pdf' else 'rss')
    source = capture(path.read_bytes(), url, 'application/pdf')
    feed = capture(ET.tostring(root), feed_url, 'application/rss+xml')
    authority, reason = capture_pdf_report(path, source, domain='audits', publisher_receipt=feed)
    if broken:
        assert authority is None and reason
    else:
        assert reason is None and authority is not None
        assert authority.value['published_on'] is None and authority.value['catalogued_on'] == '2024-04-05'
        assert authority.value['period'] == 'FY 2022/23' and authority.value['catalogue_authority']['institution'] == kind


@pytest.mark.parametrize('which', ['pdf', 'rss'])
def test_serialized_acquisition_is_not_authority(tmp_path, which):
    path, source, feed = input_pair(tmp_path)
    if which == 'pdf': source = dict(source)
    else: feed = dict(feed)
    assert capture_pdf_report(path, source, domain='audits', publisher_receipt=feed)[0] is None


def test_caption_keeps_catalogue_day_separate_from_unknown_publication(tmp_path):
    from social.generation.contracts import SourceObservation, NativeFinancialEvidence
    from social.generation.social_copy import render_social
    from seeding.native_report_authority import DOMAINS
    path, source, feed = input_pair(tmp_path)
    authority, _ = capture_pdf_report(path, source, domain='audits', publisher_receipt=feed)
    value = authority.value
    report = dict(native_domain='audits', institution='executives', scope_key=value['scope_key'],
        entity_id=1, source_record_id=1, authority_fingerprint='a' * 64, entity=value['entity'],
        period=value['period'], period_start=value['period_start'], period_end=value['period_end'],
        source_document_id=1, document_url=value['document_url'], document_checksum=value['document_checksum'],
        publisher=DOMAINS['audits'][2], published_on=None, retrieved_at=source['acquired_at'],
        verified_at=source['byte_check']['checked_at'], canonical_url='https://www.auditgava.com/audits',
        locator=value['locator'], publication_extraction_id=1, qualification_extraction_id=1,
        evidence_kind='publisher_catalogue', catalogued_on=value['catalogued_on'], catalogue_url=FEED)
    observation = SourceObservation.model_validate(dict(schema_version=1, source_type='oag',
        source_key='oag:native:audits:1:' + value['scope_key'], evidence_version=1, ingestion_id='1',
        category='dataset_availability', title='OAG report availability', committed=True, fixture=False,
        quarantined=False, publishable=True, correction_pending=False, facts=[], report=report))
    copy = render_social(observation, version='catalogue-availability-v4')
    assert 'Catalogue entry dated 21 February 2025' in copy
    assert 'an audit report' in copy
    assert 'publication date is not stated' in copy and 'Human review is required' in copy
    assert 'Published by' not in copy and 'AuditGava' in copy
    with pytest.raises(ValueError): NativeFinancialEvidence.model_validate({'native_domain': 'audits'})
    from social.automation.service import source_scope
    from social.service import SocialError
    with pytest.raises(SocialError, match='CATALOGUE_HUMAN_REVIEW_REQUIRED'):
        source_scope(observation)


def test_cover_extraction_releases_layout_before_next_page(tmp_path, monkeypatch):
    from pdfplumber.page import Page
    from test_native_publisher_metadata import pdf_document
    path, source, feed = input_pair(tmp_path)
    body = pdf_document(["AUDITOR-GENERAL'S REPORT ON THE COUNTY GOVERNMENTS FOR THE YEAR 2023-2024 VOLUME 1 - COUNTY EXECUTIVES", 'VISION', 'MISSION'])
    path.write_bytes(body)
    source = capture_response(httpx.Response(200, content=body, headers={'content-type':'application/pdf'},
        request=httpx.Request('GET', EXECUTIVE)), LocalReceiptStore(tmp_path/'layouts'), source_kind='pdf')
    held = set()
    extract, close = Page.extract_text, Page.close
    def checked_extract(page, **kwargs):
        assert not held, 'Previous cover layout remains resident'
        held.add(page.page_number)
        return extract(page, **kwargs)
    def checked_close(page):
        held.discard(page.page_number)
        close(page)
    monkeypatch.setattr(Page, 'extract_text', checked_extract)
    monkeypatch.setattr(Page, 'close', checked_close)
    authority, reason = capture_pdf_report(path, source, domain='audits', publisher_receipt=feed)
    assert authority is not None and reason is None and not held


def test_cover_reader_never_traverses_a_fourth_page(tmp_path, monkeypatch):
    from pdfminer.pdfpage import PDFPage
    from test_native_publisher_metadata import pdf_document
    path, source, feed = input_pair(tmp_path)
    body = pdf_document(["AUDITOR-GENERAL'S REPORT ON THE COUNTY GOVERNMENTS FOR THE YEAR 2023-2024 VOLUME 1 - COUNTY EXECUTIVES", 'VISION', 'MISSION', 'BODY'])
    path.write_bytes(body)
    source = capture_response(httpx.Response(200, content=body, headers={'content-type':'application/pdf'},
        request=httpx.Request('GET', EXECUTIVE)), LocalReceiptStore(tmp_path/'page-budget'), source_kind='pdf')
    create = PDFPage.create_pages
    def bounded(document):
        for number, page in enumerate(create(document), 1):
            assert number <= 3, 'Cover reader traversed beyond its three-page budget'
            yield page
    monkeypatch.setattr(PDFPage, 'create_pages', bounded)
    authority, reason = capture_pdf_report(path, source, domain='audits', publisher_receipt=feed)
    assert authority is not None and reason is None
