"""Destinations for qualified draft sources; evidence URLs remain original."""
from importlib import import_module
from urllib.parse import quote, urlencode

from ..service import SocialError
from .contracts import SourceObservation


def draft_destination(db, observation, *, template_version=None):
    observation = SourceObservation.model_validate(observation.model_dump(mode='python'))
    # A saved revision keeps its reviewed destination contract. New report copy
    # points at its qualified document rather than an unrelated default year.
    from .service import generator_metadata
    selected = generator_metadata(observation, template_version=template_version)['template_version']
    if selected in ('report-availability-v3', 'catalogue-availability-v3'):
        return observation.report.document_url
    if selected == 'financial-v4':
        return observation.facts[0].document_url

    financial = observation.financial
    if selected == 'financial-v3' and financial and financial.native_domain == 'pending_bills' and observation.facts[0].metric == 'Reported pending bills: county':
        models = import_module('backend.models' if __package__.startswith('backend.') else 'models')
        loan = db.get(models.Loan, financial.record_id, populate_existing=True)
        entity = db.get(models.Entity, loan.entity_id, populate_existing=True) if loan else None
        if (entity is None or entity.type != models.EntityType.COUNTY or not entity.slug
                or entity.canonical_name != observation.facts[0].entity):
            raise SocialError('SOURCE_REVIEW_REQUIRED', 'The qualified county destination is unavailable.', 422)
        query = urlencode({'tab': 'budget', 'as_at': financial.period_end.isoformat()})
        return f'https://www.auditgava.com/counties/{quote(entity.slug, safe="")}?{query}#pending-bills'
    return (observation.report or observation.facts[0]).canonical_url
