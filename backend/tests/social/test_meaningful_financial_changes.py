"""Business changes, including corrections, are independent of source layout."""
from copy import deepcopy
import pytest
from social.generation.contracts import SourceObservation
from social.generation.service import semantic_fingerprint
from test_generation import observation, configure, consume
from test_domain_support import db


@pytest.mark.parametrize('changes', [
    {'document_checksum': 'b'*64}, {'locator': 'page 99, repaginated'},
    {'source_document_id': 99}, {'document_url': 'https://example.gov/reissued.pdf'},
    {'published_on': '2026-01-02'}, {'publisher': 'Controller of Budget (official)'},
    {'value': '123.4500'},
])
def test_financial_fingerprint_excludes_provenance_and_decimal_spelling(changes):
    first = observation()
    raw = first.model_dump(mode='json')
    raw['facts'][0].update(changes)
    raw.update(evidence_version=2, ingestion_id='job:43', title='Refreshed source title')
    assert semantic_fingerprint(first) == semantic_fingerprint(SourceObservation.model_validate(raw))


@pytest.mark.parametrize('field,value', [('value','124'), ('period','FY2024/25'),
    ('comparison_basis','Revised estimate'), ('classification','projected'),
    ('unit','USD'), ('scale','billions'), ('entity','Another county'), ('metric','Another metric')])
def test_business_value_and_scope_changes_are_meaningful(field,value):
    first = observation()
    raw = first.model_dump(mode='json'); raw['facts'][0][field] = value
    assert semantic_fingerprint(first) != semantic_fingerprint(SourceObservation.model_validate(raw))


def test_metadata_refresh_then_correction_creates_one_pending_draft(db):
    configure(db)
    first = observation()
    assert consume(db,first)['status']=='baseline'
    raw=first.model_dump(mode='json');raw.update(evidence_version=2,ingestion_id='job:43')
    raw['facts'][0].update(document_checksum='b'*64, locator='repaginated page 13')
    assert consume(db,SourceObservation.model_validate(raw))['status']=='unchanged'
    raw.update(evidence_version=3,ingestion_id='job:44');raw['facts'][0]['value']='125.00'
    result=consume(db,SourceObservation.model_validate(raw))
    assert result['status']=='draft_created' and result['sequence']==1
    assert consume(db,SourceObservation.model_validate(raw))['status']=='unchanged'


@pytest.mark.parametrize('marker', [{}, False, [], {'financial_semantics':True},
    {'financial_semantics':2.0}, {'financial_semantics':2,'unknown':True}])
def test_unknown_financial_cursor_state_is_not_a_legacy_baseline(marker):
    from types import SimpleNamespace
    from social.generation.service import prior_financial_fingerprint, legacy_fingerprint
    from social.service import SocialError
    value=observation(2)
    cursor=SimpleNamespace(report_state=marker,fingerprint=legacy_fingerprint(value))
    with pytest.raises(SocialError,match='EVIDENCE_INTEGRITY_FAILED'):
        prior_financial_fingerprint(value,cursor,None)
