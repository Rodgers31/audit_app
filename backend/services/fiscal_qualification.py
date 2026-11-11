"""Versioned fiscal measure evidence shared by every public fiscal reader.

A row locator qualifies a row's presence, never all of its numeric columns.
The evidence binds each value, period, accounting basis, vintage and precision.
"""
import re
from urllib.parse import urlsplit

from services.fiscal_outturns import finite_number

VERSION = 'fiscal-measures-v1'
MONEY_BASES = {
    'appropriated_budget': {'cob_gross'},
    'total_revenue': {'ordinary_revenue_excl_aia'},
    'tax_revenue': {'ordinary_revenue_excl_aia'},
    'non_tax_revenue': {'ordinary_revenue_excl_aia'},
    'debt_service_cost': {'total_debt_service_interest_and_principal'},
    'total_borrowing': {'treasury_fiscal_framework'},
    'recurrent_spending': {'treasury_fiscal_framework'},
    'development_spending': {'treasury_fiscal_framework'},
    'county_allocation': {'treasury_fiscal_framework'},
    'debt_ceiling': set(), 'actual_debt': set(),
}
VINTAGES = frozenset({'Actual','Preliminary','Approved','Supplementary I'})
SOURCE_TEXT_FIELDS = ('title', 'publisher', 'table', 'edition', 'column',
                      'column_identification', 'measure', 'cell', 'extraction_method')


def fiscal_year_key(value):
    if not isinstance(value,str):
        return None
    match=re.fullmatch(r'(?:FY\s*)?(\d{4})/(\d{2})',value)
    if not match or int(match[2])!=(int(match[1])+1)%100:
        return None
    return f"FY {match[1]}/{match[2]}"


def valid_source(source):
    from services.publication_gate import _has_page_locator
    if not isinstance(source, dict):
        return False
    if not isinstance(source.get('url'),str):
        return False
    if any(source.get(key) is not None and (not isinstance(source[key], str)
           or not source[key].strip() or len(source[key]) > 2000)
           for key in SOURCE_TEXT_FIELDS if key != 'column'):
        return False
    try:
        url = urlsplit(source['url'])
        host = url.hostname
        if (url.scheme != 'https' or host not in {'treasury.go.ke','www.treasury.go.ke','cob.go.ke','www.cob.go.ke'}
                or url.username or url.password or url.port not in (None,443) or url.fragment):
            return False
    except (TypeError,ValueError):
        return False
    page = source.get('page')
    page = str(page) if type(page) is int else page
    digest = source.get('sha256')
    return bool(_has_page_locator(page, allow_descriptive=True)
                and isinstance(digest,str) and re.fullmatch(r'[0-9a-f]{64}',digest))


def public_source(source):
    """No unknown nested financial payload can hitchhike in source metadata."""
    from copy import deepcopy
    result = {key: deepcopy(source[key]) for key in ('url', 'page', 'sha256')}
    result.update({key: source[key] for key in SOURCE_TEXT_FIELDS
                   if isinstance(source.get(key), str) and source[key].strip()})
    return result


def public_measure_proof(proof):
    from copy import deepcopy
    result = {key: deepcopy(proof[key]) for key in (
        'value_kes', 'fiscal_year', 'basis', 'vintage', 'precision_kes')}
    result['source'] = public_source(proof['source'])
    for key in ('source_document_id', 'extraction_id'):
        if type(proof.get(key)) is int and proof[key] > 0:
            result[key] = proof[key]
    return result


def measure_evidence(value_kes, fiscal_year, basis, vintage, precision_kes, source):
    """Create evidence only at a source parser's qualified promotion boundary."""
    # Match the existing Numeric(..., 2) KES storage boundary. Binary
    # float products such as 2167.8 * 1e9 must survive exact DB readback.
    amount=finite_number(value_kes, nonnegative=False)
    if amount is not None:
        value_kes=round(amount,2)
    return {'value_kes':value_kes, 'fiscal_year':fiscal_year, 'basis':basis,
            'vintage':vintage, 'precision_kes':precision_kes, 'source':source}


def qualify_measure(row, field):
    meta = row.meta if isinstance(row.meta,dict) else {}
    contract = meta.get('fiscal_measure_contract')
    if not isinstance(contract,dict) or contract.get('version') != VERSION:
        return None, None, 'measure_contract_missing_or_unknown'
    measures = contract.get('measures')
    proof = measures.get(field) if isinstance(measures,dict) else None
    if not isinstance(proof,dict):
        return None,None,'measure_source_unconfirmed'
    amount = finite_number(getattr(row,field,None))
    witnessed = finite_number(proof.get('value_kes'))
    precision = finite_number(proof.get('precision_kes'))
    fy = getattr(row,'fiscal_year',None)
    if (getattr(row,'unit',None) != 'KES' or amount is None or witnessed is None
            or amount != witnessed or precision is None or precision <= 0
            or precision > 1e9 or not isinstance(fy,str)
            or fiscal_year_key(fy) is None
            or fiscal_year_key(proof.get('fiscal_year')) != fiscal_year_key(fy)
            or not isinstance(proof.get('basis'),str) or proof['basis'] not in MONEY_BASES.get(field,set())
            or not isinstance(proof.get('vintage'),str) or proof['vintage'] not in VINTAGES
            or not valid_source(proof.get('source'))
            or (proof['source'].get('column') is not None
                and proof['source']['column']!=proof['vintage'])):
        return None,None,'measure_evidence_invalid_or_contradictory'
    return amount,public_measure_proof(proof),None


def fiscal_values(row):
    """Return raw KES, nullable derived ratios and a reason for every absence."""
    result={'fiscal_year':row.fiscal_year,'unit':'KES','absent_reasons':{},'measure_qualifications':{}}
    for field in MONEY_BASES:
        amount,proof,reason=qualify_measure(row,field)
        result[field]=amount
        if reason:result['absent_reasons'][field]=reason
        else:result['measure_qualifications'][field]=proof
    # A contradictory/absent split never escapes merely because a legacy
    # column still contains the old number. No residual is manufactured.
    q=result['measure_qualifications']
    split=('total_revenue','tax_revenue','non_tax_revenue')
    if all(f in q for f in split):
        signatures={(q[f]['source']['sha256'],q[f]['vintage'])for f in split}
        tolerance=sum(q[f]['precision_kes']/2 for f in split)
        if len(signatures)!=1 or abs(result['tax_revenue']+result['non_tax_revenue']-result['total_revenue'])>tolerance:
            for f in split[1:]:
                result[f]=None;q.pop(f,None);result['absent_reasons'][f]='tax_split_basis_or_vintage_disagrees'
    meta=row.meta if isinstance(row.meta,dict)else {}
    if meta.get('tax_split_absent_reason'):
        for field in ('tax_revenue','non_tax_revenue'):
            result[field]=None;q.pop(field,None)
            result['absent_reasons'][field]='source_declares_tax_split_absent'
    for field in ('borrowing_pct_of_budget','debt_service_per_shilling','debt_ceiling_usage_pct'):
        result[field]=None;result['absent_reasons'][field]='compatible_qualified_inputs_required'
    ds,rev=q.get('debt_service_cost'),q.get('total_revenue')
    if ds and rev and result['total_revenue']>0 and (ds['vintage'],ds['source']['sha256'])==(rev['vintage'],rev['source']['sha256']):
        ratio=finite_number(result['debt_service_cost']/result['total_revenue']*100)
        if ratio is not None:
            result['debt_service_per_shilling']=round(ratio,1)
            result['absent_reasons'].pop('debt_service_per_shilling')
    meta=row.meta if isinstance(row.meta,dict)else {}
    framework=meta.get('fiscal_framework')
    if isinstance(framework,dict) and 'total_borrowing' in q:
        from services.fiscal_outturns import fiscal_outturn
        outturn=fiscal_outturn(row)
        denominator_source=framework.get('source')
        numerator=q['total_borrowing']
        compatible=(isinstance(denominator_source,dict)
                    and numerator['source']['sha256']==denominator_source.get('sha256')
                    and numerator['vintage']==denominator_source.get('column')
                    and result['total_borrowing']/1e9==outturn.get('financing'))
        if compatible and outturn['absent_reason'] is None and outturn['expenditure']>0:
            ratio=finite_number(result['total_borrowing']/1e9/outturn['expenditure']*100)
            if ratio is not None:
                result['borrowing_pct_of_budget']=round(ratio,1)
                result['absent_reasons'].pop('borrowing_pct_of_budget')
    return result


def published_framework(row):
    """Every exposed framework cell passes its own versioned evidence gate."""
    from services.fiscal_framework_qualification import qualified_framework
    return qualified_framework(row)[0]


def published_tax_observation(row):
    """Only the independently reviewed BROP observation is presently supported."""
    from seeding.domains.fiscal_summary.actuals import BROP_SHA256,BROP_URL,FY
    meta=row.meta if isinstance(row.meta,dict)else {}
    observation=meta.get('tax_split_observation')
    if not isinstance(observation,dict) or observation.get('fiscal_year')!=FY or fiscal_year_key(row.fiscal_year)!=FY:
        return None
    expected={'ordinary_revenue_billion':2041,'tax_revenue_billion':1887,
              'non_tax_revenue_billion':154,'aia_billion':319,'total_revenue_incl_aia_billion':2361}
    if (any(type(observation.get(k))not in (int,float)or observation[k]!=v for k,v in expected.items())
            or type(observation.get('precision_kes'))is not int or observation['precision_kes']!=1_000_000_000
            or observation.get('basis')!='ordinary_revenue_excl_aia' or observation.get('vintage')!='Preliminary'
            or not valid_source(observation.get('source'))
            or observation['source']['sha256']!=BROP_SHA256 or observation['source']['url']!=BROP_URL
            or observation['source']['page']!='Table 8, PDF p.21'
            or observation['source'].get('table') not in (None, 'Table 8', 'Table 8: Government Fiscal Projections')
            or observation['source'].get('column') not in (None, 'Preliminary', 'Prel. Actual')):
        return None
    result = {key: observation[key] for key in (*expected, 'fiscal_year', 'precision_kes', 'basis', 'vintage')}
    result['source'] = public_source(observation['source'])
    result['disclosure'] = 'Separate BROP preliminary observation at whole-billion precision; not a split of the higher-precision APDMR headline.'
    return result
