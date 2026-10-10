import hashlib,json,subprocess,time
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT/'baseline-final'
CANDIDATE=Path('/Users/roger/.codex/worktrees/batch10-etl-mappings/audit_app')
base='f6c31e271297eece52f34102dc40a1e2ed7069a8'
targets=['backend/admin_etl_dispatch.py','backend/admin_etl_dispatch_worker.py','backend/admin_etl_dispatch_adapter.py','backend/models.py','backend/seeding/exclusion.py','backend/seeding/cli.py','backend/seeding/registries.py']
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for name in targets:
 if (ROOT/name).read_bytes()!=subprocess.check_output(['git','show',base+':'+name],cwd=CANDIDATE): raise RuntimeError('base source mismatch')
fixtures=['backend/tests/test_batch10_etl_mappings.py',*['backend/tests/batch10_etl_mappings_fixture/'+p.name for p in (ROOT/'backend/tests/batch10_etl_mappings_fixture').glob('*.py')]]
for name in fixtures:
 if (ROOT/name).read_bytes()!=(CANDIDATE/name).read_bytes(): raise RuntimeError('fixture mismatch')
env={'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin','PYTHON_DOTENV_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'backend'),'DATABASE_URL':'postgresql+psycopg2://batch10_mappings:batch10-inert-local@127.0.0.1:55522/batch10_mappings','BATCH10_MAPPINGS_DATABASE_URL':'postgresql+psycopg2://batch10_mappings:batch10-inert-local@127.0.0.1:55522/batch10_mappings'}
cmd=[str(OUT/'venv/bin/python'),'-m','pytest','backend/tests/test_batch10_etl_mappings.py','-k','mapping_runs_real_cli','-q','-p','no:cacheprovider']
start={n:digest(ROOT/n) for n in targets+fixtures}; began=time.time()
with (OUT/'published-fixture-base-red.log').open('xb') as f: code=subprocess.run(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=90).returncode
end={n:digest(ROOT/n) for n in targets+fixtures}
data={'generated_by':'replay_baseline_final.py','generator_sha256':digest(Path(__file__)),'target_commit':base,'target_tree':'69ddfad6deb814dd08fdaee2db2d512d73e14c78','archive_sha256':digest(OUT/'pinned-base.tar'),'command':cmd,'environment':env,'started_at':began,'ended_at':time.time(),'source_before':start,'source_after':end,'source_stable':start==end,'child_exit':code,'log_sha256':digest(OUT/'published-fixture-base-red.log')}
with (OUT/'published-fixture-base-red.json').open('x') as f:json.dump(data,f,indent=2)
if json.loads((OUT/'published-fixture-base-red.json').read_text())!=data:raise RuntimeError('readback')
print(code,(OUT/'published-fixture-base-red.log').read_text()[-2000:])
