"""Actual native HTTP listing/PDF wrapper, not the broader text utility."""
from copy import deepcopy
from decimal import Decimal

import httpx
import pytest
from seeding.config import SeedingSettings
from seeding.domains.fiscal_summary import fetcher
from seeding.http_client import SeedingHttpClient
from services.receipt_store import LocalReceiptStore


def pdf(text):
    lines=[]
    for i,line in enumerate(text.splitlines()):
        escaped=line.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
        lines.append(f'BT /F1 8 Tf 12 {800-i*18} Td ({escaped}) Tj ET')
    stream='\n'.join(lines).encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [4 0 R] /Count 1 >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 850] /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>',
        b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    body=bytearray(b'%PDF-1.4\n');offsets=[0]
    for n,obj in enumerate(objects,1):offsets.append(len(body));body.extend(f'{n} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(body);body.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:body.extend(f'{offset:010d} 00000 n \n'.encode())
    body.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(body)


HEADER='NATIONAL GOVERNMENT BUDGET IMPLEMENTATION REVIEW REPORT\nFY 2025/26 FY 2025/26 FY 2025/26\n'
CASES={
    'original':(HEADER+"The National Government's original gross budget for FY 2025/26 amounts to KSh 4.69 trillion.",Decimal('4690')),
    'revised':(HEADER+'The revised original gross budget for FY 2025/26 was KSh 4.70 trillion.',None),
    'approved-only':(HEADER+'The approved budget for FY 2025/26 was KSh 4.70 trillion.',None),
    'net':(HEADER+'The original net estimates for FY 2025/26 were KSh 4.70 trillion.',None),
    'ministerial':(HEADER+'The ministerial original gross budget for FY 2025/26 was KSh 4.70 trillion.',None),
    'sectoral':(HEADER+'The sectoral original gross budget for FY 2025/26 was KSh 4.70 trillion.',None),
    'prior-year':(HEADER+'The original gross budget for FY 2024/25 was KSh 4.70 trillion.',None),
    'invalid-fy':('FY 2025/99 FY 2025/99. The original gross budget for FY 2025/99 was KSh 4.70 trillion.',None),
    'ambiguous-values':(HEADER+'The original gross budget for FY 2025/26 was KSh 4.69 trillion.\nThe original gross budget for FY 2025/26 was KSh 4.70 trillion.',None),
    'unrelated-revenue':(HEADER+'The original gross budget for FY 2025/26 was under review. Revenue was KSh 4.70 trillion.',None),
    'county-subject':(HEADER+"The County Government's original gross budget for FY 2025/26 was KSh 4.70 trillion.",None),
    'supplementary-original':(HEADER+'The supplementary original gross budget for FY 2025/26 was KSh 4.70 trillion.',None),
}


@pytest.mark.parametrize('case',list(CASES))
def test_native_pdf_wrapper_preserves_original_same_fy_national_measure(tmp_path,case):
    text,expected=CASES[case]
    url='https://cob.go.ke/owned/National-Government-Budget-Implementation-Review-Report-FY-2025-2026.pdf'
    requests=[]
    def respond(request):
        requests.append(str(request.url))
        if str(request.url)==url:return httpx.Response(200,content=pdf(text),headers={'content-type':'application/pdf'})
        return httpx.Response(200,text=f'<a href="{url}">National Government report FY 2025/26</a>',headers={'content-type':'text/html'})
    settings=SeedingSettings(_env_file=None,cob_birr_page_url='https://cob.go.ke/owned/listing/',storage_path=tmp_path,http_cache_enabled=False,rate_limit='1000/sec')
    with SeedingHttpClient(settings,client=httpx.Client(transport=httpx.MockTransport(respond)),receipt_store=LocalReceiptStore(tmp_path/'receipts')) as client:
        value,revenue,fy=fetcher._fetch_cob_headlines(client,settings)
    base={'fiscal_years':[{'fiscal_year':'FY 2025/26','appropriated_budget':4690,'budget_basis':'cob_gross'}]}
    result,status=fetcher._overlay_live_budget_headline(deepcopy(base),value,fiscal_year=fy)
    assert len(requests)==2
    assert value==(float(expected)if expected is not None else None),case
    if expected is None:assert status!='promoted' and result==base
    else:assert status=='promoted'
