"""Release chronology rejects regression without suppressing human corrections."""
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from social.generation.contracts import SourceObservation
from social.generation.models import SourceCursor
from social.service import SocialError
from test_domain_support import db
from test_generation import configure, consume
from test_report_generation import report_observation


def test_report_release_cannot_regress_only_period_start(db):
    configure(db)
    consume(db, SourceObservation.model_validate(report_observation()), backfill=True)
    value = report_observation(2, published='2026-08-01', document=2, digest='b')
    value['report']['period_start'] = '2024-07-01'
    with pytest.raises(SocialError, match='REPORT_RELEASE_REGRESSION'):
        consume(db, SourceObservation.model_validate(value))


def test_same_period_human_review_correction_is_still_a_draft(db):
    configure(db)
    consume(db, SourceObservation.model_validate(report_observation()), backfill=True)
    value = report_observation(2, published='2026-08-01', document=2, digest='b')
    result = consume(db, SourceObservation.model_validate(value))
    assert result['status'] == 'draft_created'


@pytest.mark.parametrize('field,value', [('period_start',''), ('period_end',''), ('published_on',''),
    ('release_hash',''), ('period_start',True), ('period_start','2024-13-40'),
    ('period_start','20250701'), ('period_start','2028-07-01'), ('period_end',None)])
def test_malformed_durable_release_baseline_cannot_certify_a_draft(db, field, value):
    configure(db)
    consume(db, SourceObservation.model_validate(report_observation()), backfill=True)
    cursor = db.scalar(select(SourceCursor))
    cursor.report_state = dict(cursor.report_state, **{field:value})
    db.commit()
    candidate = report_observation(2, published='2026-08-01', document=2, digest='b')
    with pytest.raises(SocialError, match='EVIDENCE_INTEGRITY_FAILED'):
        consume(db, SourceObservation.model_validate(candidate))
