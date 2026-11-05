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


def measure_evidence(value_kes, fiscal_year, basis, vintage, precision_kes, source):
    """Create evidence only at a source parser's qualified promotion boundary."""
    # Match the existing Numeric(..., 2) KES storage boundary. Binary
    # float products such as 2167.8 * 1e9 must survive exact DB readback.
    amount=finite_number(value_kes)
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
    return amount,proof,None


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
    """Sanitize every nested figure consumed by fiscal charts and civic readers."""
    from copy import deepcopy
    from services.fiscal_outturns import fiscal_outturn
    if fiscal_outturn(row)['absent_reason'] is not None:
        return None
    meta=row.meta if isinstance(row.meta,dict)else {}
    result=deepcopy(meta['fiscal_framework'])
    for key,value in list(result.items()):
        if key.endswith('_billion'):
            result[key]=finite_number(value,nonnegative=key not in {
                'adjustment_to_cash_basis_billion','statistical_discrepancy_billion'})
    revenue_parts=('ordinary_revenue_billion','ministerial_aia_billion')
    if any(k in result for k in revenue_parts):
        if (any(result.get(k)is None for k in revenue_parts)
                or abs(sum(result[k]for k in revenue_parts)-result['total_revenue_incl_aia_billion'])>0.150001):
            return None
    parts=('recurrent_billion','development_billion','county_transfers_billion','contingency_billion')
    if any(result.get(k)is None for k in parts) or abs(sum(result[k]for k in parts)-result['total_expenditure_billion'])>0.250001:
        for key in (*parts,'interest_payments_billion','county_equitable_share_billion'):
            result[key]=None
    interest,recurrent=result.get('interest_payments_billion'),result.get('recurrent_billion')
    if interest is None or recurrent is None or interest>recurrent:
        result['interest_payments_billion']=None
    share,transfers=result.get('county_equitable_share_billion'),result.get('county_transfers_billion')
    if share is None or transfers is None or share>transfers:
        result['county_equitable_share_billion']=None
    tax,non_tax,ordinary=(result.get(k)for k in ('tax_revenue_billion','non_tax_revenue_billion','ordinary_revenue_billion'))
    if (meta.get('tax_split_absent_reason') or result.get('tax_split_absent_reason')
            or tax is None or non_tax is None or ordinary is None
            or abs(tax+non_tax-ordinary)>0.150001):
        result['tax_revenue_billion']=result['non_tax_revenue_billion']=None
        result['tax_heads_billion']=None
    else:
        heads=result.get('tax_heads_billion')
        if isinstance(heads,dict):
            checked={k:finite_number(v)for k,v in heads.items()}
            result['tax_heads_billion']=checked if checked and all(v is not None for v in checked.values())and abs(sum(checked.values())-tax)<0.300001 else None
        else:result['tax_heads_billion']=None
    return result


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
            or observation['source']['sha256']!=BROP_SHA256 or observation['source']['url']!=BROP_URL):
        return None
    return {**observation, 'disclosure':'Separate BROP preliminary observation at whole-billion precision; not a split of the higher-precision APDMR headline.'}
