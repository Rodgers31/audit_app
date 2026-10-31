"""Host orchestration only. Application tests run in capped offline Linux Docker."""
import argparse,json,pathlib,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--optimized',action='store_true');a=p.parse_args();e=pathlib.Path(__file__).resolve().parent;label='canonical-affected-'+('optimized' if a.optimized else 'normal');cmd=['docker','run','--pull','never','--rm','--name','overview-standards-'+label,'--network','none','--cpus','1','--memory','1g','--pids-limit','256']
values={'DATABASE_URL':'sqlite:////tmp/overview-standards.sqlite','ENVIRONMENT':'test','SUPABASE_URL':'https://identity.invalid','CORS_ORIGINS':'https://allowed.owned','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':'/case','AUTO_SEEDER_ENABLED':'false','SOCIAL_GENERATION_HOOK_ENABLED':'false','SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED':'false','SOCIAL_PUBLISHING_ENABLED':'false','SOCIAL_NATIVE_ENABLED':'false','SOCIAL_WORKER_ENABLED':'false','SOCIAL_WORKER_SUPERVISOR_ENABLED':'false','SOCIAL_MEDIA_ENABLED':'false','SOCIAL_UPLOADS_ENABLED':'false'}
for k,v in values.items():cmd+=['-e',k+'='+v]
cmd+=['-v',str(e/'candidate-2/backend')+':/case:ro','-v',str(e)+':/evidence','-w','/case','admin-redesign-python-runtime:local','python']
if a.optimized:cmd+=['-O']
cmd+=['-m','pytest','-q','-p','no:cacheprovider','tests/test_auth_retry_after.py','tests/test_jwks_request_budget.py','tests/test_jwks_transport_bounds.py','tests/test_jwks_cache_recovery.py','tests/test_source_failure_diagnostics.py','tests/test_status_v2.py','tests/test_pipeline_health_worker.py','tests/test_request_resource_bounds.py','--junitxml=/evidence/'+label+'.xml'];(e/(label+'-command.json')).write_text(json.dumps(cmd,indent=2)+'\n');start=time.monotonic()
with (e/(label+'.txt')).open('wb') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
(e/(label+'-execution.json')).write_text(json.dumps({'exit':r.returncode,'seconds':time.monotonic()-start},indent=2)+'\n');print(label,r.returncode);raise SystemExit(r.returncode)
