from types import SimpleNamespace
import pytest
from social.generation.destination import draft_destination
from social.service import SocialError
from test_financial_copy import financial
from models import EntityType


def reader(*, slug='nairobi-county', name='Nairobi County', kind=EntityType.COUNTY):
    class Reader:
        def get(self, model, key, **kwargs):
            if model.__name__ == 'Loan':
                assert key == 1
                return SimpleNamespace(entity_id=71)
            assert model.__name__ == 'Entity' and key == 71
            return SimpleNamespace(slug=slug, canonical_name=name, type=kind)
    return Reader()


def test_county_link_uses_actual_entity_slug_and_source_day_without_rewriting_evidence():
    source=financial(); before=source.model_dump(mode='json')
    assert draft_destination(reader(),source,template_version='financial-v3')=='https://www.auditgava.com/counties/nairobi-county?tab=budget&as_at=2026-06-30#pending-bills'
    assert source.model_dump(mode='json')==before


@pytest.mark.parametrize('change',[{'slug':None},{'name':'Mombasa County'},{'kind':EntityType.NATIONAL}])
def test_unavailable_county_identity_cannot_be_replaced_by_a_generic_debt_link(change):
    with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
        draft_destination(reader(**change),financial(),template_version='financial-v3')


@pytest.mark.parametrize('domain',['national_budget','revenue_by_source'])
def test_national_financial_link_selects_auditgava_evidence_and_retains_saved_destinations(domain):
    source=financial(domain);before=source.model_dump(mode='json')
    assert draft_destination(None,source).startswith('https://www.auditgava.com/reports/'+domain+'/')
    assert draft_destination(None,source,template_version='financial-v4')==source.facts[0].document_url
    for version in ('factual-v1','financial-v2','financial-v3'):
        assert draft_destination(None,source,template_version=version)==source.facts[0].canonical_url
    assert source.model_dump(mode='json')==before


def test_new_county_pending_bills_destination_binds_meaning_not_just_the_date():
    source=financial();url=draft_destination(None,source)
    assert url.startswith('https://www.auditgava.com/reports/pending_bills/') and 'snapshot=' in url
    raw=source.model_dump(mode='json');raw['facts'][0]['value']='12'
    from social.generation.contracts import SourceObservation
    assert draft_destination(None,SourceObservation.model_validate(raw))!=url
