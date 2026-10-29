"""Catalogue availability is distinct from a publisher's publication day."""
from copy import deepcopy
from datetime import datetime, timezone
import httpx
import pytest
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response

URL = 'https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026'
CATALOGUE = 'https://www.kra.go.ke/component/search/?searchphrase=all&searchword=KRA+performance'
TITLE = 'Key Sectors Push Revenue to KES 2.8 Trillion as KRA Records Strongest Growth in Recent Years'
WRAPPER = f'<html><head><title>Annual Revenue Performance - FY 2025/2026 - KRA</title></head><body><h2>{TITLE}</h2></body></html>'.encode()
ENTRY = f'''<div class="content-wrapper"><p class="title"><a href="/annual-revenue-performance-fy-2025-2026">{TITLE}</a></p>
<p class="item-section"><span class="small item-cat">(KRA Revenue Performance)</span><span class="result-created"></span>08/07/2026</p></div>'''.encode()


def acquired(tmp_path, body, url):
    return capture_response(httpx.Response(200, content=body, headers={'content-type':'text/html'},
        request=httpx.Request('GET', url)), LocalReceiptStore(tmp_path))


def capture(tmp_path, wrapper=WRAPPER, entry=ENTRY, *, fiscal_year='FY 2025/26', url=URL, catalogue_url=CATALOGUE):
    from seeding.kra_report_catalogue import capture_catalogue_report
    return capture_catalogue_report(acquired(tmp_path, wrapper, url), acquired(tmp_path, entry, catalogue_url), fiscal_year=fiscal_year)


def test_catalogue_day_is_never_a_publication_day(tmp_path):
    authority, reason = capture(tmp_path)
    assert authority is not None, reason
    value = authority.value
    assert value['published_on'] is None
    assert value['catalogued_on'] == '2026-07-08'
    assert value['evidence_kind'] == 'publisher_catalogue'
    assert value['catalogue_url'] == CATALOGUE
    assert value['period'] == 'FY 2025/26'
    assert 'publication_authority' not in value
    assert authority.publisher_receipt['observations'][0]['title'] == TITLE


@pytest.mark.parametrize('entry', [b'', ENTRY + ENTRY,
    ENTRY.replace(b'08/07/2026', b'07/2026'), ENTRY.replace(b'08/07/2026', b'31/02/2026'),
    ENTRY.replace(b'08/07/2026', b'08/07/2099'), ENTRY.replace(b'08/07/2026', b'08/06/2026'),
    ENTRY.replace(b'(KRA Revenue Performance)', b'(Downloads)'),
    ENTRY.replace(b'FY 2025', b'FY 2024').replace(b'2025-2026', b'2024-2025'),
    ENTRY.replace(b'Key Sectors', b'Monthly targets'),
    ENTRY.replace(b'href="', b'href="https://evil.invalid" href="'),
    ENTRY.replace(b'</span>08', b'</span>retrieved 08'),
    ENTRY.replace(b'2025-2026"', b'2025-2026?other=1"'),
])
def test_wrong_ambiguous_or_incomplete_catalogue_refuses(tmp_path, entry):
    assert capture(tmp_path, entry=entry)[0] is None


@pytest.mark.parametrize('changes', [dict(fiscal_year='FY 2024/25'), dict(wrapper=b''),
    dict(wrapper=WRAPPER.replace(b'2025/2026', b'2025/2027')),
    dict(wrapper=WRAPPER + f'<h2>{TITLE}</h2>'.encode()),
    dict(url='https://www.kra.go.ke.evil.invalid/annual-revenue-performance-fy-2025-2026'),
    dict(catalogue_url=CATALOGUE+'&start=10'),
])
def test_wrapper_and_parsed_annual_scope_must_match(tmp_path, changes):
    assert capture(tmp_path, **changes)[0] is None


def test_contradictory_machine_date_in_catalogue_section_refuses(tmp_path):
    changed = ENTRY.replace(b'08/07/2026',b'<time datetime="2099-01-01">08/07/2026</time>')
    assert capture(tmp_path,entry=changed)[0] is None


def test_copied_or_changed_transport_refuses(tmp_path):
    from seeding.kra_report_catalogue import capture_catalogue_report
    wrapper, entry = acquired(tmp_path, WRAPPER, URL), acquired(tmp_path, ENTRY, CATALOGUE)
    assert capture_catalogue_report(wrapper, dict(entry), fiscal_year='FY 2025/26')[0] is None
    entry['status'] = True
    assert capture_catalogue_report(wrapper, entry, fiscal_year='FY 2025/26')[0] is None


def test_bounded_transport_and_scratch_cleanup(tmp_path):
    from pathlib import Path
    from seeding.kra_report_catalogue import fetch_catalogue_receipt, MAX_METADATA_BYTES
    seen = []
    class Client:
        def download_to_file(self, url, path, **kw):
            assert url == CATALOGUE and kw == dict(max_seconds=20, max_bytes=MAX_METADATA_BYTES)
            seen.append(Path(path)); Path(path).write_bytes(ENTRY)
        def download_receipt(self, url): return 'receipt'
    assert fetch_catalogue_receipt(Client()) == 'receipt'
    assert len(seen) == 1 and not seen[0].exists() and not seen[0].parent.exists()


def report(authority):
    value = authority.value
    return dict(native_domain='revenue_by_source', scope_key=value['scope_key'], entity_id=1,
        source_record_id=11, authority_fingerprint='a'*64, entity=value['entity'], period=value['period'],
        period_start=value['period_start'], period_end=value['period_end'], source_document_id=2,
        document_url=URL, document_checksum=value['document_checksum'], publisher='Kenya Revenue Authority',
        published_on=None, catalogued_on=value['catalogued_on'], catalogue_url=CATALOGUE,
        evidence_kind='publisher_catalogue', retrieved_at=datetime.now(timezone.utc).isoformat(),
        verified_at=datetime.now(timezone.utc).isoformat(), canonical_url='https://www.auditgava.com/budget',
        locator=value['locator'], publication_extraction_id=11, qualification_extraction_id=11)


def observation(value):
    return dict(source_type='kra', source_key='kra:native:revenue_by_source:1:annual-revenue',
        evidence_version=3, ingestion_id='3', category='dataset_availability', title='KRA report availability',
        committed=True, fixture=False, quarantined=False, publishable=True, report=value)


def test_typed_catalogue_and_copy_preserve_unknown_day(tmp_path):
    from social.generation.contracts import SourceObservation, NativeReportEvidence
    from social.generation.service import render, generator_metadata, report_release_state, valid_report_release_state
    value = report(capture(tmp_path)[0]); parsed = SourceObservation.model_validate(observation(value))
    text = render(parsed)
    assert 'Catalogue entry dated 8 July 2026.' in text
    assert 'The report’s publication date is not stated. Human review is required.' in text
    assert '2.8' not in text and 'Publisher publication date' not in text
    assert generator_metadata(parsed)['template_version'] == 'catalogue-availability-v2'
    state = report_release_state(parsed)
    assert state['catalogued_on'] == '2026-07-08' and 'published_on' not in state
    assert valid_report_release_state(state)
    with pytest.raises(ValueError): NativeReportEvidence.model_validate(value)
    for key, bad in [('published_on','2026-07-08'), ('catalogued_on','2099-01-01'),
                     ('native_domain','national_budget'), ('evidence_kind','publication'),
                     ('catalogue_url','https://evil.invalid'), ('period','FY 2024/25')]:
        with pytest.raises(ValueError): SourceObservation.model_validate(observation({**value,key:bad}))


def test_catalogue_cursor_state_refuses_day_before_reporting_period_end():
    from social.generation.service import valid_report_release_state
    assert not valid_report_release_state(dict(release_hash='a'*64,evidence_kind='publisher_catalogue',catalogued_on='2020-01-01',
        period_start='2025-07-01',period_end='2026-06-30'))


def test_wrapper_keeps_existing_two_mib_budget_separate_from_catalogue(tmp_path):
    padded=WRAPPER+b'<!--'+b'x'*(600*1024)+b'-->'
    assert capture(tmp_path,wrapper=padded)[0] is not None
    assert capture(tmp_path,wrapper=WRAPPER+b'x'*(2*1024*1024))[0] is None
    assert capture(tmp_path,entry=ENTRY+b'x'*(512*1024))[0] is None
