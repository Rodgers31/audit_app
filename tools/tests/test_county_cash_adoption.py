"""Focused source-bound whole-image and producer controls; fixtures passed explicitly."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("cash_adoption", Path(__file__).parents[1] / "prepare_county_cash_adoption.py")
adoption = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adoption)

@pytest.fixture
def inputs():
    base = os.environ.get("CASH_ADOPTION_CAPTURE")
    replay = os.environ.get("CASH_ADOPTION_REPLAY")
    catalog = os.environ.get("CASH_ADOPTION_CATALOG")
    if not all((base, replay, catalog)):
        pytest.skip("Explicit safe local capture, pinned producer replay and catalog required")
    return json.loads(Path(base).read_text()), json.loads(Path(replay).read_text()), json.loads(Path(catalog).read_text())

def plan(inputs):
    c,r,k = inputs
    out=adoption.bind_catalog(adoption.build_plan(c, r['records'], r['coverage'], c['completed_utc']), k)
    protected=json.loads(Path(os.environ["CASH_ADOPTION_PROTECTED"]).read_text())
    out=adoption.bind_protected(out,protected,adoption._digest(os.environ["CASH_ADOPTION_PROTECTED"]))
    triggers=json.loads(Path(os.environ["CASH_ADOPTION_TRIGGERS"]).read_text())
    return adoption.bind_triggers(out,triggers,adoption._digest(os.environ["CASH_ADOPTION_TRIGGERS"]))

def test_actual_producer_writer_delta_and_inverse(inputs):
    p=plan(inputs)
    assert len(p['inserts'])==40 and len(p['updates'])==6
    assert {r['subcategory'] for r in p['inserts'] if r['subcategory']=='Total'}=={'Total'}
    for update in p['updates']:
        assert {f for f in update['before'] if update['before'][f]!=update['after'][f]}=={'provenance'}
    for recovery in (False,True):
        sql=adoption.render_sql(p,recovery)
        assert sql.endswith('ROLLBACK;\n')
        assert 'nextval(' not in sql.split('DECLARE')[0]
        assert 'setval(' not in sql

@pytest.mark.parametrize('mutation', ['source_digest','source_id_bool','missing_budget_field',
    'accepted_cash_drift','protected_osr_drift','producer_annual_drift','producer_lost_county',
    'producer_withheld_promoted','duplicate_budget_key','missing_entity','catalog_missing_column',
    'catalog_wrong_sequence','catalog_wrong_sequence_type','extra_source_period'])
def test_bad_source_cohort_and_catalog_refuse(inputs,mutation):
    c,r,k=copy.deepcopy(inputs)
    if mutation=='source_digest': c['sources'][0]['metadata']['sha256']='0'*64
    elif mutation=='source_id_bool': c['sources'][0]['id']=True
    elif mutation=='missing_budget_field': c['budget_lines'][0].pop('validation_warnings')
    elif mutation=='accepted_cash_drift': next(x for x in c['budget_lines'] if x['category']=='Revenue Receipts')['actual_spent']+=1
    elif mutation=='protected_osr_drift': next(x for x in c['budget_lines'] if x['category']=='Own Source Revenue')['actual_spent']+=1
    elif mutation=='producer_annual_drift': r['records'][0]['quarter']='9M'
    elif mutation=='producer_lost_county': r['coverage'].pop('Baringo')
    elif mutation=='producer_withheld_promoted': r['coverage']['Kwale']['status']='reconciled'
    elif mutation=='duplicate_budget_key': c['budget_lines'].append(dict(c['budget_lines'][0],id=100000))
    elif mutation=='missing_entity': c['entities'].pop()
    elif mutation=='catalog_missing_column': k['columns'].pop()
    elif mutation=='catalog_wrong_sequence': k['budget_max'][0]['sequence']='public.unknown'
    elif mutation=='catalog_wrong_sequence_type': k['budget_sequence'][0]['is_called']=1
    elif mutation=='extra_source_period': k['other_source_lines']=[{'period_id':8}]
    with pytest.raises((ValueError,KeyError)):
        plan((c,r,k))

@pytest.mark.parametrize('field,value',[
    ('actual_spent',None),('actual_spent',0),('actual_spent',True),
    ('actual_spent','16154951221.00'),('actual_spent',16154951221),
    ('allocated_amount',False),('entity_id',3),('source_document_id',2395),
    ('period_id',8),('category','Own Source Revenue'),('page_ref',None),
    ('currency','USD')])
def test_renderer_refuses_insert_plan_tampering(inputs,field,value):
    p=plan(inputs);p['inserts'][0][field]=value
    with pytest.raises(ValueError,match='Plan was altered'):
        adoption.render_sql(p)

@pytest.mark.parametrize('table',['audits','budget_lines','source_documents'])
def test_renderer_refuses_incomplete_protected_scope(inputs,table):
    p=plan(inputs);p['protected_totals'].pop(table)
    with pytest.raises(ValueError,match='Incomplete protected15'):
        adoption.render_sql(p)


def test_direct_builder_refuses_fabricated_full_output(inputs):
    c,r,k=copy.deepcopy(inputs)
    next(x for x in r['records'] if x['county']=='Bungoma' and x['category']=='Revenue Receipts')['absorbed']='1'
    with pytest.raises(ValueError,match='reviewed pinned PDF replay'):
        adoption.build_plan(c,r['records'],r['coverage'],c['completed_utc'])


@pytest.mark.parametrize('section,field,value', [
    ('periods','start_date','2024-07-01T00:00:00'),
    ('periods','end_date','2025-06-30T00:00:00'),
    ('periods','country_id',2),('entities','type','MINISTRY'),
    ('entities','slug','wrong-county'),('entities','country_id',2)])
def test_source_period_and_county_identity_reject_bad_capture(inputs,section,field,value):
    c,r,k=copy.deepcopy(inputs);c[section][0][field]=value
    with pytest.raises(ValueError,match='identity'):
        adoption.build_plan(c,r['records'],r['coverage'],c['completed_utc'])
