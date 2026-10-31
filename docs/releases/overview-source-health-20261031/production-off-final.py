import io,contextlib,json
out=io.StringIO()
with contextlib.redirect_stdout(out):
 import os,json,datetime,pathlib
 import psycopg2
 conn=None
 try:
  dsn=os.getenv('DATABASE_URL')
  if dsn:
   conn=psycopg2.connect(dsn.replace('postgresql+psycopg2://','postgresql://',1),connect_timeout=5,sslmode='verify-full',sslrootcert='/etc/secrets/supabase-root-ca.crt',application_name='auditgava-release-readonly')
  else:
   conn=psycopg2.connect(host=os.environ['DB_HOST'],port=int(os.getenv('DB_PORT','5432')),dbname=os.getenv('DB_NAME','postgres'),user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],sslmode='verify-full',sslrootcert='/etc/secrets/supabase-root-ca.crt',connect_timeout=5,application_name='auditgava-release-readonly')
  conn.set_session(readonly=True,autocommit=False)
  with conn.cursor() as cur:
   cur.execute("SET LOCAL statement_timeout='5s'");cur.execute("SET LOCAL lock_timeout='1s'")
   cur.execute('SHOW transaction_read_only');readonly=cur.fetchone()[0]
   if readonly!='on':raise RuntimeError('Readonly transaction required')
   cur.execute('SELECT version_num FROM alembic_version');migration=cur.fetchall()
   cur.execute('SELECT publishing_enabled,auto_approve_enabled,auto_schedule_enabled,auto_publish_enabled,version FROM social_controls WHERE id=1');controls=cur.fetchall()
   cur.execute('SELECT platform,publishing_enabled,count(*) FROM social_accounts GROUP BY 1,2 ORDER BY 1,2');accounts=cur.fetchall()
   cur.execute('SELECT state,count(*) FROM social_post_targets GROUP BY state ORDER BY state');targets=cur.fetchall()
   cur.execute('SELECT state,heartbeat_at,last_scan_at FROM social_worker_heartbeats ORDER BY heartbeat_at DESC LIMIT 1');heartbeat=cur.fetchall()
   totals={}
   for table in ('social_posts','social_publications','social_post_targets','social_media_assets','social_media_uploads','social_publish_attempts'):
    cur.execute('SELECT count(*) FROM '+table);totals[table]=cur.fetchone()[0]
   print('READ_ONLY_SOCIAL_COUNTS '+json.dumps(totals))
   print('READ_ONLY_SOCIAL_DATABASE '+json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'transaction_read_only':readonly,'migration':migration,'controls_columns':['publishing','auto_approve','auto_schedule','auto_publish','version'],'controls':controls,'accounts_platform_publishing_counts':accounts,'target_state_counts':targets,'last_heartbeat':heartbeat},default=str))
 except Exception as exc:print('READ_ONLY_SOCIAL_DATABASE_ERROR '+json.dumps({'type':type(exc).__name__,'sqlstate':getattr(exc,'pgcode',None)}))
 finally:
  if conn is not None:conn.rollback();conn.close()
 processes=[]
 for directory in pathlib.Path('/proc').iterdir():
  if not directory.name.isdigit():continue
  try:
   args=(directory/'cmdline').read_bytes().decode(errors='replace').split('\0');comm=(directory/'comm').read_text().strip()
  except OSError:continue
  web=any(pathlib.Path(a).name in ('gunicorn','uvicorn') or a.startswith(('gunicorn:','uvicorn:')) for a in args)
  social=any(a.startswith('social.') and ('worker' in a or 'retirement' in a) or a=='social_worker_supervisor' for a in args)
  background=any(('worker' in a or 'consumer' in a or 'supervisor' in a) and (a.startswith(('social.','seeding.','etl.')) or pathlib.Path(a).name.startswith(('etl_dispatch_','social_worker_'))) for a in args)
  processes.append({'background_worker_or_consumer':background,'pid':int(directory.name),'comm':comm,'web':web,'social_worker_or_supervisor':social})
 print('READ_ONLY_PROCESS_INVENTORY '+json.dumps(processes))
 
 keys=('SOCIAL_WORKER_SUPERVISOR_ENABLED','SOCIAL_NATIVE_ENABLED','SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED','SOCIAL_POLICY_AUTOMATION_ENABLED','SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED','SOCIAL_MEDIA_ENABLED','SOCIAL_STUDIO_ENABLED','SOCIAL_GENERATION_HOOK_ENABLED','SOCIAL_REPORT_GENERATION_ENABLED','AUTO_SEEDER_ENABLED','ADMIN_ETL_DISPATCH_ENABLED')
 print('READ_ONLY_FLAGS '+json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha':os.getenv('RENDER_GIT_COMMIT'),'flags':{k:os.getenv(k,'<unset>') for k in keys}}))

print("OFF_RELEASE "+json.dumps(out.getvalue().splitlines()))
