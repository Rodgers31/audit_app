"""Strict optional cell authority for the native KRA annual article parser."""
from decimal import Decimal
import re
from bs4 import BeautifulSoup
from services.response_receipts import copy_receipt, seal_receipt
from .kra_parser import _TAX_HEADS, _MONEY_RE, _COLLECTION_CUE, _FIGURE_DISQUALIFIER

_NUMBER = r'(?:[1-9]\d{0,2}(?:,\d{3})+|(?:0|[1-9]\d*))(?:\.\d+)?'
_COLLECTION = re.compile(
    r'(?:PAYE|P\.A\.Y\.E|Pay As You Earn|Corporation Tax|Corporate Tax|Domestic VAT|VAT|Domestic Excise|Excise Duty|Customs|Customs & Import Duty) '
    r'(?:collections? stood at|collected|collections? amounted to) '
    r'(?:Kshs?|KES)\.?\s*'+_NUMBER+r'\s*(?:Trillion|Billion|tn|bn)\.?',re.I)


def bind_press_cells(release, receipt):
    """Only one collection and one named head in a visible paragraph qualify.

    The existing best-effort numeric parser is unchanged. Ambiguous prose stays
    numeric-only; it cannot acquire announcement authority from a nearby value.
    """
    from ...native_report_authority import retained_body
    body = retained_body(receipt,'revenue_by_source','text/html')
    soup = BeautifulSoup(body,'html.parser')
    for hidden in soup.select('script,style,noscript,[hidden],[aria-hidden="true"]'):
        hidden.decompose()
    articles=soup.select('.blog-content')
    if len(articles)!=1:
        return
    if any(getattr(node,'attrs',{}).get('style') is not None for node in [articles[0],*articles[0].parents]):
        return  # CSS visibility is outside the retained article grammar.
    candidates = {}
    # The annual achieved-results lead grants scope only to a consecutive run
    # of explicit collection paragraphs. A heading, unknown narrative or nested
    # section ends this narrow grammar; later prose cannot inherit annual scope.
    paragraphs=[]
    for node in articles[0].children:
        if getattr(node,'name',None) is None:
            if str(node).strip():break
            continue
        if node.name!='p':break
        if node.attrs or any(child.name not in {'b','strong','em','i'} or child.attrs for child in node.find_all(True)):
            break
        paragraphs.append(node)
    if not paragraphs or not paragraphs[0].get_text(' ',strip=True).startswith('The Kenya Revenue Authority (KRA) has surpassed the revenue target of '):
        return
    for index, paragraph in enumerate(paragraphs[1:],2):
        text = ' '.join(paragraph.stripped_strings)
        low=text.lower()
        heads={head for head,patterns in _TAX_HEADS if any(re.search(pattern,low) for pattern in patterns)}
        money=list(_MONEY_RE.finditer(text))
        if len(heads)!=1 or len(money)!=1 or _COLLECTION.fullmatch(text) is None:
            break
        head=next(iter(heads));m=money[0];before=text[max(0,m.start()-60):m.start()]
        if not _COLLECTION_CUE.search(before) or _FIGURE_DISQUALIFIER.search(before):
            continue
        amount=Decimal(m[1].replace(',',''))*(Decimal('1000000000000') if m[2].lower() in ('trillion','tn') else Decimal('1000000000'))
        figure=release.heads.get(head)
        if figure is None or amount/Decimal('1000000000')!=figure.amount_bn:
            continue
        candidates.setdefault(head,[]).append((format(amount,'f'),dict(table='KRA annual press release',edition=release.fiscal_year,paragraph=index,head=head)))
    qualified={head:items[0] for head,items in candidates.items() if len(items)==1}
    if not qualified:
        return
    bound=copy_receipt(receipt,parser_version='kra-press-cells-v1',source_kind='web')
    bound['observations']=[dict(identity=dict(measure='amount_billion_kes',entity_id=None,geography='KEN',period=release.fiscal_year,
        unit='billion_KES',basis='actual',dimensions=dict(revenue_type=head,category='tax')),
        locator=locator,raw_value=raw,raw_unit='KES',transformation=dict(operation='multiply',factor='0.000000001',rounding=1,rounding_mode='ROUND_HALF_UP')) for head,(raw,locator) in qualified.items()]
    seal_receipt(bound)
    for head,(raw,locator) in qualified.items():
        release.heads[head].raw_amount=raw;release.heads[head].locator=locator
    release.response_receipt=bound


def row_evidence(release, row):
    figure=release.heads.get(row.get('revenue_type'))
    receipt=release.response_receipt
    if not receipt or figure is None or figure.raw_amount is None or figure.locator is None:
        return []
    return [dict(version=1,source_kind='web',identity=dict(measure='amount_billion_kes',entity_id=None,
        geography='KEN',period=release.fiscal_year,unit='billion_KES',basis='actual',
        dimensions=dict(revenue_type=row['revenue_type'],category=row.get('category','tax'))),
        receipt=dict(digest=receipt['digest']),_response_receipt=receipt,raw_value=figure.raw_amount,raw_unit='KES',
        value=str(row['amount_billion_kes']),unit='billion_KES',locator=figure.locator,
        transformation=dict(operation='multiply',factor='0.000000001',rounding=1,rounding_mode='ROUND_HALF_UP'),
        checks=dict(identity=True,value=True,transport=True,bytes=True,locator=True),
        reconciliation=dict(status='matched',reason='Exact unambiguous annual article collection token; no independent annual-PDF reconciliation'))]
