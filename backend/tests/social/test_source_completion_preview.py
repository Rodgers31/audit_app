"""Preview must refuse the same unrenderable evidence as draft detection."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from social.generation.models import SourceCursor, SourceEvent
from social.generation.preview import preview
from social.models import SocialPost
from social.service import SocialError
from test_domain_support import db
from test_generation import configure, consume, observation


@pytest.mark.parametrize('state', ['baseline', 'unchanged', 'eligible_change'])
@pytest.mark.parametrize('unresolved', [True, False], ids=['unresolved', 'complete'])
def test_source_completion_preview_and_detection_agree(db, monkeypatch, state, unresolved):
    import seeding.source_observations as adapter

    configure(db)
    if state != 'baseline':
        assert consume(db, observation())['status'] == 'baseline'
    value = observation(
        version=2 if state == 'eligible_change' else 1,
        value='124.00' if state == 'eligible_change' else '123.45',
        title='[TODO complete source title]' if unresolved else 'County expenditure dataset',
    )
    monkeypatch.setattr(adapter, 'read_county_budget_observation', lambda *a, **kw: value)
    tables = (SourceCursor, SourceEvent, SocialPost)
    before = [db.scalar(select(func.count()).select_from(table)) for table in tables]
    db.rollback()
    result = preview(sessionmaker(bind=db.bind, expire_on_commit=False), dict(
        domain='counties_budget', record_ids=[1], ingestion_id=1, reports=False, backfill=False))
    item = result['results'][0]
    assert item['status'] == ('refused' if unresolved else state), result
    if unresolved:
        assert item['reason'] == 'unresolved_template'
        with pytest.raises(SocialError, match='UNRESOLVED_TEMPLATE'):
            consume(db, value)
        assert [db.scalar(select(func.count()).select_from(table)) for table in tables] == before
    else:
        actual = consume(db, value)['status']
        assert actual == ('draft_created' if state == 'eligible_change' else state)
