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
    assert draft_destination(reader(),source)=='https://www.auditgava.com/counties/nairobi-county?tab=budget&as_at=2026-06-30#pending-bills'
    assert source.model_dump(mode='json')==before


@pytest.mark.parametrize('change',[{'slug':None},{'name':'Mombasa County'},{'kind':EntityType.NATIONAL}])
def test_unavailable_county_identity_cannot_be_replaced_by_a_generic_debt_link(change):
    with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
        draft_destination(reader(**change),financial())


def test_other_domains_keep_their_existing_canonical_destination():
    source=financial('revenue_by_source')
    assert draft_destination(None,source)==source.facts[0].canonical_url
