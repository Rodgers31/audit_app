"""Destinations for qualified draft sources; evidence URLs remain original."""
from importlib import import_module
from urllib.parse import quote, urlencode

from ..service import SocialError


def draft_destination(db, observation):
    financial = observation.financial
    if financial and financial.native_domain == 'pending_bills' and observation.facts[0].metric == 'Reported pending bills: county':
        models = import_module('backend.models' if __package__.startswith('backend.') else 'models')
        loan = db.get(models.Loan, financial.record_id, populate_existing=True)
        entity = db.get(models.Entity, loan.entity_id, populate_existing=True) if loan else None
        if (entity is None or entity.type != models.EntityType.COUNTY or not entity.slug
                or entity.canonical_name != observation.facts[0].entity):
            raise SocialError('SOURCE_REVIEW_REQUIRED', 'The qualified county destination is unavailable.', 422)
        query = urlencode({'tab': 'budget', 'as_at': financial.period_end.isoformat()})
        return f'https://www.auditgava.com/counties/{quote(entity.slug, safe="")}?{query}#pending-bills'
    return (observation.report or observation.facts[0]).canonical_url
