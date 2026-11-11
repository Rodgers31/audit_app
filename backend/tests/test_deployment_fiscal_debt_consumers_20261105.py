"""Pinned BROP publication metadata, synthetic guard inputs only; never source acceptance."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from seeding.domains.fiscal_summary.actuals import BROP_SHA256, BROP_URL, FY
from services.fiscal_qualification import published_tax_observation


def brop_row():
    observation = {
        'fiscal_year': FY, 'basis': 'ordinary_revenue_excl_aia', 'vintage': 'Preliminary',
        'ordinary_revenue_billion': 2041, 'tax_revenue_billion': 1887,
        'non_tax_revenue_billion': 154, 'aia_billion': 319,
        'total_revenue_incl_aia_billion': 2361, 'precision_kes': 1_000_000_000,
        'source': {'url': BROP_URL, 'sha256': BROP_SHA256, 'page': 'Table 8, PDF p.21',
                   'title': '2023 Budget Review and Outlook Paper, September 2023'},
    }
    return SimpleNamespace(fiscal_year=FY, meta={'tax_split_observation': observation})


def test_brop_separate_pinned_observation_remains_available():
    result = published_tax_observation(brop_row())
    assert result is not None
    assert result['ordinary_revenue_billion'] == 2041
    assert result['tax_revenue_billion'] == 1887
    assert result['precision_kes'] == 1_000_000_000
    assert result['source']['page'] == 'Table 8, PDF p.21'
    assert 'not a split' in result['disclosure']


@pytest.mark.parametrize('field,bad', [
    ('page', 'Table 8, PDF p.22'), ('page', 'Table 9, PDF p.21'),
    ('table', 'Table 9: Government Fiscal Projections'),
    ('column', 'Actual'), ('column', 'Approved'),
])
def test_pinned_brop_locator_and_column_cannot_contradict_its_transcription(field, bad):
    row = brop_row()
    row.meta['tax_split_observation']['source'][field] = bad
    assert published_tax_observation(row) is None
