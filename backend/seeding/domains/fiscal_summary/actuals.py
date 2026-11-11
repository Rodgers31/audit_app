"""Pinned official FY2022/23 provisional actuals; never joined by proximity.

APDMR Table 4.1-1 supplies the ordinary-revenue denominator and total debt
service at million-shilling precision. BROP Table 8's whole-billion split is
retained as a separate observation, not silently joined to the APDMR amount.
Only these explicitly reviewed editions are supported; new bytes need review.
"""
import hashlib
from pathlib import Path
from io import BytesIO
import re
from decimal import Decimal

from ...isolated_parser import isolated
from services.fiscal_qualification import VERSION, measure_evidence

APDMR_URL = 'https://www.treasury.go.ke/sites/default/files/Annual%20borrowing/Annual-Public-Debt-Report-2022-2023-Sept-2023.pdf'
APDMR_SHA256 = '00cf5f2e12e6b6733110d66e130404f63824b42d413b5a67b0250ec734f6eb1e'
BROP_URL = 'https://www.treasury.go.ke/sites/default/files/BBB/2023-Budget-Review-and-Outlook-Paper_f.pdf'
BROP_SHA256 = 'a8d6d4f38c9e4ec74134b98b1ed6164d8b4cd152714006740add1c9923e22986'
FY = 'FY 2022/23'


_PARSED_EDITION = object()


class ParsedAPDMR(dict):
    """Runtime binding to a read of the exact reviewed official PDF bytes."""
    def __init__(self, values, *, capability=None):
        if capability is not _PARSED_EDITION:
            raise ValueError('actuals require a pinned PDF read')
        super().__init__(values)
        self._authority = capability
        self._snapshot = dict(values)

    def __reduce_ex__(self, protocol):
        return dict, (dict(self),)


def parse_apdmr_table(cover, text):
    """Parse the native source table, refusing duplicate labels before cells."""
    cover=' '.join(cover.split())
    if ('ANNUAL PUBLIC DEBT MANAGEMENT REPORT' not in cover
            or not re.search(r'2022\s*/\s*2023',cover)):
        raise ValueError('apdmr_edition_identity')
    if (not re.search(r'Table 4\.1-\s*1: Total Public Debt Service \(Ksh Million\)',text)
            or not re.search(r'Jun-19\s+Jun-20\s+Jun-21\s+Jun-22\s+Jun-23\*',text)
            or '*Provisional' not in text):
        raise ValueError('apdmr_table_period_units_vintage')
    table=text.split('Table 4.1-',1)[1].split('As a percentage of Export',1)[0]
    fields={}
    for label in ('Total Debt Service','Total interest','External Debt Service','External Principal',
                  'External Interest','Domestic Debt','Domestic Interest','Domestic Principal','Ordinary Revenue'):
        hits=list(re.finditer(r'^'+re.escape(label)+r'(?:[ \t]+([^\n]*))?\n?',table,re.M))
        # The later memorandum repeats total interest/domestic interest as
        # ratios. Parse monetary rows strictly before "Memorandum items".
        scope=table if label=='Ordinary Revenue' else table.split('Memorandum items',1)[0]
        hits=list(re.finditer(r'^'+re.escape(label)+r'(?:[ \t]+([^\n]*))?\n?',scope,re.M))
        if len(hits)!=1:raise ValueError('apdmr_duplicate_or_missing_row:'+label)
        hit=hits[0];tail=(hit.group(1)or '').strip()
        if not tail:tail=scope[hit.end():].splitlines()[0].strip()
        tokens=tail.split()
        if len(tokens)!=5 or any(re.fullmatch(r'\d{1,3}(?:,\d{3})*|\d+',v)is None for v in tokens):
            raise ValueError('apdmr_malformed_required_row:'+label)
        fields[label]=[Decimal(v.replace(',','')) for v in tokens]
    for i in range(5):
        if (fields['External Principal'][i]+fields['External Interest'][i]!=fields['External Debt Service'][i]
                or fields['Domestic Interest'][i]+fields['Domestic Principal'][i]!=fields['Domestic Debt'][i]
                or fields['External Debt Service'][i]+fields['Domestic Debt'][i]!=fields['Total Debt Service'][i]):
            raise ValueError('apdmr_component_reconciliation')
    # Earlier years have publisher rounding inconsistencies; the selected
    # FY2022/23 column must reconcile exactly at the printed precision.
    if fields['Total interest'][-1] != fields['Domestic Interest'][-1]+fields['External Interest'][-1]:
        raise ValueError('apdmr_interest_reconciliation')
    return {key:float(values[-1]/1000)for key,values in fields.items()}


@isolated("payload", errors=(ImportError,))
def decode_apdmr_amounts(payload):
    """Read the selected native table from the reviewed edition."""
    import pdfplumber

    if len(payload) > 10_000_000 or hashlib.sha256(payload).hexdigest() != APDMR_SHA256:
        raise ValueError("apdmr_unreviewed_edition_bytes")
    with pdfplumber.open(BytesIO(payload)) as pdf:
        if len(pdf.pages) < 37:
            raise ValueError("apdmr_missing_table_page")
        return parse_apdmr_table(pdf.pages[0].extract_text() or "", pdf.pages[36].extract_text() or "")


def read_apdmr(path):
    path = Path(path)
    if path.stat().st_size > 10_000_000:
        raise ValueError("apdmr_unreviewed_edition_bytes")
    payload = path.read_bytes()
    if len(payload) > 10_000_000 or hashlib.sha256(payload).hexdigest() != APDMR_SHA256:
        raise ValueError("apdmr_unreviewed_edition_bytes")
    return ParsedAPDMR(decode_apdmr_amounts(payload), capability=_PARSED_EDITION)


def apply_apdmr(payload, amounts):
    """Explicit source transition, selected FY only; no spending rebase."""
    if (type(amounts) is not ParsedAPDMR
            or getattr(amounts, "_authority", None) is not _PARSED_EDITION
            or getattr(amounts, "_snapshot", None) != {k:v for k,v in amounts.items() if not k.startswith("_")}
            or type(amounts.get("Ordinary Revenue")) not in (int,float)
            or type(amounts.get("Total Debt Service")) not in (int,float)
            or amounts["Ordinary Revenue"] != 2041.119
            or amounts["Total Debt Service"] != 1201.033):
        raise ValueError("apdmr_selected_edition_amounts_disagree")
    from .fetcher import _validate_measure_contracts
    _validate_measure_contracts(payload)
    rows=payload.get('fiscal_years',[])
    hits=[row for row in rows if row.get('fiscal_year')==FY]
    if len(hits)!=1:raise ValueError('apdmr_target_row_ambiguous')
    row=hits[0]
    source={'title':'Annual Public Debt Management Report FY2022/2023 (September 2023)',
            'publisher':'The National Treasury','url':APDMR_URL,'page':'Table 4.1-1, PDF p.37',
            'sha256':APDMR_SHA256,'column':'Preliminary'}
    proofs={}
    for field,key,basis in (
        ('total_revenue','Ordinary Revenue','ordinary_revenue_excl_aia'),
        ('debt_service_cost','Total Debt Service','total_debt_service_interest_and_principal')):
        value=amounts[key]
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not 0<value<10000:
            raise ValueError('apdmr_invalid_amount')
        proofs[field]=measure_evidence(value*1e9,FY,basis,'Preliminary',1_000_000,dict(source))
    # Validate everything before altering the payload (including direct calls).
    from copy import deepcopy
    candidate=deepcopy(row)
    candidate.update(total_revenue=amounts['Ordinary Revenue'],debt_service_cost=amounts['Total Debt Service'],
        tax_revenue=None,non_tax_revenue=None,revenue_basis='ordinary_revenue_excl_aia',
        revenue_source=dict(source),debt_service_source=dict(source),
        tax_split_absent_reason='APDMR prints no tax/non-tax split; BROP Table 8 is a separate rounded observation.')
    old=candidate.get('fiscal_measure_contract')
    measures=dict(old.get('measures',{}))if isinstance(old,dict)and old.get('version')==VERSION else {}
    measures.pop('tax_revenue',None);measures.pop('non_tax_revenue',None);measures.update(proofs)
    candidate['fiscal_measure_contract']={'version':VERSION,'measures':measures}
    receipt=amounts.get('_response_receipt')
    if receipt is not None:
        from services.response_receipts import seal_receipt, copy_receipt
        receipt=copy_receipt(receipt, parser_version="fiscal-apdmr-actuals-v1")
        amounts["_response_receipt"]=receipt
        observations=[]
        for field in ('total_revenue','debt_service_cost'):
            proof=proofs[field]
            observations.append({
                'version':1,'source_kind':'pdf',
                'identity':{'measure':field,'entity_id':None,'geography':'KEN','period':FY,
                            'unit':'KES','basis':proof['basis'],'dimensions':{'vintage':'Preliminary'}},
                'raw_value':str(proof['value_kes']/1e6),'raw_unit':'million_KES',
                'value':str(proof['value_kes']),'unit':'KES',
                'locator':{'page':37,'table':'Table 4.1-1','cell':field+' / Jun-23*'},
                'transformation':{'operation':'multiply','factor':'1000000'},
                'checks':{'identity':True,'value':True,'transport':receipt.get('status')==200,
                          'bytes':receipt.get('byte_check',{}).get('status')=='matched','locator':True},
                'reconciliation':{'status':'matched','reason':'native printed table and component identities'},
            })
        seal_receipt(receipt,observations)
        candidate['source_evidence']=[{**item,'_response_receipt':receipt}for item in observations]
    row.clear();row.update(candidate)
    return payload


def fetch_apdmr(client, settings):
    from seeding.pdf_download import get_or_download_pdf
    path=get_or_download_pdf(client,APDMR_URL,cache_dir=Path(settings.cache_path)/'pdfs',
        ttl_seconds=settings.pdf_cache_ttl_seconds,max_seconds=settings.pdf_download_timeout_seconds,
        max_bytes=min(settings.pdf_download_max_bytes,10_000_000))
    parsed=read_apdmr(path)
    receipt=client.download_receipt(APDMR_URL)
    if receipt is not None:
        parsed["_response_receipt"]=receipt
    return parsed


@isolated("payload")
def _validate_brop_pdf(payload):
    import pdfplumber

    if len(payload) > 10_000_000 or hashlib.sha256(payload).hexdigest() != BROP_SHA256:
        raise ValueError("brop_unreviewed_edition_bytes")
    with pdfplumber.open(BytesIO(payload)) as pdf:
        cover = " ".join((pdf.pages[0].extract_text() or "").split())
        if ("2023 BUDGET REVIEW" not in cover or "SEPTEMBER 2023" not in cover
                or "Table 8: Government Fiscal Projections, Ksh Billion" not in (pdf.pages[20].extract_text() or "")):
            raise ValueError("brop_edition_table_identity")


def read_brop(path):
    """Read a reviewed transcription bound to this exact official edition.

    Automatic OCR was refused: selected cells read2081/1987 instead of
    2041/1887. This is an explicit human-reviewed candidate, not OCR success.
    Unknown bytes require another independent visual review and manifest.
    """
    import json

    path = Path(path)
    if path.stat().st_size > 10_000_000:
        raise ValueError("brop_unreviewed_edition_bytes")
    _validate_brop_pdf(path.read_bytes())
    manifest=json.loads((Path(__file__).parent/'data/brop-2023-table8-v1.json').read_text())
    if (manifest.get('contract')!='brop-reviewed-transcription-v1'
            or manifest.get('table')!='Table 8: Government Fiscal Projections'
            or manifest['source_sha256']!=BROP_SHA256 or type(manifest['pdf_page']) is not int
            or manifest['pdf_page']!=21 or manifest['fiscal_year']!=FY
            or manifest['column']!='Prel. Actual' or manifest['printed_unit']!='Ksh Billion'):
        raise ValueError('brop_transcription_identity_disagrees')
    values=manifest['cells']
    expected={'ordinary_revenue_billion':2041,'tax_revenue_billion':1887,'non_tax_revenue_billion':154,
              'aia_billion':319,'total_revenue_incl_aia_billion':2361}
    if set(values)!=set(expected) or any(type(values[k])is not int or values[k]!=v for k,v in expected.items()):
        raise ValueError('brop_transcription_cells_disagree')
    return {'fiscal_year':FY,'basis':'ordinary_revenue_excl_aia','vintage':'Preliminary',
        'precision_kes':1_000_000_000,**values,'extraction_method':'reviewed_transcription_v1',
        'source':{'url':BROP_URL,'sha256':BROP_SHA256,'page':'Table 8, PDF p.21',
                  'title':'2023 Budget Review and Outlook Paper, September 2023'}}


def fetch_brop(client,settings):
    from seeding.pdf_download import get_or_download_pdf
    path=get_or_download_pdf(client,BROP_URL,cache_dir=Path(settings.cache_path)/'pdfs',
        ttl_seconds=settings.pdf_cache_ttl_seconds,max_seconds=settings.pdf_download_timeout_seconds,
        max_bytes=min(settings.pdf_download_max_bytes,10_000_000))
    return read_brop(path)
