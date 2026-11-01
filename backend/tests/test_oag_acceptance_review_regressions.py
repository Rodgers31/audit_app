"""Review regressions for real evidence and source-only child execution."""
from copy import deepcopy
from itertools import product

import pytest

from test_oag_auxiliary_evidence import world, finding
from test_oag_source_acceptance_plan import execute


@pytest.mark.parametrize('field,bad', [
    ('finding_text', None), ('finding_text', ''), ('finding_text', ' \n\t'),
    ('finding_text', True), ('finding_text', ['finding']),
    ('finding_text', '\u00a0\u2003\u2028'), ('finding_text', '\x1c\x85\u3000'),
    ('entity_name', None), ('entity_name', ''), ('entity_name', ' \t\r'),
    ('entity_name', {'county': 'Nairobi'}),
    ('entity_name', '\u00a0\u2003\u2028'), ('entity_name', '\x1c\x85\u3000'),
    ('severity', None), ('severity', ''), ('severity', 'UNKNOWN'),
])
def test_scope_refuses_findings_without_loader_required_content(world, field, bad):
    from seeding.domains.audits.scope import verify_extraction_evidence, AuditSourceScopeError
    session, doc, entry = world
    row = finding(session, doc, entry)
    row.extracted_json = {**row.extracted_json, 'entity_name': 'County Assembly of Nairobi',
                          'finding_text': 'Actual attributed finding.', 'severity': 'WARNING', field: bad}
    session.flush()
    with pytest.raises(AuditSourceScopeError):
        verify_extraction_evidence(session, doc, entry)


def test_positive_counts_cannot_certify_schema_only_finding(world):
    from seeding.domains.audits.scope import verify_extractions, AuditSourceScopeError
    session, doc, entry = world
    row = finding(session, doc, entry)
    row.extracted_json = {k: row.extracted_json[k] for k in ('schema', 'fiscal_year', 'volume_kind')}
    session.flush()
    with pytest.raises(AuditSourceScopeError):
        verify_extractions(session, doc, entry, {'created': 0, 'skipped': 1})


CONTROLS = ('SOCIAL_GENERATION_HOOK_ENABLED', 'SOCIAL_REPORT_GENERATION_ENABLED',
            'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED')


@pytest.mark.parametrize('values', list(product(('true', 'false'), repeat=4)) + [('TRUE', '1', 'yes', '')])
def test_acceptance_child_forces_all_generation_and_source_admission_off(monkeypatch, values):
    import os
    for flag, value in zip(CONTROLS, values):
        monkeypatch.setenv(flag, value)
    result, calls = execute(monkeypatch)
    assert result == 0 and len(calls) == 1
    child = calls[0][1]['env']
    assert {flag: child[flag] for flag in CONTROLS} == dict.fromkeys(CONTROLS, 'false')
    assert {flag: os.environ[flag] for flag in CONTROLS} == dict(zip(CONTROLS, values))


@pytest.mark.parametrize('field,bad', [('listed_at', 'https://unreviewed.invalid/'),
                                     ('listed_at', None), ('pdf_pages', 1), ('pdf_pages', True)])
def test_legacy_receipt_refuses_changed_listing_or_page_context(field, bad):
    from seeding.domains.audits.observation import accepted_editions
    from seeding.domains.audits.scope import receipt_for, AuditSourceScopeError
    entries = deepcopy(list(accepted_editions().values())[3:])
    entries[0][field] = bad
    with pytest.raises(AuditSourceScopeError):
        receipt_for(entries)
