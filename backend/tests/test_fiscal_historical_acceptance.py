"""Historical source boundaries; real retained table text, inert acquisition seams."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import httpx

import pytest

from seeding.domains.fiscal_summary import fiscal_framework as ff
from seeding.domains.fiscal_summary.fetcher import _apply_fiscal_framework
from seeding.domains.fiscal_summary.fetcher import _fetch_budget_summary_editions
from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient

FIXTURES = Path(__file__).parent / 'fixtures' / 'budget_summary'
URL = ('https://www.treasury.go.ke/sites/default/files/Budget%20summary/'
       'Budget%20Summary%20for%20the%20FY%202026_27%20Budget.pdf')


def pages(name='fy2026_27'):
    doc = json.loads((FIXTURES / (name + '.json')).read_text())
    return [doc['pages'].get(str(i), '') for i in range(1, doc['_source']['page_count'] + 1)]


@pytest.mark.parametrize('label', ['Ordinary Revenue', 'Tax Revenue', 'Non-Tax Revenue'])
@pytest.mark.parametrize('shape', ['identical', 'different', 'short', 'label_only', 'nan', 'missing', 'mixed_invalid'])
def test_duplicate_component_is_ambiguous_even_when_first_copy_reconciles(label, shape):
    text = pages()
    line = next(line for line in text[62].splitlines() if line.startswith(label + ' '))
    tails = {'short': '1.0', 'different': ' '.join(['1.0'] * 12),
             'label_only': '', 'nan': 'NaN', 'missing': '-', 'mixed_invalid': '1.0 NaN'}
    duplicate = line if shape == 'identical' else (label + ' ' + tails[shape]).strip()
    text[62] += '\n' + duplicate
    with pytest.raises(ff.FiscalFrameworkError) as exc:
        ff.read_edition(text, fiscal_year='FY 2026/27')
    assert exc.value.reason == 'duplicate_annex_row'


def test_link_year_cannot_establish_missing_cover_identity():
    text = pages()
    text[:3] = ['', '', '']
    with pytest.raises(ff.FiscalFrameworkError) as exc:
        ff.read_edition(text, fiscal_year='FY 2026/27')
    assert exc.value.reason == 'edition_cover_year_unknown'


def test_relabeled_cover_and_link_cannot_relabel_the_narrative_budget():
    text = pages()
    text[0] = text[0].replace('2026/27', '2027/28')
    with pytest.raises(ff.FiscalFrameworkError) as exc:
        ff.read_edition(text, fiscal_year='FY 2027/28')
    assert exc.value.reason == 'narrative_edition_year_disagrees'


def test_cover_only_policy_anchor_cannot_supply_independent_body_identity():
    text = pages()
    text[0] = text[0].replace('2026/27', '2027/28') + '\nFiscal Policy Framework for the FY 2027/28'
    text[11] = text[11].replace('Fiscal Policy Framework for the FY', 'Fiscal discussion about FY')
    text[12] = text[12].replace('The FY 2026/27\ncomprises', 'The FY 2026/27\nincludes')
    assert 'comprises' not in text[12]
    with pytest.raises(ff.FiscalFrameworkError) as exc:
        ff.read_edition(text, fiscal_year='FY 2027/28')
    assert exc.value.reason == 'narrative_edition_year_disagrees'


@pytest.mark.parametrize('bad', ['million', 'USD billion', 'percent of GDP'])
def test_wrong_annex_unit_never_reuses_otherwise_valid_cells(bad):
    text = pages()
    assert 'KSh billion' in text[62]
    text[62] = text[62].replace('KSh billion', bad)
    with pytest.raises(ff.FiscalFrameworkError):
        ff.read_edition(text, fiscal_year='FY 2026/27')


def test_current_own_year_source_is_revalidated_on_an_unchanged_replay():
    edition = ff.read_edition(pages(), fiscal_year='FY 2026/27')
    payload = {'fiscal_years': [{'fiscal_year': 'FY 2026/27'}]}
    refreshed = set()
    first, _ = _apply_fiscal_framework(payload, [(URL, edition)], refreshed_revenue_years=refreshed)
    assert refreshed == {'FY 2026/27'}
    before = deepcopy(first)
    replayed = set()
    again, _ = _apply_fiscal_framework(first, [(URL, edition)], refreshed_revenue_years=replayed)
    assert again == before
    assert replayed == {'FY 2026/27'}


@pytest.mark.parametrize('basis,url,value', [
    ('apdmr_not_rebased', URL, 2985.7),
    ('ordinary_revenue_excl_aia', 'https://www.treasury.go.ke/another.pdf', 2985.7),
    ('ordinary_revenue_excl_aia', URL, 2901.9),
])
def test_retained_revenue_without_current_same_basis_evidence_earns_no_refresh(basis, url, value):
    row = {'fiscal_year': 'FY 2026/27', 'total_revenue': value,
           'revenue_basis': basis, 'revenue_source': {'url': url}}
    refreshed = set()
    result, _ = _apply_fiscal_framework({'fiscal_years': [row]},
        [(URL, ff.read_edition(pages(), fiscal_year='FY 2026/27'))],
        refreshed_revenue_years=refreshed)
    assert refreshed == set()
    assert result['fiscal_years'][0]['total_revenue'] == value


def test_retained_fy2022_budget_is_not_the_apdmr_actual_and_has_no_explicit_tax_split():
    edition = ff.read_edition(pages('fy2022_23'), fiscal_year='FY 2022/23')
    split = ff.split_for_fiscal_year(edition, 'FY 2022/23', known_ordinary_revenue=None)
    assert split.values['ordinary_revenue'] == Decimal('2141.6')
    assert split.values['recurrent'] == Decimal('2255.0')
    assert not split.tax_split_ok
    assert split.tax_split_reason == 'edition_prints_no_tax_or_non_tax_row'
    row = {'fiscal_year': 'FY 2022/23', 'total_revenue': 2042,
           'revenue_basis': 'apdmr_not_rebased'}
    refreshed = set()
    result, _ = _apply_fiscal_framework({'fiscal_years': [row]},
        [('https://www.treasury.go.ke/sites/default/files/Budget%20summary/Budget-Summary-for-the-FY-2022_23.pdf', edition)],
        refreshed_revenue_years=refreshed)
    assert refreshed == set()
    assert result['fiscal_years'][0]['total_revenue'] == 2042
    assert result['fiscal_years'][0]['tax_split_absent_reason'] == 'edition_prints_no_tax_or_non_tax_row'


def test_retained_fy2021_optional_unreadable_gdp_does_not_remove_sound_financial_coverage():
    text = pages('fy2021_22')
    assert '—' in next(line for line in text[56].splitlines() if line.startswith('Nominal GDP'))
    edition = ff.read_edition(text, fiscal_year='FY 2021/22')
    split = ff.split_for_fiscal_year(edition, 'FY 2021/22', known_ordinary_revenue=None)
    assert split.values['ordinary_revenue'] == Decimal('1775.6')
    assert split.values['expenditure'] == Decimal('3053.5')
    assert 'nominal_gdp' not in split.values
    text[56] += '\nNominal GDP NaN'
    with pytest.raises(ff.FiscalFrameworkError) as exc:
        ff.read_edition(text, fiscal_year='FY 2021/22')
    assert exc.value.reason == 'duplicate_annex_row'


@pytest.mark.parametrize('replacement', ['html', 'malformed_pdf', 'tls_error'])
def test_real_pdf_redirect_then_unusable_new_response_does_not_accept_cached_parse(tmp_path, replacement):
    # Native PDF page objects from the exact downloaded official edition,
    # reduced to cover, two narrative pages and Annex 2a; mapping is retained.
    data = (FIXTURES / 'fy2026_27_excerpt.pdf').read_bytes()
    source = json.loads((FIXTURES / 'fy2026_27_excerpt_source.json').read_text())
    assert hashlib.sha256(data).hexdigest() == source['sha256']
    listing = 'https://www.treasury.go.ke/budget-summary-revenue-expenditure'
    state = {'body': data}
    calls = []

    def serve(request):
        calls.append(str(request.url))
        if str(request.url) == listing:
            return httpx.Response(200, text=f'<a href="{URL}">FY 2026/27 Budget Summary</a>')
        if str(request.url) == URL:
            return httpx.Response(302, headers={'location': '/source-edition.pdf'})
        assert str(request.url) == 'https://www.treasury.go.ke/source-edition.pdf'
        if state['body'] is None:
            raise httpx.ConnectError('[SSL: CERTIFICATE_VERIFY_FAILED] hostname mismatch', request=request)
        return httpx.Response(200, content=state['body'])

    settings = SeedingSettings(_env_file=None, cache_path=tmp_path,
        pdf_cache_ttl_seconds=0, parse_cache_enabled=True, pdf_download_timeout_seconds=1,
    )
    with httpx.Client(transport=httpx.MockTransport(serve), follow_redirects=True) as transport:
        with SeedingHttpClient(settings, client=transport) as client:
            first, facts = _fetch_budget_summary_editions(client, settings)
            assert len(first) == 1
            split = ff.split_for_fiscal_year(first[0][1], 'FY 2026/27', known_ordinary_revenue=None)
            assert split.values['ordinary_revenue'] == Decimal('2985.7')
            assert split.values['tax_revenue'] == Decimal('2858.7')
            assert split.values['non_tax_revenue'] == Decimal('127.1')
            assert first[0][1].table.page == 4
            state['body'] = {'html': b'<html>Budget Summary FY 2026/27</html>',
                'malformed_pdf': b'%PDF-1.7\nmalformed\n%%EOF', 'tls_error': None}[replacement]
            second, refused = _fetch_budget_summary_editions(client, settings)
            assert second == []
            assert refused['budget_summary_editions'][URL]['status'].startswith('unreadable(')
    assert URL in calls and 'https://www.treasury.go.ke/source-edition.pdf' in calls


def test_all_five_accepted_parser_results_keep_exact_financial_values():
    # Replays the retained source-vintage choices, not a production row census.
    import test_fiscal_framework_split as existing
    payload = existing._payload_as_revenue_step_leaves_it()
    edition_22 = ff.read_edition(pages('fy2022_23'), fiscal_year='FY 2022/23')
    edition_23 = ff.read_edition(pages('fy2023_24'), fiscal_year='FY 2023/24')
    result, _ = _apply_fiscal_framework(payload, [(URL, ff.read_edition(pages(), fiscal_year='FY 2026/27')),
        (existing.URL_2324, edition_23),
        ('https://www.treasury.go.ke/sites/default/files/Budget%20summary/Budget-Summary-for-the-FY-2022_23.pdf', edition_22)])
    rows = {r['fiscal_year']: r for r in result['fiscal_years']}
    expected = {
        'FY 2022/23': (2042, 3342.8, 2255.0, 676.7, 407.0, 862.5),
        'FY 2023/24': (2288.9, 3605.2, 2678.4, 546.4, 380.4, 818.3),
        'FY 2024/25': (2420.2, 3975.9, 2948.4, 582.9, 444.6, 1034.2),
        'FY 2025/26': (2784.4, 4638.4, 3393.2, 758.4, 484.8, 1199.4),
        'FY 2026/27': (2985.7, 4785.2, 3538.7, 749.0, 495.5, 1111.8),
    }
    for fy, values in expected.items():
        r = rows[fy]
        assert (r['total_revenue'], r['fiscal_framework']['total_expenditure_billion'],
                r['recurrent_spending'], r['development_spending'], r['county_allocation'],
                r['total_borrowing']) == values
