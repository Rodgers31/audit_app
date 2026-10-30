"""Strict optional cell authority for the native KRA annual article parser."""
from decimal import Decimal
import re
from bs4 import BeautifulSoup, Comment
from services.response_receipts import copy_receipt, seal_receipt
from .kra_parser import _TAX_HEADS, _MONEY_RE, _COLLECTION_CUE, _FIGURE_DISQUALIFIER

_NUMBER = r'(?:[1-9]\d{0,2}(?:,\d{3})+|(?:0|[1-9]\d*))(?:\.\d+)?'
_COLLECTION = re.compile(
    r'(?:PAYE|P\.A\.Y\.E|Pay As You Earn|Corporation Tax|Corporate Tax|Domestic VAT|Domestic Excise|Customs|Customs & Import Duty) '
    r'(?:collections? stood at|collected|collections? amounted to) '
    r'(?:Kshs?|KES)\.?\s*'+_NUMBER+r'\s*(?:Trillion|Billion|tn|bn)\.?',re.I)

_MONEY_TOKEN = r'(?:Kshs?|KES)\.?\s*'+_NUMBER+r'\s*(?:Trillion|Billion|tn|bn)\b'
_MONEY = r'(?:Kshs?|KES)\.?\s*(?P<amount>'+_NUMBER+r')\s*(?P<unit>Trillion|Billion|tn|bn)\b'
_PERCENT = _NUMBER+r'\s*%'
_ARTICLE_CLAIMS = {
    'PAYE': re.compile(r'Pay As You Earn \(P\.A\.YE\): KRA collected '+_MONEY+r'\s+from P\.A\.Y\.E, signifying a growth of '+_PERCENT+r'\s*\.', re.I),
    'VAT': re.compile(r'Domestic VAT: Domestic VAT collection stood at '+_MONEY+r'\s*,\s*reflecting a growth of '+_PERCENT+r' compared to the previous year\.', re.I),
    'Corporation Tax': re.compile(r'Corporation Tax: Corporation Tax grew by '+_PERCENT+r' compared to '+_PERCENT+r' in the last financial year, after KRA collected '+_MONEY+r'\s+against a target of '+_MONEY_TOKEN+r'\s*\.', re.I),
    'Excise Duty': re.compile(r'Domestic Excise\s*: The tax head recorded a performance rate of '+_PERCENT+r'\s*,\s*with a collection of '+_MONEY+r'\s*\.', re.I),
    'Customs & Import Duty': re.compile(r'Customs Revenue recorded a performance rate of '+_PERCENT+r' with a collection of '+_MONEY+r'\s+against a target of '+_MONEY_TOKEN+r'\s*\.', re.I),
}
_ARTICLE_TAILS = {
    'PAYE': re.compile(
        r'Despite the slow growth, the tax head recorded a performance rate of '+_PERCENT+r'\s*\. '
        r'The slow growth was attributed to utilisation of adjustment vouchers by taxpayers to offset tax liabilities '
        r'and policy impacts, which included adjustment of SHIF and Housing Levy from relief to allowable deductions '
        r'before tax computation\s*\.', re.I),
    'VAT': re.compile(
        r'In the first half of the FY, KRA collected '+_MONEY_TOKEN+r'\s*\. '
        r'In the second half of the FY, KRA implemented a raft of VAT compliance initiatives to seal revenue loopholes, '
        r'enabling the collection of '+_MONEY_TOKEN+r'\s*\. '
        r'These initiatives included strict VAT registration controls and verification of declarations\.', re.I),
    'Corporation Tax': re.compile(
        r'The performance was boosted by a number of sectors, including ICT, manufacturing, financial, real estate, '
        r'wholesale and retail among others\.', re.I),
    'Excise Duty': re.compile(
        r'The performance is attributed to a decline of revenue remittance from manufacturers of beer and tobacco '
        r'products by '+_PERCENT+r' and '+_PERCENT+r' respectively\. '
        r'KRA continues to enhance compliance measures in the sector\.', re.I),
    'Customs & Import Duty': re.compile(
        r'This translates to a revenue growth of '+_PERCENT+r', compared to the same period in '
        r'FY (?P<start>20\d{2})/(?P<end>20\d{2}|\d{2})\.', re.I),
}
_ARTICLE_CONTEXT = tuple(re.compile(pattern, re.I) for pattern in (
    r'The Exchequer Revenue grew by '+_PERCENT+r' after KRA collected '+_MONEY_TOKEN+
    r' compared to '+_MONEY_TOKEN+r' collected in the previous financial year\. '
    r'This translates to a performance rate of '+_PERCENT+r'\s*, against a target of '+_MONEY_TOKEN+r'\s*\.',
    r'KRA also collected '+_MONEY_TOKEN+r' on behalf of other government agencies\s*, '
    r'surpassing the target by '+_MONEY_TOKEN+r'\s*\. This translated to a performance rate of '+_PERCENT+r'\s*\.',
    r'Domestic Revenues registered a growth of '+_PERCENT+r' after KRA collected '+_MONEY_TOKEN+
    r' against a target of '+_MONEY_TOKEN+r'\s*\. This translates to a performance rate of '+_PERCENT+r'\s*\.',
    r'Betting Taxes: Excise Tax on betting services surpassed the target after registering a surplus of '+_MONEY_TOKEN+
    r' with a performance rate of '+_PERCENT+r'\s*\. The tax head collected '+_MONEY_TOKEN+
    r' against a target of '+_MONEY_TOKEN+r'\s*\. Betting Tax also registered a performance rate of '+_PERCENT+
    r' after collecting '+_MONEY_TOKEN+r' against a target of '+_MONEY_TOKEN+r'\s*\.',
))


def _reviewed_alignment(style):
    # CSS whitespace is bounded explicitly: str.strip() would silently erase
    # unsupported control bytes and turn an unknown declaration into authority.
    return type(style) is str and re.fullmatch(
        r'[ \t\r\n]*(?:text-align[ \t\r\n]*:[ \t\r\n]*justify[ \t\r\n]*;?[ \t\r\n]*)?',
        style, re.I) is not None


def _reviewed_article_tail(head, tail, period):
    # Authority needs the whole paragraph's reviewed meaning. A scope-word
    # blacklist cannot enumerate unknown qualifications (Q1, H1, or new prose).
    tail = tail.strip()
    if not tail:
        return True
    match = _ARTICLE_TAILS[head].fullmatch(tail)
    if match is None:
        return False
    if head == 'Customs & Import Duty':
        year = int(period[3:7])
        return int(match['start']) == year-1 and int(match['end'][-2:]) == year % 100
    return True


def _reviewed_article_claims(article, period):
    """Annual labelled sections; each amount belongs to an anchored head claim.

    Alignment is presentation only. Unknown CSS/classes and nested containers
    remain outside this grammar; later targets, half-years and vouchers never
    supply the selected collection token.
    """
    first = None
    for node in article.children:
        if isinstance(node, Comment):
            continue
        if getattr(node, 'name', None) is None:
            if str(node).strip():
                return
            continue
        first = node
        break
    if first is None or first.name != 'p':
        return
    attrs = dict(first.attrs)
    style = attrs.pop('style', '')
    if (attrs or not _reviewed_alignment(style)
            or any(n.name not in {'b','strong','em','i','u','sup'} or n.attrs for n in first.find_all(True))
            or not first.get_text(' ', strip=True).startswith('The Kenya Revenue Authority (KRA) has surpassed the revenue target of ')):
        return
    annual = customs = heads = False
    paragraph = 0
    for node in article.children:
        if getattr(node, 'name', None) is None:
            if not isinstance(node, Comment) and str(node).strip():
                annual = customs = heads = False
            continue
        if node.name == 'p':
            paragraph += 1
        attrs = dict(node.attrs)
        style = attrs.pop('style', '')
        if not _reviewed_alignment(style):
            annual = customs = heads = False
            continue
        if node.name == 'ol':
            start = attrs.pop('start', '1')
            visible = (not attrs and str(start) in ('1','2','3','4','5')
                and all(child.name in {'li','b','strong','em','i','u','sup'} and not child.attrs
                        for child in node.find_all(True)))
            text = ' '.join(node.stripped_strings)
            if not visible or text not in ('Exchequer Revenue', 'Agency Revenue',
                    'Domestic and Customs Revenue Performance'):
                annual = False
            customs = annual and visible and text == 'Domestic and Customs Revenue Performance'
            heads = False
            continue
        if (node.name != 'p' or attrs
                or any(child.name not in {'b','strong','em','i','u','sup'} or child.attrs
                       for child in node.find_all(True))):
            annual = customs = heads = False
            continue
        text = ' '.join(' '.join(node.stripped_strings).split())
        if not text:
            continue
        heading = re.fullmatch(r'Revenue Performance for FY\s*(20\d{2})/(20\d{2}|\d{2})', text, re.I)
        if heading:
            end = heading[2][-2:]
            annual = f'FY {heading[1]}/{end}' == period
            customs = heads = False
            continue
        if text == 'Performance of Key Tax Heads':
            heads, customs = annual, False
            continue
        # An entirely emphasised heading opens a different, unreviewed section.
        if node.find('u') is not None:
            annual = customs = heads = False
            continue
        qualified = False
        for head, pattern in _ARTICLE_CLAIMS.items():
            if not (customs if head == 'Customs & Import Duty' else heads):
                continue
            match = pattern.match(text)
            if match and _reviewed_article_tail(head, text[match.end():], period):
                qualified = True
                yield head, match['amount'], match['unit'], paragraph
        if annual and not qualified and not any(pattern.fullmatch(text) for pattern in _ARTICLE_CONTEXT):
            annual = customs = heads = False


def bind_press_cells(release, receipt):
    """Qualify one unambiguous annual collection per head in reviewed prose.

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
    if paragraphs and not paragraphs[0].get_text(' ',strip=True).startswith('The Kenya Revenue Authority (KRA) has surpassed the revenue target of '):
        paragraphs = []
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
    for head, number, unit, index in _reviewed_article_claims(articles[0], release.fiscal_year):
        amount = Decimal(number.replace(',', '')) * (Decimal('1000000000000')
            if unit.lower() in ('trillion','tn') else Decimal('1000000000'))
        figure = release.heads.get(head)
        if figure is not None and amount/Decimal('1000000000') == figure.amount_bn:
            candidates.setdefault(head, []).append((format(amount.normalize(), 'f'),
                dict(table='KRA annual press release', edition=release.fiscal_year,
                     paragraph=index, head=head)))
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
