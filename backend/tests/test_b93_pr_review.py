"""PR816 review regressions: typed refusals cannot become successful fallback."""
import argparse
from contextlib import nullcontext

import pytest
from sqlalchemy import select
from models import IngestionJob, IngestionStatus
from seeding import cli
from seeding.config import SeedingSettings
from seeding.domains import counties_budget as domain
from seeding.domains.counties_budget import fetcher
from seeding.pdf_parsers import CountyTableIncomplete
from seeding import freshness
from test_seeding_cli_budget import clock, sessionmaker_factory, _FakeRegistry


def test_recognized_report_refusal_never_loads_a_fixture(monkeypatch,tmp_path):
    error=CountyTableIncomplete('owned inconsistent caption boundary')
    def refuse(*args):raise error
    fixture_calls=[]
    monkeypatch.setattr(fetcher,'_fetch_from_cob_county_pdf',refuse)
    monkeypatch.setattr(fetcher,'load_json_resource',lambda **kwargs:fixture_calls.append(kwargs) or [])
    freshness.reset('counties_budget')
    with pytest.raises(CountyTableIncomplete) as caught:
        fetcher.fetch_budget_payload(object(),SeedingSettings(log_path=tmp_path/'seed.log'))
    assert caught.value is error and fixture_calls==[]
    assert freshness.get('counties_budget')['mode']=='refused'
    assert freshness.get('counties_budget')['reason']=='county_report_incomplete'


def test_parser_refusal_survives_native_cli_as_an_error_record(clock,sessionmaker_factory,monkeypatch,tmp_path):
    def refuse(*args):raise CountyTableIncomplete('owned inconsistent caption boundary')
    fixture_calls=[]
    monkeypatch.setattr(domain,'create_http_client',lambda *a:nullcontext(object()))
    monkeypatch.setattr(fetcher,'_fetch_from_cob_county_pdf',refuse)
    monkeypatch.setattr(fetcher,'load_json_resource',lambda **kwargs:fixture_calls.append(kwargs) or [])
    monkeypatch.setattr(cli,'REGISTRY',_FakeRegistry({'counties_budget':domain.run}))
    args=argparse.Namespace(domain=['counties_budget'],all=False,dry_run=False,since=None)
    cli.run_seed_command(args,SeedingSettings(log_path=tmp_path/'seed.log'))
    with sessionmaker_factory() as db:
        job=db.scalars(select(IngestionJob)).one()
        assert job.status==IngestionStatus.COMPLETED_WITH_ERRORS
        assert job.meta['source_mode']=='refused'
        assert job.meta['source_fallback_reason']=='county_report_incomplete'
        assert any('owned inconsistent caption boundary' in error for error in job.errors)
        assert (job.items_processed,job.items_created,job.items_updated)==(0,0,0)
        assert fixture_calls==[]


@pytest.mark.parametrize('review,expected',[(None,0),('oag-2542-20261026',1),('unknown-review',1)])
def test_empty_cli_selection_refuses_any_explicit_review(monkeypatch,tmp_path,review,expected):
    monkeypatch.setattr(cli,'load_builtin_domains',lambda:None)
    monkeypatch.setattr(cli,'REGISTRY',_FakeRegistry({}))
    monkeypatch.setattr(cli,'_ensure_db_sessionlocal',lambda:pytest.fail('empty selection must not access database'))
    args=argparse.Namespace(domain=None,all=False,dry_run=False,since=None,audits_reconciliation_review=review)
    assert cli.run_seed_command(args,SeedingSettings(log_path=tmp_path/'seed.log'))==expected
