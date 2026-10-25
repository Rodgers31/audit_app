"""Native publisher authority behavior; synthetic transport, no source requests."""
import httpx
from seeding.generation_capabilities import capability
from seeding.domains.revenue_by_source.fetcher import _read_release

KRA_URL='https://www.kra.go.ke/news-center/press-release/2235-result'
LEAD=b"The Kenya Revenue Authority (KRA) has surpassed the revenue target of Kshs. 10 Trillion for the Financial Year 2024/2025 after collecting Kshs. 11 Trillion."
HTML=b'''<div class="blog-content"><p>'''+LEAD+b'''</p>
<p>PAYE collection stood at Kshs. 560 Billion.</p></div>
<div class="bottom-wrapper"><p>PRESS RELEASE 10/07/2025</p></div>'''


def test_existing_cob_control():
    assert capability('counties_budget').reports is True
    class Client:
        def get(self,url,**kwargs):
            return httpx.Response(200,content=HTML,headers={'content-type':'text/html'},request=httpx.Request('GET',url))
    result=_read_release(Client(),KRA_URL,None)
    assert result.fiscal_year=='FY 2024/25'
    assert result.heads


def test_kra_release_retains_native_report_authority(tmp_path):
    from services.receipt_store import LocalReceiptStore
    class Client:
        receipt_store=LocalReceiptStore(tmp_path)
        def get(self,url,**kwargs):
            return httpx.Response(200,content=HTML,headers={'content-type':'text/html'},request=httpx.Request('GET',url))
    result=_read_release(Client(),KRA_URL,None)
    proof=getattr(result,'native_report_authority',None)
    assert proof is not None, 'Native KRA producer drops full publisher day/scope authority'
    assert proof.value['published_on']=='2025-07-10'
    assert proof.value['period']=='FY 2024/25'


def test_priority_report_adapters_are_concrete():
    for domain in ('national_budget','revenue_by_source','audits'):
        assert capability(domain).reports, f'{domain} has no committed report adapter'
    assert capability('opendata').reports is False


import pytest
from copy import deepcopy
from services.response_receipts import capture_response
from services.receipt_store import LocalReceiptStore
from seeding.native_report_authority import capture_kra_release, capture_pdf_report, NativeReportAuthority


def receipt(tmp_path,body=HTML,url=KRA_URL,ctype='text/html',status=200):
    return capture_response(httpx.Response(status,content=body,headers={'content-type':ctype},request=httpx.Request('GET',url)),LocalReceiptStore(tmp_path))


@pytest.mark.parametrize('bad',[
    b'',b'<p>PRESS RELEASE 10/07/2025</p>',
    HTML.replace(b'10/07/2025',b'07/2025'),HTML.replace(b'10/07/2025',b'31/02/2025'),
    HTML.replace(b'10/07/2025',b'10/07/2099'),HTML.replace(b'2024/2025',b'2024/2026'),
    HTML.replace(b'Financial Year',b'retrieved year'),
    HTML+ b'<div class="bottom-wrapper"><p>PRESS RELEASE 10/07/2025</p></div>',
    HTML.replace(b'2024/2025',b'2024/2025 and Financial Year 2023/2024'),
])
def test_kra_malformed_date_or_scope_never_qualifies(tmp_path,bad):
    proof,reason=capture_kra_release(receipt(tmp_path,bad))
    assert proof is None and reason=='native_report_date_or_scope_unavailable'


@pytest.mark.parametrize('url',['http://www.kra.go.ke/report','https://www.kra.go.ke.evil.invalid/report','https://user@www.kra.go.ke/report','https://www.kra.go.ke:444/report','https://example.com/report'])
def test_nonofficial_transport_never_qualifies(tmp_path,url):
    proof,reason=capture_kra_release(receipt(tmp_path,url=url))
    assert proof is None and reason


def test_copied_json_and_mutated_acquisition_cannot_grant_authority(tmp_path):
    original=receipt(tmp_path)
    assert capture_kra_release(original)[0] is not None
    assert capture_kra_release(dict(original))[0] is None
    changed=deepcopy(original);changed['status']=True
    assert capture_kra_release(changed)[0] is None
    with pytest.raises(TypeError):NativeReportAuthority({},original)


@pytest.mark.parametrize('domain',['national_budget','audits'])
def test_pdf_retrieval_month_and_signature_are_not_publication_date(tmp_path,domain):
    from test_cob_publication_producer import pdf_bytes
    body=pdf_bytes('0','July 2026')
    path=tmp_path/'report.pdf';path.write_bytes(body)
    url='https://cob.go.ke/report.pdf' if domain=='national_budget' else 'https://www.oagkenya.go.ke/report.pdf'
    proof,reason=capture_pdf_report(path,receipt(tmp_path,body,url,'application/pdf'),domain=domain)
    assert proof is None and reason


def test_disabled_native_hooks_open_no_sessions(monkeypatch):
    from seeding.generation_dispatch import dispatch_committed_generation, dispatch_committed_report_generation
    monkeypatch.delenv('SOCIAL_GENERATION_HOOK_ENABLED',raising=False)
    def factory():pytest.fail('Default-off hook opened a session')
    for domain in ('national_budget','revenue_by_source','audits'):
        assert dispatch_committed_generation(factory,domain=domain,ingestion_id=1,dry_run=False) is None
        assert dispatch_committed_report_generation(factory,domain=domain,ingestion_id=1,dry_run=False) is None


@pytest.mark.parametrize('lead',[
    b'Revenue collection for the first quarter of the Financial Year 2024/2025.',
    b'Revenue collection for the first half of the Financial Year 2024/2025.',
    b'Revenue targets for the Financial Year 2024/2025.',
    b'Revenue projected to be collected for the Financial Year 2024/2025.',
    b'Revenue collected for the Financial Year 2026/2027.',
])
def test_annual_release_refuses_subperiod_target_and_forward_scope(tmp_path,lead):
    article=HTML.replace(LEAD,lead)
    assert capture_kra_release(receipt(tmp_path,article))[0] is None


def test_native_unsupported_financial_reason_survives_safe_job_projection():
    from services.generation_outcome import safe_generation_outcome
    raw=dict(state='unavailable',reason='financial_adapter_unavailable',processed=0,drafts_created=0,baselines=0,unchanged=0,refused=0)
    assert safe_generation_outcome(raw).get('reason')=='financial_adapter_unavailable'


def test_monthly_release_is_not_annual_scope(tmp_path):
    article=HTML.replace(LEAD,b'Revenue collected in July of the Financial Year 2024/2025.')
    assert capture_kra_release(receipt(tmp_path,article))[0] is None
