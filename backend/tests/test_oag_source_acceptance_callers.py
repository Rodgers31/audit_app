"""Actual native CLI+domain handler, controlled PDF identity/parser/IO seams.
These do not confer PDF source authority or pretend synthetic bytes are genuine.
"""
import json
from pathlib import Path
import pytest
from models import IngestionJob,SourceDocument
from seeding.native_report_authority import KEY
from seeding.domains.audits.scope import CATALOGUE_MANIFEST_SHA256
from seeding.domains import audits
from seeding.config import SeedingSettings
import test_audits_source_scope as old
from test_audits_source_scope import cli_harness,harness

MANIFEST=Path(__file__).resolve().parents[2] / 'docs/operations/2026-11-01-oag-catalogue-acceptance/manifest.json'
RAW=MANIFEST.read_bytes();ENTRIES=json.loads(RAW)['deferred_sources'];URLS=[e['source_url'] for e in ENTRIES]

def new_packet(monkeypatch,harness):
    monkeypatch.setattr(old,'SOURCES',ENTRIES)
    monkeypatch.setattr(old,'RAW',RAW)
    monkeypatch.setattr(old,'URLS',URLS)
    old.allow_controlled_bytes(monkeypatch,harness)


def test_actual_direct_handler_preserves_exact_new_four_source_receipt(harness,monkeypatch,tmp_path):
    new_packet(monkeypatch,harness)
    result=audits.run(harness['session'],SeedingSettings(audits_county_start_budget_seconds=1000,storage_path=tmp_path/'owned-receipts'),old.context(RAW))
    assert not result.errors
    assert len(harness['fetched'])==4 and set(harness['fetched'])==set(URLS)
    receipt=result.metadata['audit_source_scope']
    assert receipt['manifest_sha256']==CATALOGUE_MANIFEST_SHA256
    assert len(receipt['selected'])==4
    assert receipt['whole_world_coverage'] is False
    assert receipt['processed']==harness['fetched']
    for doc in harness['session'].query(SourceDocument):
        assert (doc.meta or {}).get(KEY,{}).get('audits') is None


def test_actual_cli_uses_exact_new_four_sources_without_claiming_authority(cli_harness,monkeypatch,tmp_path):
    import seeding.cli as cli
    harness,factory,settings=cli_harness;settings.storage_path=tmp_path/'owned-receipts';new_packet(monkeypatch,harness)
    assert cli.main(['seed','--domain','audits','--audits-source-manifest',str(MANIFEST)])==0
    assert len(harness['fetched'])==4 and set(harness['fetched'])==set(URLS)
    with factory() as read:
        job=read.query(IngestionJob).one();receipt=job.meta['audit_source_scope']
        assert receipt['manifest_sha256']==CATALOGUE_MANIFEST_SHA256
        assert receipt['whole_world_coverage'] is False
        assert len(receipt['selected'])==4
        assert receipt['processed']==harness['fetched']
        assert not job.meta.get('native_report_records',{}).get('audits')
        assert {d.url for d in read.query(SourceDocument)}==set(URLS)
        for doc in read.query(SourceDocument):assert (doc.meta or {}).get(KEY,{}).get('audits') is None


def test_actual_cli_modified_new_packet_refuses_before_any_job_source_or_io(cli_harness,tmp_path):
    import seeding.cli as cli
    harness,factory,settings=cli_harness
    value=json.loads(RAW);value['deferred_sources'][0]['sha256']='0'*64
    path=tmp_path/'changed-new-packet.json';path.write_text(json.dumps(value))
    assert cli.main(['seed','--domain','audits','--audits-source-manifest',str(path)])==1
    with factory() as read:
        assert read.query(IngestionJob).count()==read.query(SourceDocument).count()==0
    assert harness['fetched']==[]
