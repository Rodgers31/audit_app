"""Observable refusals and read-only previews; inert evidence is never live acceptance."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from test_domain_support import db
from test_api_admin import make_client
from test_generation import configure
from test_generation_integration import source
from seeding import generation_dispatch as bridge
from social.generation.integration import maybe_generate_committed
from social.generation.models import SourceCursor, SourceEvent
from social.models import SocialPost, SocialPublication, SocialCommandReceipt


def test_safe_projection_retains_known_reason_but_discards_diagnostic():
    from services.generation_outcome import safe_generation_outcome
    raw = bridge._result('completed', 'no_new_record_lineage')
    result = safe_generation_outcome({**raw, 'private': 'PRIVATE_DIAGNOSTIC'})
    assert result.get('reason') == 'no_new_record_lineage'
    assert 'PRIVATE_DIAGNOSTIC' not in str(result)


def test_unsupported_source_is_visible_without_source_scan(monkeypatch):
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    monkeypatch.setattr(bridge, '_record_outcome', lambda *args, **kwargs: None)
    def forbidden():
        raise AssertionError('Unsupported source entered evidence reader')
    result = bridge.dispatch_committed_generation(forbidden, domain='opendata', ingestion_id=1, dry_run=False)
    assert result is not None and result['reason'] == 'source_extracted_not_publication_qualified'


def test_refusals_have_safe_reason_counts(db, monkeypatch):
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    source(monkeypatch)
    configure(db)
    factory = sessionmaker(bind=db.bind, expire_on_commit=False)
    result = maybe_generate_committed(factory, record_ids=[2,3], ingestion_id=1)
    assert result['refused'] == 1 and result['baselines'] == 1
    assert result.get('refusal_reasons') == {'source_evidence_ineligible': 1}


def test_preview_is_private_and_has_no_durable_effects(db, monkeypatch):
    source(monkeypatch)
    client = make_client(db.bind)
    body = {'domain':'counties_budget','record_ids':[1,2], 'ingestion_id':1,'reports':False,'backfill':False}
    path = '/api/v1/admin/social/generation/preview'
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    assert [r['status'] for r in response.json()['results']] == ['baseline','refused']
    assert response.json()['drafts_enabled'] is False
    for model in (SourceCursor, SourceEvent, SocialPost, SocialPublication, SocialCommandReceipt):
        assert db.scalar(select(func.count()).select_from(model)) == 0
    assert make_client(db.bind,authenticated=False).post(path,json=body).status_code in {401,403}


def test_service_refusal_counts_and_continues_after_rollback(db, monkeypatch):
    from types import ModuleType
    import sys
    from test_generation import consume
    from test_report_generation import report_observation
    from social.generation.contracts import SourceObservation
    from social.generation.integration import maybe_generate_reports_committed
    from seeding.source_observations import SourceObservationUnavailable
    configure(db)
    consume(db, SourceObservation.model_validate(report_observation()))
    older = report_observation(2, published='2025-07-01', period='FY2024/25', end='2025-06-30')
    older['report']['period_start'] = '2024-07-01'
    valid = report_observation(2, published='2026-10-01', period='FY2026/27', end='2027-06-30')
    module = ModuleType('seeding.source_observations')
    module.SourceObservationUnavailable = SourceObservationUnavailable
    module.read_county_report_observation = lambda factory, **kw: older if kw['record_id'] == 1 else valid
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED','true')
    monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED','false')
    result = maybe_generate_reports_committed(sessionmaker(bind=db.bind, expire_on_commit=False), record_ids=[1,2], ingestion_id=2)
    assert result['processed'] == 2 and result['refused'] == 1 and result['drafts_created'] == 1
    assert result['refusal_reasons'] == {'report_release_regression':1}
    assert db.scalar(select(func.count()).select_from(SocialPost)) == 1


def test_preview_refuses_template_that_detection_cannot_render(db, monkeypatch):
    from test_generation import observation
    from social.generation.preview import preview
    module = source(monkeypatch)
    module.read_county_budget_observation = lambda *a, **kw: observation(title='[TODO]').model_dump(mode='json')
    value = preview(sessionmaker(bind=db.bind, expire_on_commit=False), {
        'domain':'counties_budget','record_ids':[1],'ingestion_id':1,'reports':False,'backfill':True})
    assert value['results'][0]['status'] == 'refused'
    assert value['results'][0]['reason'] == 'unresolved_template'
    assert db.scalar(select(func.count()).select_from(SourceCursor)) == 0


@pytest.mark.parametrize('bad', [[], True, 'bad', 1, {'execution_unverified':True,'confirmed':None}])
def test_malformed_timeout_summary_never_escapes_postcommit_receipt_boundary(monkeypatch, bad):
    monkeypatch.setattr(bridge,'_record_outcome',lambda *args,**kw:None)
    result = bridge.record_generation_timeout(object(),domain='counties_budget',ingestion_id=1,financial_outcome=bad)
    assert result['execution_unverified'] is True and result['processed'] is None


def test_preview_refuses_duplicate_report_series_without_saving(db,monkeypatch):
    from copy import deepcopy
    from types import ModuleType
    import sys
    from test_report_generation import report_observation
    from social.generation.preview import preview
    from seeding.source_observations import SourceObservationUnavailable
    module=ModuleType('seeding.source_observations')
    module.SourceObservationUnavailable=SourceObservationUnavailable
    def read(*args,record_id,**kw):
        value=deepcopy(report_observation())
        value['report']['source_record_id']=record_id
        return value
    module.read_county_report_observation=read
    monkeypatch.setitem(sys.modules,module.__name__,module)
    result=preview(sessionmaker(bind=db.bind,expire_on_commit=False),{
        'domain':'counties_budget','record_ids':[1,2],'ingestion_id':1,'reports':True,'backfill':True})
    assert all(r['status']=='refused' and r['reason']=='duplicate_source_series' for r in result['results'])
    assert db.scalar(select(func.count()).select_from(SourceCursor))==0


def test_capability_matrix_covers_native_domains_without_importing_them():
    from seeding.registries import _BUILTIN_DOMAIN_PACKAGES
    from seeding.generation_capabilities import CAPABILITIES
    assert set(CAPABILITIES)=={p.rsplit('.',1)[1] for p in _BUILTIN_DOMAIN_PACKAGES}|{'cra','opendata','county_borrowing'}
    assert {c.domain for c in CAPABILITIES.values() if c.financial or c.reports}=={'counties_budget','national_budget','revenue_by_source','audits'}
