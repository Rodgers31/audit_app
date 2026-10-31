from decimal import Decimal

import pytest

from seeding.domains.national_budget.headline import (
    extract_overall_budget_billion_from_text,
    extract_total_revenue_billion_from_text,
)


@pytest.mark.parametrize('text', [
    'This represents 17 per cent of the revised gross national budget and '
    '30 per cent of the revised gross ministerial budget of Kshs.2.93 billion.',
    'The revised gross budget for FY 2025/26 amounted to KSh 5.27 trillion.',
    'The overall budget remained under review. Revenue amounted to KSh 2.45 trillion.',
    'The ministerial gross budget amounted to KSh 2.93 trillion.',
])
def test_other_subjects_cannot_supply_the_original_national_budget(text):
    assert extract_overall_budget_billion_from_text(text) is None


def test_revenue_does_not_take_the_next_subjects_amount():
    assert extract_total_revenue_billion_from_text(
        'Total revenue remained under review. Expenditure was KSh 3.4 trillion.'
    ) is None


@pytest.mark.parametrize('subject,verb', [
    ('original gross budget for FY 2025/26', 'amounts to'),
    ('gross national budget', 'was'),
    ('approved budget', 'of'),
])
def test_unambiguous_budget_subject_still_reads_its_own_amount(subject, verb):
    assert extract_overall_budget_billion_from_text(
        f'The {subject} {verb} KSh 4.69 trillion, compared to KSh 5.0 trillion previously.'
    ) == Decimal('4690.00')
