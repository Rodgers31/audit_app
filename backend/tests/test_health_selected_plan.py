"""Run the actual health shell with an inert curl transport observation."""
import os
from pathlib import Path
import subprocess
import json
from urllib.parse import urlsplit,parse_qsl

import yaml
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _inventory_env(tmp_path, inventory):
    path = tmp_path/'seed-health-inventory'
    path.write_text(inventory + '\n')
    path.chmod(0o600)
    return {'RUNNER_TEMP': str(tmp_path)}


@pytest.mark.parametrize('inventory', [
    'county_officials governors|reference|false',
    'unknown|reference|false',
    'required|https://example.invalid|true\nrequired|https://example.invalid|true',
])
def test_health_shell_rejects_reference_disguise_and_duplicate_inputs(tmp_path, inventory):
    script = next(s['run'] for s in yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())['jobs']['healthcheck']['steps'] if s.get('id') == 'check')
    curl = tmp_path/'curl'; curl.write_text('#!/bin/sh\nprintf 200\n'); curl.chmod(0o755)
    proc = subprocess.run(['bash','-eo','pipefail','-c',script],cwd=ROOT,text=True,capture_output=True,timeout=10,
        env={'PATH':str(tmp_path)+':'+os.environ['PATH'],**_inventory_env(tmp_path, inventory),
             'GITHUB_OUTPUT':str(tmp_path/'output'),'GITHUB_STEP_SUMMARY':str(tmp_path/'summary')})
    assert proc.returncode != 0, proc.stdout+proc.stderr


@pytest.mark.parametrize('legacy', [False, True])
def test_health_issue_with_other_unrecovered_scope_is_not_closed(legacy):
    doc = yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())
    scripts = {s['name']:s.get('with',{}).get('script') for s in doc['jobs']['notify']['steps'] if 'name' in s}
    program = r'''
const input=JSON.parse(process.argv[1]);const state={issues:[],comments:[],calls:[]};
if(input.legacy)state.issues.push({number:17,state:'open',body:'Older outage; source scope not recorded'});
const github={rest:{issues:{
 async listForRepo(a){return {data:JSON.parse(JSON.stringify(state.issues.filter(x=>x.state==='open')))};},
 async create(a){state.issues.push({...a,number:17,state:'open'});return {data:{number:17}};},
 async createComment(a){state.comments.push(a);return {data:{id:1}};},
 async update(a){Object.assign(state.issues.find(x=>x.number===a.issue_number),a);state.calls.push(a);return {data:{}};}
}}};
const context={repo:{owner:'fixture',repo:'fixture'},serverUrl:'https://github.com',runId:101};
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
async function run(script,plan,inventory){process.env.HEALTH_PLAN=plan.repeat(64);process.env.HEALTH_INVENTORY=inventory.repeat(64);process.env.HEALTH_REPORT='CRITICAL|source|404';await new AsyncFunction('github','context',script)(github,context);context.runId++;}
(async()=>{await run(input.failure,'a','1');if(!input.legacy)await run(input.failure,'b','2');await run(input.recovery,'a','1');console.log(JSON.stringify(state));})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    proc = subprocess.run(['node','-e',program,json.dumps({'failure':scripts['Create issue on URL health-check failure'],
        'recovery':scripts['Auto-close resolved health-check issues'],'legacy':legacy})],cwd=ROOT,capture_output=True,text=True,timeout=10,
        env={'PATH':os.environ['PATH']})
    assert proc.returncode == 0,proc.stderr
    assert json.loads(proc.stdout.splitlines()[-1])['issues'][0]['state'] == 'open',proc.stdout


@pytest.mark.parametrize('domain,path', [
    ('economic_indicators','https://www.centralbank.go.ke/inflation-rates/'),
    ('revenue_by_source','https://www.kra.go.ke/news-center/press-release'),
    ('population','https://api.worldbank.org/v2/country/KEN/indicator/SP.POP.TOTL'),
    ('national_gdp','https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN'),
])
def test_selected_component_inventory_includes_actual_fetcher_endpoint(domain,path):
    from seeding.source_plan import SourcePlan,health_source_lines
    urls = [line.split('|')[1] for line in health_source_lines(SourcePlan((domain,),False,False)).splitlines()]
    assert any(url.split('?')[0] == path for url in urls),urls


def test_unused_optional_brop_fallback_does_not_block_planning():
    from seeding.source_plan import SourcePlan,health_source_lines
    from seeding.config import SeedingSettings
    inventory = health_source_lines(SourcePlan(('pending_bills',),False,False),SeedingSettings(treasury_brop_url=None))
    assert 'Treasury actuals' in inventory


@pytest.mark.parametrize('links', [True, False])
def test_actual_health_shell_discovers_historical_editions_or_reports_missing(tmp_path, links):
    doc = yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())
    script = next(s['run'] for s in doc['jobs']['healthcheck']['steps'] if s.get('id') == 'check')
    urls = [
        'https://oldsite.treasury.go.ke/wp-content/uploads/2025/06/Budget-Summary-for-the-FY-2025-26F.pdf',
        'https://oldsite.treasury.go.ke/wp-content/uploads/2025/03/Budget-Summary-for-the-FY-2024-25.pdf',
    ]
    listing = tmp_path/'listing'
    listing.write_text(''.join(f'<a href="{url}">Budget Summary</a>' for url in urls) if links else '<p>No edition links</p>')
    calls = tmp_path/'calls'
    curl = tmp_path/'curl'
    curl.write_text('''#!/bin/sh
body=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = -o ]; then shift; body=$1; fi
  url=$1; shift
done
printf '%s\\n' "$url" >> "$HEALTH_TEST_CALLS"
case "$url" in
 *oldsite*) printf 000; exit 60 ;;
 *) cp "$HEALTH_TEST_LISTING" "$body"; printf 200 ;;
esac
''')
    curl.chmod(0o755)
    output = tmp_path/'output'
    proc = subprocess.run(['bash','-eo','pipefail','-c',script],cwd=ROOT,text=True,capture_output=True,timeout=10,
        env={'PATH':str(tmp_path)+':'+os.environ['PATH'],**_inventory_env(tmp_path,
             'fiscal_summary framework|https://www.treasury.go.ke/budget-summary-revenue-expenditure|true|treasury_editions'),
             'HEALTH_TEST_CALLS':str(calls),'HEALTH_TEST_LISTING':str(listing),
             'GITHUB_OUTPUT':str(output),'GITHUB_STEP_SUMMARY':str(tmp_path/'summary')})
    assert proc.returncode == 0,proc.stderr
    assert 'has_failures=true' in output.read_text() and 'critical_reachable=false' in output.read_text()
    if links:
        assert all(calls.read_text().splitlines().count(url) == 1 for url in urls),calls.read_text()
        assert 'TLS certificate verification failed' in output.read_text()
    else:
        assert 'required diagnostic coverage unavailable' in output.read_text()


def test_native_prior_step_inventory_covers_every_preceding_workflow_step():
    from seeding.current_run import PRIOR_STEPS
    steps = yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())['jobs']['seed']['steps']
    before = steps[:next(i for i,s in enumerate(steps) if s.get('id') == 'results')]
    assert all('id' in step for step in before)
    assert {s['id'] for s in before} == PRIOR_STEPS


@pytest.mark.parametrize('raw', ['', '{}', '[]', 'null', '{bad',
    '{"checkout":{"outcome":"success"},"checkout":{"outcome":"failure"}}'])
def test_environment_prior_step_reader_never_upgrades_bad_json(raw, monkeypatch):
    from seeding.current_run import environment_context,prior_steps_success
    from seeding.source_plan import SourcePlan
    monkeypatch.setenv('SEED_PRIOR_STEPS',raw)
    monkeypatch.setenv('SEED_PRIOR_JOB_STATUS','success')
    context = environment_context()
    assert not prior_steps_success(context['prior_steps'],context['prior_job_status'],SourcePlan(('population',),False,False))


@pytest.mark.parametrize('payload', [
    "URL = 'https://example.invalid/one'\nURL = 'https://example.invalid/two'\n",
    'URL = True\n', 'URL = 1\n', 'URL = 1e999\n',
    "URL = str('https://example.invalid')\n", '',
])
def test_literal_reader_refuses_ambiguous_nonliteral_or_wrong_typed_sources(tmp_path,monkeypatch,payload):
    from seeding import source_plan
    root=tmp_path/'source';path=root/'domains/cra/source.py';path.parent.mkdir(parents=True)
    path.write_text(payload)
    monkeypatch.setattr(source_plan,'_SOURCE_ROOT',root)
    with pytest.raises((ValueError,SyntaxError)):
        source_plan.source_literals('domains/cra/source.py')


def test_literal_reader_never_executes_domain_code(tmp_path,monkeypatch):
    from seeding import source_plan
    root=tmp_path/'source';path=root/'domains/cra/source.py';path.parent.mkdir(parents=True)
    path.write_text("raise RuntimeError('provider import must not run')\nURL = 'https://example.invalid/edition.pdf'\n")
    monkeypatch.setattr(source_plan,'_SOURCE_ROOT',root)
    assert source_plan.source_literals('domains/cra/source.py')['URL']=='https://example.invalid/edition.pdf'
    with pytest.raises(ValueError,match='Unknown'):
        source_plan.source_literals('../../outside.py')


def test_all_selected_plan_validation_has_no_database_import(tmp_path):
    output=tmp_path/'output';output.touch()
    program="""
import builtins,runpy,sys
original=builtins.__import__
def guarded(name,*args,**kwargs):
 if name=='database':raise RuntimeError('database import before admission')
 return original(name,*args,**kwargs)
builtins.__import__=guarded
sys.argv=['source_plan','--check']
runpy.run_module('seeding.source_plan',run_name='__main__')
"""
    proc=subprocess.run([__import__('sys').executable,'-c',program],cwd=ROOT,text=True,capture_output=True,timeout=15,
        env={'PATH':os.environ['PATH'],'PYTHONPATH':str(ROOT/'backend'),'PYTHONDONTWRITEBYTECODE':'1',
             'PYTHON_DOTENV_DISABLED':'1','DATABASE_URL':'inert-invalid-driver://no-network','GITHUB_OUTPUT':str(output),
             'SEED_PLAN_EVENT':'workflow_dispatch','SEED_PLAN_DOMAIN':'all'})
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert set(line.split('=', 1)[0] for line in output.read_text().splitlines()) == {'domains', 'bootstrap'}


def test_optional_settings_do_not_break_unrelated_selection_and_queries_are_well_formed():
    from seeding.source_plan import SourcePlan,health_source_lines
    from seeding.config import SeedingSettings
    settings=SeedingSettings(kra_revenue_url='https://www.kra.go.ke/reviewed-release')
    assert len(health_source_lines(SourcePlan(('county_officials',),False,False),settings).splitlines())==2
    urls=[line.split('|')[1] for line in health_source_lines(SourcePlan(('national_gdp',),False,False),settings).splitlines()]
    for url in urls:
        keys=[k for k,v in parse_qsl(urlsplit(url).query)]
        assert url.count('?')<=1 and len(keys)==len(set(keys)),url


def test_disabled_national_population_still_probes_the_non_dry_run_census():
    from seeding.source_plan import SourcePlan,health_source_lines
    from seeding.config import SeedingSettings
    settings=SeedingSettings(live_pdf_fetch_enabled=False,enrich_with_worldbank=False)
    lines=health_source_lines(SourcePlan(('population',),False,False),settings).splitlines()
    assert any('county census edition' in line and '.pdf|' in line for line in lines)
    assert any('|missing|true' in line for line in lines)
    assert not any('api.worldbank.org' in line for line in lines)


def test_real_native_imf_call_inventory_is_covered():
    from seeding.source_plan import SourcePlan,health_source_lines
    from seeding.config import SeedingSettings
    from seeding.domains.imf_weo.fetcher import fetch_imf_weo
    class Client:
        def __init__(self):self.calls=[]
        def get(self,url,**kwargs):
            self.calls.append(url)
            class Response:
                def raise_for_status(self):pass
                def json(self):return {}
            return Response()  # Inert body; only the actual call inventory is asserted.
    client=Client()
    fetch_imf_weo(client,SeedingSettings())
    urls={line.split('|')[1] for line in health_source_lines(SourcePlan(('imf_weo',),False,False)).splitlines()}
    assert len(client.calls)==4 and set(client.calls)<=urls


@pytest.mark.parametrize('mutation', [
    "(SOURCE_URL, other) = ('https://example.invalid/new', 1)",
    "[SOURCE_URL] = ['https://example.invalid/new']",
    "(SOURCE_URL := 'https://example.invalid/new')",
    "for SOURCE_URL in ['https://example.invalid/new']: pass",
    'del SOURCE_URL',
    'def SOURCE_URL(): pass',
    'class SOURCE_URL: pass',
    "globals()['SOURCE_URL'] = 'https://example.invalid/new'",
])
def test_source_literal_rebinding_cannot_certify_stale_urls(tmp_path,monkeypatch,mutation):
    from seeding import source_plan
    root=tmp_path/'source';path=root/'extractors/cog_governors.py';path.parent.mkdir(parents=True)
    code="SOURCE_URL='https://example.invalid/old'\nDEPUTIES_SOURCE_URL='https://example.invalid/deputies'\n"+mutation+'\n'
    namespace={};exec(code,namespace)
    assert namespace.get('SOURCE_URL')!='https://example.invalid/old'
    path.write_text(code);monkeypatch.setattr(source_plan,'_SOURCE_ROOT',root)
    with pytest.raises(ValueError):source_plan.source_literals('extractors/cog_governors.py')


@pytest.mark.parametrize('mutation', [
    '_WB_POPULATION_INDICATORS.clear()',
    "_WB_POPULATION_INDICATORS.update({'SP.POP.NEW':'new'})",
    "_WB_POPULATION_INDICATORS['SP.POP.NEW']='new'",
])
def test_source_literal_table_mutation_is_not_a_static_contract(tmp_path,monkeypatch,mutation):
    from seeding import source_plan
    root=tmp_path/'source';path=root/'domains/population/fetcher.py';path.parent.mkdir(parents=True)
    path.write_text("_WB_BASE='https://example.invalid'\n_WB_POPULATION_INDICATORS={'SP.POP.TOTL':'total_population'}\n_WB_SUPPLEMENTARY={'SP.POP.GROW':'growth'}\n"+mutation+'\n')
    monkeypatch.setattr(source_plan,'_SOURCE_ROOT',root)
    with pytest.raises(ValueError):source_plan.source_literals('domains/population/fetcher.py')


@pytest.mark.parametrize('table', ['{}', "{'SP.POP.TOTL':True}", "{'SP.POP.TOTL':1}", "{'SP.POP.TOTL':None}"])
def test_empty_or_wrong_nested_source_tables_are_not_coverage(tmp_path,monkeypatch,table):
    from seeding import source_plan
    root=tmp_path/'source';path=root/'domains/population/fetcher.py';path.parent.mkdir(parents=True)
    path.write_text("_WB_BASE='https://example.invalid'\n_WB_POPULATION_INDICATORS="+table+"\n_WB_SUPPLEMENTARY={'SP.POP.GROW':'growth'}\n")
    monkeypatch.setattr(source_plan,'_SOURCE_ROOT',root)
    with pytest.raises(ValueError):source_plan.source_literals('domains/population/fetcher.py')


def test_health_uses_only_the_selected_component_inventory(tmp_path):
    doc = yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())
    script = next(s['run'] for s in doc['jobs']['healthcheck']['steps'] if s.get('id') == 'check')
    curl = tmp_path/'curl'
    curl.write_text('#!/bin/sh\nprintf 200\n')
    curl.chmod(0o755)
    output = tmp_path/'output'
    result = subprocess.run(['bash','-eo','pipefail','-c',script], cwd=ROOT,
        env={'PATH':str(tmp_path)+':'+os.environ['PATH'],
            **_inventory_env(tmp_path, 'county_officials governors|https://cog.go.ke/current-governors/|true'),
            'GITHUB_OUTPUT':str(output), 'GITHUB_STEP_SUMMARY':str(tmp_path/'summary')},
        text=True,capture_output=True,timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'county_officials governors' in result.stdout
    assert 'Total: 1 | OK: 1' in result.stdout
    assert 'OAG' not in result.stdout and 'CBK' not in result.stdout


def test_scheduled_health_probes_configured_url_without_publishing_it(tmp_path):
    import sys

    workflow = yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())
    plan_job = workflow['jobs']['source_plan']
    health_job = workflow['jobs']['healthcheck']
    plan = next(s for s in plan_job['steps'] if s.get('id') == 'plan')
    output, summary, calls = (tmp_path/name for name in ('output', 'summary', 'calls'))
    output.touch()
    runner = tmp_path/'runner'
    runner.mkdir()
    private_url = 'https://private-source.invalid/feed?token=fixture-secret-17'
    env = {
        'PATH': f'{tmp_path}:{Path(sys.executable).parent}:{os.defpath}',
        'RUNNER_TEMP': str(runner), 'GITHUB_OUTPUT': str(output),
        'GITHUB_STEP_SUMMARY': str(summary), 'HEALTH_TEST_CALLS': str(calls),
        'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'SEED_PLAN_EVENT': 'schedule', 'SEED_PLAN_SCHEDULE': '0 2 * * 1-6',
        'GITHUB_SHA': 'a'*40, 'SEED_AUDITS_DATASET_URL': private_url,
        'HC_RETRY_DELAY': '0',
    }
    def run(step, **override):
        return subprocess.run(['bash','-eo','pipefail','-c',step['run']], cwd=ROOT,
            env=env | override, text=True, capture_output=True, timeout=12)

    result = run(plan)
    assert result.returncode == 0, result.stderr
    assert private_url not in output.read_text()
    assert 'health_sources' not in plan_job['outputs']
    assert private_url not in result.stdout + result.stderr
    fields = dict(line.split('=', 1) for line in output.read_text().splitlines())
    output.unlink()
    prepare = next(s for s in health_job['steps'] if s.get('id') == 'inventory')
    assert prepare['env']['SEED_AUDITS_DATASET_URL'] == plan['env']['SEED_AUDITS_DATASET_URL']
    assert prepare['env']['HC_PLAN_SHA'] == '${{ needs.source_plan.outputs.plan_sha256 }}'
    assert prepare['env']['HC_SOURCE_SHA'] == '${{ needs.source_plan.outputs.source_sha }}'

    binding = {'HC_PLAN_SHA': fields['plan_sha256'], 'HC_SOURCE_SHA': fields['source_sha']}
    for mismatch in ({'HC_PLAN_SHA': '0'*64}, {'HC_SOURCE_SHA': '0'*40}):
        refused = run(prepare, **(binding | mismatch))
        assert refused.returncode != 0 and private_url not in refused.stdout + refused.stderr
    malformed = run(prepare, **binding, SEED_KRA_REVENUE_URL='https://host.invalid/fixture-secret-17|bad')
    assert malformed.returncode != 0 and 'fixture-secret-17' not in malformed.stdout + malformed.stderr
    assert not (runner/'seed-health-inventory').exists()
    result = run(prepare, **binding)
    assert result.returncode == 0, result.stderr
    assert private_url not in result.stdout + result.stderr
    assert not output.exists()
    inventory = runner/'seed-health-inventory'
    assert (inventory.stat().st_mode & 0o777) == 0o600
    assert private_url in inventory.read_text()

    curl = tmp_path/'curl'
    curl.write_text('#!/bin/sh\nfor url do :; done\nprintf "%s\\n" "$url" >> "$HEALTH_TEST_CALLS"\n'
                    'case "$url" in *private-source.invalid*) printf 404;; *) printf 200;; esac\n')
    curl.chmod(0o700)
    check = next(s for s in health_job['steps'] if s.get('id') == 'check')
    result = run(check, SEED_AUDITS_DATASET_URL='')
    assert result.returncode == 0, result.stderr
    assert private_url in calls.read_text().splitlines()
    public = result.stdout + result.stderr + output.read_text() + summary.read_text()
    assert 'CRITICAL|audits configured dataset|404' in public
    assert 'private-source.invalid' not in public and 'fixture-secret-17' not in public
    assert not inventory.exists()
