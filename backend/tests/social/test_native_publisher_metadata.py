"""Publisher post-day authority is distinct from PDF/reporting/modified dates."""
from copy import deepcopy
import httpx
import pytest
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response
from seeding.native_report_authority import capture_pdf_report
from test_cob_publication_producer import pdf_bytes

PAGE='https://cob.go.ke/download/national-government-budget-implementation-review-report-fy-2025-2026/'
URL=PAGE+'?wpdmdl=16454'
TITLE='NATIONAL GOVERNMENT BUDGET IMPLEMENTATION REVIEW REPORT FY 2025/2026'
COUNTY_TITLE='COUNTY GOVERNMENTS BUDGET IMPLEMENTATION REVIEW REPORT FOR THE FINANCIAL YEAR 2025/26'
COUNTY_PAGE='https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/'


def listing(title=TITLE,page=PAGE,identifier=16454):
    return f'''<meta property="og:type" content="article"><meta property="og:title" content="{title}">
<meta property="og:url" content="{page}"><meta property="article:published_time" content="2026-09-04T10:32:37+00:00">
<meta property="article:modified_time" content="2026-10-14T08:40:37+00:00">
<article id="post-{identifier}" class="wpdmpro status-publish"><div class="post-materials">
<a title=" Publish Time : September 4, 2026 10:32 Updated Time : October 14, 2026 8:40" href="{page}">
<time datetime="2026-09-04T10:32:37+00:00">September 4, 2026</time></a></div>
<a class="wpdm-download-link" href="#" onclick="location.href='{page}?wpdmdl={identifier}';return false;">Download</a></article>'''.encode()


def acquisition(tmp_path,body,url,ctype):
    return capture_response(httpx.Response(200,content=body,headers={'content-type':ctype},request=httpx.Request('GET',url)),LocalReceiptStore(tmp_path/'receipts'))


def inputs(tmp_path,domain='national_budget'):
    title,page,identifier=(TITLE,PAGE,16454) if domain=='national_budget' else (COUNTY_TITLE,COUNTY_PAGE,16482)
    body=pdf_bytes(label='September 2026').replace(b'Controller of Budget County Budget Implementation Review FY2025/26 Annual',title.encode())
    path=tmp_path/'report.pdf';path.write_bytes(body)
    return path,acquisition(tmp_path,body,page+f'?wpdmdl={identifier}','application/pdf'),acquisition(tmp_path,listing(title,page,identifier),page,'text/html')


@pytest.mark.parametrize('domain',['national_budget','pending_bills'])
def test_exact_publisher_post_day_qualifies_without_artificial_pdf_label(tmp_path,domain):
    path,pdf,metadata=inputs(tmp_path,domain)
    authority,reason=capture_pdf_report(path,pdf,domain=domain,publisher_receipt=metadata)
    assert authority is not None,reason
    assert authority.value['published_on']=='2026-09-04'
    assert authority.value['period']=='FY 2025/26'
    assert authority.value['publication_authority']['modified_at']=='2026-10-14T08:40:37+00:00'
    assert authority.value['publication_authority']['receipt']['digest']==metadata['digest']
    assert authority.value['document_checksum']==pdf['digest']


@pytest.mark.parametrize('mutation',[
    lambda b:b.replace(b'2026-09-04T10:32:37+00:00',b'2026-09-05T10:32:37+00:00',1),
    lambda b:b.replace(b'16454',b'16455'),
    lambda b:b.replace(b'2025/2026',b'2024/2025'),
    lambda b:b.replace(b'September 4, 2026',b'October 14, 2026'),
    lambda b:b.replace(b'article:published_time',b'article:retrieved_time'),
    lambda b:b.replace(b'og:url',b'og:other'),
    lambda b:b+b'<meta property="article:published_time" content="2026-09-04T10:32:37+00:00">',
    lambda b:b.replace(b'https://cob.go.ke/',b'https://evil.invalid/'),
    lambda b:b.replace(b'2026-10-14T08:40:37+00:00',b'2099-10-14T08:40:37+00:00'),
    lambda b:b.replace(b'status-publish',b'status-draft'),
])
def test_mismatched_ambiguous_or_unpublished_metadata_refuses(tmp_path,mutation):
    path,pdf,_=inputs(tmp_path)
    bad=acquisition(tmp_path,mutation(listing()),PAGE,'text/html')
    authority,reason=capture_pdf_report(path,pdf,domain='national_budget',publisher_receipt=bad)
    assert authority is None and reason


def test_no_metadata_keeps_existing_refusal(tmp_path):
    path,pdf,_=inputs(tmp_path)
    assert capture_pdf_report(path,pdf,domain='national_budget')[0] is None


@pytest.mark.parametrize('kind',['json','mutated','missing_bytes','cross_host','stale'])
def test_metadata_capability_and_retained_bytes_required(tmp_path,kind):
    path,pdf,metadata=inputs(tmp_path)
    if kind=='json':metadata=dict(metadata)
    if kind=='mutated':metadata['status']=True
    if kind=='missing_bytes':metadata._store.read=lambda key:b''
    if kind=='cross_host':metadata=acquisition(tmp_path,listing(),'https://www.kra.go.ke/other','text/html')
    if kind=='stale':
        # Original acquisition snapshot remains protected; no edited JSON can refresh it.
        metadata['acquired_at']='2026-10-01T00:00:00+00:00'
    assert capture_pdf_report(path,pdf,domain='national_budget',publisher_receipt=metadata)[0] is None


def test_real_stale_metadata_acquisition_cannot_pair_with_current_pdf(tmp_path,monkeypatch):
    from services import response_receipts
    path,pdf,_=inputs(tmp_path)
    monkeypatch.setattr(response_receipts,'now_iso',lambda:'2026-10-20T00:00:00+00:00')
    stale=acquisition(tmp_path,listing(),PAGE,'text/html')
    assert capture_pdf_report(path,pdf,domain='national_budget',publisher_receipt=stale)[0] is None


def test_pdf_label_conflict_is_not_replaced_by_post_day(tmp_path):
    body=pdf_bytes(label='Publication date: 2026-08-01').replace(b'Controller of Budget County Budget Implementation Review FY2025/26 Annual',TITLE.encode())
    path=tmp_path/'conflict.pdf';path.write_bytes(body)
    pdf=acquisition(tmp_path,body,URL,'application/pdf')
    post=acquisition(tmp_path,listing(),PAGE,'text/html')
    assert capture_pdf_report(path,pdf,domain='national_budget',publisher_receipt=post)[0] is None


def test_equivalent_fiscal_spellings_do_not_create_two_editions(tmp_path):
    body=pdf_bytes(label='Publication date: 2026-09-04').replace(b'Controller of Budget County Budget Implementation Review FY2025/26 Annual',
        (TITLE+' '+TITLE.replace('2025/2026','2025/26')).encode())
    path=tmp_path/'two-spellings.pdf';path.write_bytes(body)
    pdf=acquisition(tmp_path,body,URL,'application/pdf')
    assert capture_pdf_report(path,pdf,domain='national_budget')[0] is not None


@pytest.mark.parametrize('body',[b'x'*(512*1024+1)])
def test_publisher_transfer_byte_cap(tmp_path,body):
    from seeding.cob_report_metadata import fetch_publisher_receipt
    from seeding.http_client import SeedingHttpClient,PdfDownloadError
    from seeding.config import SeedingSettings
    settings=SeedingSettings()
    transport=httpx.MockTransport(lambda req:httpx.Response(200,content=body,headers={'content-type':'text/html'},request=req))
    with SeedingHttpClient(settings,client=httpx.Client(transport=transport),receipt_store=LocalReceiptStore(tmp_path/'store')) as client:
        with pytest.raises(PdfDownloadError):fetch_publisher_receipt(client,URL,tmp_path)
        assert client.download_receipt(PAGE) is None
    assert not list(tmp_path.glob('report-post-*'))


def test_native_publisher_transport_retains_exact_html_and_cleans_scratch(tmp_path):
    from seeding.cob_report_metadata import fetch_publisher_receipt
    from seeding.http_client import SeedingHttpClient
    from seeding.config import SeedingSettings
    requests=[]
    def handle(req):
        requests.append(str(req.url))
        return httpx.Response(200,content=listing(),headers={'content-type':'text/html'},request=req)
    with SeedingHttpClient(SeedingSettings(),client=httpx.Client(transport=httpx.MockTransport(handle)),receipt_store=LocalReceiptStore(tmp_path/'store')) as client:
        captured=fetch_publisher_receipt(client,URL,tmp_path)
        assert captured._store.read(captured['storage_key'])==listing()
        assert requests==[PAGE]
    assert not list(tmp_path.glob('report-post-*'))


def pdf_document(texts):
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'PLACEHOLDER',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids=[]
    for content in texts:
        page_id=len(objects)+1;stream_id=page_id+1;kids.append(page_id)
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 850] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>'.encode())
        lines=[]
        for i,line in enumerate(content.splitlines()):
            safe=line.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
            lines.append(f'BT /F1 10 Tf 20 {800-i*20} Td ({safe}) Tj ET')
        stream='\n'.join(lines).encode()
        objects.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
    objects[1]=('<< /Type /Pages /Kids ['+' '.join(f'{n} 0 R' for n in kids)+f'] /Count {len(kids)} >>').encode()
    body=bytearray(b'%PDF-1.4\n');offsets=[0]
    for n,obj in enumerate(objects,1):offsets.append(len(body));body.extend(f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(body);body.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:body.extend(f'{offset:010d} 00000 n \n'.encode())
    body.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(body)


@pytest.mark.parametrize('subperiod',['FIRST THREE MONTHS','FIRST SIX MONTHS','FIRST NINE MONTHS','FIRST QUARTER','FIRST HALF YEAR','FIRST HALF'])
def test_explicit_subperiod_on_page_three_is_not_annual(tmp_path,subperiod):
    body=pdf_document([TITLE,TITLE,f'This report covers the {subperiod} OF FY 2025/26.'])
    path=tmp_path/'subperiod.pdf';path.write_bytes(body)
    pdf=acquisition(tmp_path,body,URL,'application/pdf')
    post=acquisition(tmp_path,listing(),PAGE,'text/html')
    assert capture_pdf_report(path,pdf,domain='national_budget',publisher_receipt=post)[0] is None


def test_statutory_quarterly_duty_does_not_change_annual_scope(tmp_path):
    body=pdf_document([TITLE,TITLE,'FOREWORD: The office reports quarterly. This annual report covers 1 July 2025 to 30 June 2026.'])
    path=tmp_path/'annual.pdf';path.write_bytes(body)
    pdf=acquisition(tmp_path,body,URL,'application/pdf')
    post=acquisition(tmp_path,listing(),PAGE,'text/html')
    assert capture_pdf_report(path,pdf,domain='national_budget',publisher_receipt=post)[0] is not None


@pytest.mark.parametrize('original,changed',[
    (b'<time ',b'<time datetime="2026-10-14T08:40:37+00:00" '),
    (b'property="article:published_time"',b'property="article:modified_time" property="article:published_time"'),
    (b'id="post-16454"',b'id="post-99999" id="post-16454"'),
    (b'class="wpdm-download-link"',b'class="other" class="wpdm-download-link"'),
])
def test_ambiguous_authority_attributes_are_not_silently_normalized(tmp_path,original,changed):
    path,pdf,_=inputs(tmp_path)
    post=acquisition(tmp_path,listing().replace(original,changed),PAGE,'text/html')
    assert capture_pdf_report(path,pdf,domain='national_budget',publisher_receipt=post)[0] is None


@pytest.mark.parametrize('descriptor',['FIRST NINE MONTHS','FIRST SIX MONTHS','FIRST HALF','FIRST QUARTER','HALF YEAR'])
@pytest.mark.parametrize('page',[0,2])
def test_every_native_period_descriptor_refuses_annual_authority(tmp_path,descriptor,page):
    pages=[TITLE,TITLE,'FOREWORD'];pages[page]=TITLE+'\n'+descriptor+' FY 2025/2026'
    body=pdf_document(pages);path=tmp_path/'native-period.pdf';path.write_bytes(body)
    pdf=acquisition(tmp_path,body,URL,'application/pdf')
    post=acquisition(tmp_path,listing(),PAGE,'text/html')
    assert capture_pdf_report(path,pdf,domain='national_budget',publisher_receipt=post)[0] is None
