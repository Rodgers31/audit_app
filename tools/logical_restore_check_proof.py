"""Opt-in isolated reparse proof for two supported public CHECK predicates.

The verifier binds the source archive, plan and target before calling this module.
No general SQL equivalence is inferred. Witness DDL is rolled back; raw evidence
stays private, including original failures. No provider connection is made.
"""
from pathlib import Path
import copy,hashlib,json,re,time,uuid,importlib.util,datetime,os
from reviewed_pg_acquisition import Refusal
from bounded_pg_backup import inventory_json_lines
GRAMMAR_SHA='f3f76093ee73cb37bff96e6a1d9c20ab162ac8cc3b5862dc1bd744e1ce53a5ea'

SCOPES={('public','etl_dispatch_domains','ck_etl_dispatch_domain'),
        ('public','social_privacy_ownership','ck_social_privacy_subject')}
HOOK_SQL="""SELECT json_build_object('kind','event_hooks','rows',coalesce(json_agg(json_build_array(e.evtname,e.evtevent,e.evtenabled,pg_get_userbyid(e.evtowner),n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),e.evttags,pg_get_functiondef(p.oid)) ORDER BY e.evtname),'[]'::json)) FROM pg_event_trigger e JOIN pg_proc p ON p.oid=e.evtfoid JOIN pg_namespace n ON n.oid=p.pronamespace;"""
CONTEXT_SQL="""SELECT json_build_object('kind','witness_context','executor',current_user,'server_version',current_setting('server_version'),'local_socket',inet_server_addr() IS NULL,'database',current_database(),'search_path',current_setting('search_path'),'schemas',current_schemas(true),'builtin_length',to_regprocedure('length(text)')::oid='pg_catalog.length(text)'::regprocedure::oid,'length_immutable',(SELECT provolatile='i' FROM pg_proc WHERE oid=to_regprocedure('length(text)')));"""
def require(x):
 if x is not True:raise Refusal('CHECK_REPARSE_REFUSED')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text_sha(s):return hashlib.sha256(s.encode('utf8')).hexdigest()
def canonical(v):return json.dumps(v,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def qi(s):return '"'+s.replace('"','""')+'"'
def ql(s):return "'"+s.replace("'","''")+"'"
def one(raw):
 rows=inventory_json_lines(raw)
 require(len(rows)==1 and type(rows[0])is dict)
 return rows[0]
def column_context(inventory,schema,table):
 return [[r[i]for i in (2,4,5,6,7)]for r in inventory[0]['columns'] if r[:2]==[schema,table]]
def load_plan(path,digest,before,after):
 path=Path(path);require(path.is_file() and not path.is_symlink() and path.stat().st_uid==os.geteuid() and path.stat().st_mode&0o077==0)
 require(type(digest)is str and re.fullmatch('[0-9a-f]{64}',digest)is not None and sha(path)==digest)
 plan=json.loads(path.read_text())
 require(type(plan)is dict and set(plan)=={'version','constraints'} and type(plan['version'])is int and plan['version']==1)
 require(type(plan['constraints'])is list and len(plan['constraints'])==2)
 identities=set()
 grammar_path=Path(__file__).with_name('logical_restore_check_grammar.py');require(sha(grammar_path)==GRAMMAR_SHA)
 spec=importlib.util.spec_from_file_location('check_source_grammar',grammar_path);grammar=importlib.util.module_from_spec(spec);spec.loader.exec_module(grammar)
 source={tuple(r[:3]):r for r in before[0]['constraints'] or []}
 target={tuple(r[:3]):r for r in after[0]['constraints'] or []}
 for item in plan['constraints']:
  require(type(item)is dict and set(item)=={'schema','table','name','source_definition_sha256','target_definition_sha256','column_context_sha256'})
  identity=tuple(item[k]for k in ('schema','table','name'))
  require(identity in SCOPES and identity not in identities);identities.add(identity)
  require(identity in source and identity in target and source[identity][3]is True and target[identity][3]is True)
  require(all(type(item[k])is str and re.fullmatch('[0-9a-f]{64}',item[k])is not None for k in ('source_definition_sha256','target_definition_sha256','column_context_sha256')))
  require(source[identity][4]!=target[identity][4] and text_sha(source[identity][4])==item['source_definition_sha256'] and text_sha(target[identity][4])==item['target_definition_sha256'])
  require(source[identity][4].startswith('CHECK (') and not re.search(r'\b(?:NOT VALID|NO INHERIT)\s*$',source[identity][4]) and '\x00'not in source[identity][4])
  try:
   require(grammar.validate(identity,source[identity][4]) is True)
  except (grammar.Refusal,RecursionError,ValueError):
   raise Refusal('UNAPPROVED_CHECK_SOURCE_GRAMMAR') from None
  columns=column_context(before,*identity[:2]);require(bool(columns) and columns==column_context(after,*identity[:2]))
  require(text_sha(canonical(columns))==item['column_context_sha256'])
 require(identities==SCOPES)
 return plan

def sql_tokens(sql):
 """Ignore formatting only; preserve quoted values and every SQL token."""
 tokens=re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|::|[^\s]",sql)
 require(not any(t in ("'",'"',';','$','\\') for t in tokens))
 folding=str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')
 return [t if t.startswith(("'",'"')) else t.translate(folding) for t in tokens]

def table_entries(body):
 """Split pg_dump table entries without splitting quoted or nested commas."""
 entries=[];stack=[];quote=None;start=0;i=0
 while i<len(body):
  c=body[i]
  if quote:
   if c==quote:
    if i+1<len(body) and body[i+1]==quote:i+=2;continue
    quote=None
  elif c in ("'",'"'):quote=c
  elif c in '([':stack.append(c)
  elif c in ')]':require(bool(stack) and stack.pop()=={')':'(',']':'['}[c])
  elif c==',' and not stack:entries.append(body[start:i].strip());start=i+1
  i+=1
 require(quote is None and not stack)
 entries.append(body[start:].strip())
 require(all(entries))
 return entries

def source_archive_column_proof(archive_sql,work,save,before,after,plan):
 """The callback extracts pre-data for exactly the two source archive tables."""
 raw=archive_sql();require(type(raw)is bytes and 0<len(raw)<1024*1024)
 output=Path(work)/'source_check_tables_predata.sql'
 with output.open('xb')as f:f.write(raw)
 output.chmod(0o600)
 sql=raw.decode('utf8')
 # Conservative rejection over the entire selected archive, including any
 # suffix a quoted multiline default might hide from the structural matcher.
 require(re.search(r'\bCOLLATE\b',sql,re.I)is None)
 bindings=[]
 source_constraints={tuple(r[:3]):r for r in before[0]['constraints']or[]}
 target_constraints={tuple(r[:3]):r for r in after[0]['constraints']or[]}
 planned={tuple(p[k]for k in('schema','table','name')):p for p in plan['constraints']}
 require(len(re.findall(r'^CREATE TABLE ',sql,re.M))==2)
 for schema,table,_ in sorted(SCOPES):
  pattern=r'^CREATE TABLE '+re.escape(schema+'.'+table)+r' \(\n(.*?)\n\);$'
  matches=re.findall(pattern,sql,re.M|re.S)
  require(len(matches)==1 and re.search(r'\bCOLLATE\b',matches[0],re.I)is None)
  columns=[r for r in before[0]['columns'] if r[:2]==[schema,table]]
  expected_checks={key:r for key,r in source_constraints.items() if key[:2]==(schema,table) and r[4].startswith('CHECK (')}
  observed_columns=[];observed_checks={}
  for entry in table_entries(matches[0]):
   match=re.fullmatch(r'CONSTRAINT\s+("(?:""|[^"])+"|[a-z_][a-z_0-9]*)\s+(CHECK\s+.*)',entry,re.S)
   if match:
    name=match[1][1:-1].replace('""','"') if match[1].startswith('"') else match[1]
    key=(schema,table,name);require(key in expected_checks and key not in observed_checks)
    definition=match[2];source=expected_checks[key][4]
    path='exact_retained_source'
    if sql_tokens(definition)!=sql_tokens(source):
     require(key in planned and sql_tokens(definition)==sql_tokens(target_constraints[key][4]))
     # This is not a new SQL equivalence: final PASS still requires the
     # fresh source->exact-target witness bound by the already loaded plan.
     path='exact_planned_target_pending_source_reparse'
    observed_checks[key]={'name':name,'binding':path,'archive_definition_sha256':text_sha(definition),
      'source_definition_sha256':text_sha(source),'target_definition_sha256':text_sha(target_constraints[key][4])}
   else:
    tokens=sql_tokens(entry);require(bool(tokens))
    name=tokens[0][1:-1].replace('""','"') if tokens[0].startswith('"') else tokens[0]
    require(len(observed_columns)<len(columns))
    column=columns[len(observed_columns)]
    require(name==column[2] and column[6:8]==['',''])
    expected=column[4]
    if column[8] is not None:expected+=' DEFAULT '+column[8]
    if column[5]:expected+=' NOT NULL'
    require(tokens[1:]==sql_tokens(expected))
    observed_columns.append(name)
  require(observed_columns==[r[2]for r in columns] and set(observed_checks)==set(expected_checks))
  bindings.append({'schema':schema,'table':table,'column_context_sha256':text_sha(canonical(column_context(before,schema,table))),
                   'checks':[observed_checks[k]for k in sorted(observed_checks)]})
 proof={'status':'SOURCE_ARCHIVE_SELECTED_TABLES_BOUND_PENDING_CHECK_WITNESS','sha256':sha(output),'bytes':len(raw),'table_count':2,'bindings':bindings}
 save(Path(work)/'source_archive_column_proof.json',proof)
 return proof

def live_column_sql(schema,table):
 return "SELECT json_build_object('kind','column_context','relkind',c.relkind,'owner',pg_get_userbyid(c.relowner),'is_partition',c.relispartition,'has_children',EXISTS(SELECT 1 FROM pg_inherits i WHERE i.inhparent=c.oid),'columns',(SELECT json_agg(json_build_array(a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,CASE WHEN a.attcollation=0 THEN NULL ELSE json_build_array(cn.nspname,cl.collname)END,tn.nspname) ORDER BY a.attnum) FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid JOIN pg_namespace tn ON tn.oid=t.typnamespace LEFT JOIN pg_collation cl ON cl.oid=a.attcollation LEFT JOIN pg_namespace cn ON cn.oid=cl.collnamespace WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname="+ql(schema)+" AND c.relname="+ql(table)+";"

def dependency_query(oid):
 # PostgreSQL serializes oid directly as a JSON string. Project an explicit
 # integer so the receipt validator can require one exact scalar type.
 return "SELECT coalesce(jsonb_agg(jsonb_build_array(refclassid::regclass::text,refobjid::bigint,refobjsubid,deptype) ORDER BY refclassid::regclass::text,refobjid,refobjsubid,deptype),'[]'::jsonb) FROM pg_depend WHERE classid='pg_constraint'::regclass AND objid="+oid

def witness_block(item,source_definition,target_definition,operation_nonce):
 require(type(operation_nonce)is str and re.fullmatch("[0-9a-f]{32}",operation_nonce)is not None)
 schema,table,name=(item[k]for k in ('schema','table','name'))
 witness='audit_restore_witness_'+uuid.uuid4().hex
 relation=qi(schema)+'.'+qi(table)
 # Dependencies on custom functions/operators/types/collations are deliberately
 # refused, even if a changed predicate might otherwise deparse identically.
 guard="""SELECT 1 FROM pg_depend d
 LEFT JOIN pg_proc p ON d.refclassid='pg_proc'::regclass AND p.oid=d.refobjid
 LEFT JOIN pg_namespace pn ON pn.oid=p.pronamespace
 LEFT JOIN pg_operator o ON d.refclassid='pg_operator'::regclass AND o.oid=d.refobjid
 LEFT JOIN pg_namespace onsp ON onsp.oid=o.oprnamespace
 LEFT JOIN pg_proc op ON op.oid=o.oprcode
 LEFT JOIN pg_type t ON d.refclassid='pg_type'::regclass AND t.oid=d.refobjid
 LEFT JOIN pg_namespace tn ON tn.oid=t.typnamespace
 LEFT JOIN pg_collation cl ON d.refclassid='pg_collation'::regclass AND cl.oid=d.refobjid
 LEFT JOIN pg_namespace cn ON cn.oid=cl.collnamespace
 WHERE d.classid='pg_constraint'::regclass AND d.objid IN(old.oid,fresh.oid)
 AND ((p.oid IS NOT NULL AND (pn.nspname<>'pg_catalog' OR p.provolatile<>'i'))
 OR (o.oid IS NOT NULL AND (onsp.nspname<>'pg_catalog' OR op.provolatile<>'i'))
 OR (t.oid IS NOT NULL AND tn.nspname<>'pg_catalog')
 OR (cl.oid IS NOT NULL AND cn.nspname<>'pg_catalog'))"""
 block="DO $audit_restore_witness$\nDECLARE old pg_constraint%ROWTYPE; fresh pg_constraint%ROWTYPE; olddef text; newdef text;\nBEGIN\n"
 block+=" SELECT * INTO STRICT old FROM pg_constraint WHERE conrelid="+ql(relation)+"::regclass AND conname="+ql(name)+" AND contype='c';\n"
 block+=" olddef:=pg_get_constraintdef(old.oid,false);\n IF olddef<>"+ql(target_definition)+" OR NOT old.convalidated OR old.connoinherit OR NOT old.conislocal OR old.coninhcount<>0 OR old.conparentid<>0 THEN RAISE EXCEPTION 'unexpected original CHECK'; END IF;\n"
 block+=" IF EXISTS(SELECT 1 FROM pg_constraint WHERE conrelid=old.conrelid AND conname="+ql(witness)+") THEN RAISE EXCEPTION 'witness collision'; END IF;\n"
 block+=" fresh:=old; IF EXISTS("+guard+") THEN RAISE EXCEPTION 'unapproved original CHECK dependency'; END IF;\n"
 block+=" EXECUTE "+ql('ALTER TABLE '+relation+' ADD CONSTRAINT '+qi(witness)+' '+source_definition+' NOT VALID')+";\n"
 block+=" SELECT * INTO STRICT fresh FROM pg_constraint WHERE conrelid=old.conrelid AND conname="+ql(witness)+";\n"
 block+=" newdef:=pg_get_constraintdef(fresh.oid,false);\n IF fresh.contype<>'c' OR fresh.convalidated OR fresh.connoinherit<>old.connoinherit OR fresh.conkey IS DISTINCT FROM old.conkey OR fresh.conislocal<>old.conislocal OR fresh.coninhcount<>old.coninhcount OR fresh.conparentid<>old.conparentid OR newdef<>olddef||' NOT VALID' OR pg_get_expr(fresh.conbin,fresh.conrelid,false)<>pg_get_expr(old.conbin,old.conrelid,false) THEN RAISE EXCEPTION 'CHECK canonical parse mismatch'; END IF;\n"
 block+=" IF ("+dependency_query('old.oid')+") IS DISTINCT FROM ("+dependency_query('fresh.oid')+") THEN RAISE EXCEPTION 'CHECK dependency mismatch'; END IF;\n"
 block+=" IF EXISTS("+guard+") THEN RAISE EXCEPTION 'custom or mutable CHECK dependency'; END IF;\nEND\n$audit_restore_witness$;\n"
 block+="SELECT json_build_object('kind','constraint_reparse_witness','operation_nonce',"+ql(operation_nonce)+",'schema',"+ql(schema)+",'table',"+ql(table)+",'name',"+ql(name)+",'source_sha256',"+ql(item['source_definition_sha256'])+",'target_sha256',"+ql(item['target_definition_sha256'])+",'definition',pg_get_constraintdef(oid,false),'expression',pg_get_expr(conbin,conrelid,false),'validated',convalidated,'noinherit',connoinherit,'column_keys',conkey,'dependencies',("+dependency_query('pg_constraint.oid')+")) FROM pg_constraint WHERE conrelid="+ql(relation)+"::regclass AND conname="+ql(witness)+";\n"
 return block

def prove(before,after,props,plan_path,plan_sha,work,query,collect,archive_sql,save,logical,default_readback):
 started=time.monotonic();work=Path(work)
 require(work.is_dir() and not work.is_symlink() and work.stat().st_uid==os.geteuid() and work.stat().st_mode&0o777==0o700)
 plan=load_plan(plan_path,plan_sha,before,after)
 operation_nonce=uuid.uuid4().hex
 derived=copy.deepcopy(before)
 targets={tuple(r[:3]):r for r in after[0]['constraints']or[]}
 for r in derived[0]['constraints']or[]:
  if tuple(r[:3])in SCOPES:r[4]=targets[tuple(r[:3])][4]
 # Establish that the proposed exact two substitutions are the ENTIRE remaining
 # difference before running any DDL. Existing three equivalences remain fixed.
 logical.compare_logical_inventory(derived,after,default_readback)
 archive_proof=source_archive_column_proof(archive_sql,work,save,before,after,plan)
 context=one(query(CONTEXT_SQL,'postgres'))
 require(set(context)=={'kind','executor','server_version','local_socket','database','search_path','schemas','builtin_length','length_immutable'} and context['kind']=='witness_context' and context['executor']=='postgres' and context['server_version']=='17.6' and context['local_socket']is True and context['database']=='postgres' and type(context['search_path'])is str and bool(context['search_path']) and '\x00'not in context['search_path'] and type(context['schemas'])is list and bool(context['schemas']) and context['schemas'][0]=='pg_catalog' and context['builtin_length']is True and context['length_immutable']is True)
 hooks_before=one(query(HOOK_SQL,'postgres'))
 require(set(hooks_before)=={'kind','rows'} and hooks_before['kind']=='event_hooks' and type(hooks_before['rows'])is list)
 require(all(type(r)is list and len(r)==9 and r[2]in('O','D','R','A') and all(type(r[k])is str for k in(0,1,3,4,5,6,8)) for r in hooks_before['rows']))
 contexts=[]
 for schema,table,name in sorted(SCOPES):
  live=one(query(live_column_sql(schema,table),'postgres'))
  require(set(live)=={'kind','relkind','owner','is_partition','has_children','columns'} and live['kind']=='column_context' and live['relkind']=='r' and live['owner']=='postgres' and live['is_partition']is False and live['has_children']is False and type(live['columns'])is list)
  require(all(type(r)is list and len(r)==7 and r[5]in(None,['pg_catalog','default']) and r[6]=='pg_catalog' for r in live['columns']))
  require([r[:5]for r in live['columns']]==column_context(before,schema,table))
  contexts.append({'schema':schema,'table':table,'context':live})
 save(work/'check_reparse_contexts.json',{'executor':context,'hooks':hooks_before,'columns':contexts})
 script="BEGIN; SET LOCAL standard_conforming_strings=on; SET LOCAL lock_timeout='1s'; SET LOCAL statement_timeout='10s';\n"
 for hook in hooks_before['rows']:
  if hook[2]!='D':script+='ALTER EVENT TRIGGER '+qi(hook[0])+' DISABLE;\n'
 script+='SET LOCAL ROLE postgres;\nDO $audit_restore_context$ BEGIN PERFORM pg_catalog.set_config(\'search_path\','+ql(context['search_path'])+',true); END $audit_restore_context$;\n'
 sources={tuple(r[:3]):r for r in before[0]['constraints']or[]}
 for item in plan['constraints']:
  key=tuple(item[k]for k in('schema','table','name'))
  script+=witness_block(item,sources[key][4],targets[key][4],operation_nonce)
 script+='RESET ROLE;\nROLLBACK;\n'
 sql_path=work/'check_reparse_witness.sql'
 with sql_path.open('x')as f:f.write(script)
 sql_path.chmod(0o600)
 verdict={'status':'REFUSED_EXACT_CHECK_REPARSE','generated_by':str(Path(__file__).resolve()),'generator_sha256':sha(__file__),'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'plan_sha256':plan_sha,'operation_nonce':operation_nonce,'witness_sql_sha256':sha(sql_path),'source_archive_column_proof':archive_proof,'scope_count':2,'production_connections':0,'original_constraints_changed':False,'witnesses_validated':False}
 failure=None
 try:
  raw=query(script,'supabase_admin')
  witnesses=inventory_json_lines(raw)
  require(len(witnesses)==2 and {tuple(r[k]for k in('schema','table','name'))for r in witnesses}==SCOPES)
  for witness in witnesses:
   require(type(witness)is dict and set(witness)=={'kind','operation_nonce','schema','table','name','source_sha256','target_sha256','definition','expression','validated','noinherit','column_keys','dependencies'})
   key=tuple(witness[k]for k in('schema','table','name'))
   item=next(p for p in plan['constraints'] if tuple(p[k]for k in('schema','table','name'))==key)
   require(witness['kind']=='constraint_reparse_witness' and witness['operation_nonce']==operation_nonce and witness['definition']==targets[key][4]+' NOT VALID' and witness['validated']is False and witness['noinherit']is False)
   require(witness['source_sha256']==item['source_definition_sha256'] and witness['target_sha256']==item['target_definition_sha256'] and type(witness['expression'])is str and bool(witness['expression']))
   require(type(witness['column_keys'])is list and bool(witness['column_keys']) and all(type(n)is int and 1<=n<=32767 for n in witness['column_keys']) and len(witness['column_keys'])==len(set(witness['column_keys'])))
   require(type(witness['dependencies'])is list and bool(witness['dependencies']) and all(type(d)is list and len(d)==4 and type(d[0])is str and bool(d[0]) and type(d[1])is int and 0<d[1]<2**32 and type(d[2])is int and d[2]>=0 and type(d[3])is str and len(d[3])==1 for d in witness['dependencies']))
  verdict['witnesses_compared']=True
  save(work/'check_reparse_witnesses.json',witnesses)
  require(time.monotonic()-started<60)
  verdict['status']='PASS_EXACT_TWO_CHECK_CANONICAL_REPARSE'
 except BaseException as error:failure=error
 finally:
  # The psql callback's ON_ERROR_STOP connection close rolls back a failed script.
  # Recollect even on failure: a successful receipt requires positive rollback.
  try:
   final_records,final_props=collect()
   hooks_after=one(query(HOOK_SQL,'postgres'))
   save(work/'check_reparse_after_rollback.json',{'inventory':final_records,'prerequisites':final_props,'event_hooks':hooks_after})
   logical.acquisition.compare_recovery_prerequisites(props,final_props)
   unchanged=(canonical(final_records)==canonical(after) and canonical(hooks_after)==canonical(hooks_before))
   verdict['durable_prerequisites_unchanged']=True
   verdict['transient_activity_counts_equal']=canonical(props.get('activity_counts'))==canonical(final_props.get('activity_counts'))
   verdict['full_post_rollback_state_unchanged']=unchanged
   require(unchanged)
   require(sha(plan_path)==plan_sha)
  except BaseException as error:failure=error;verdict['status']='REFUSED_CHECK_REPARSE_ROLLBACK'
  if failure is not None:verdict['status']='REFUSED_EXACT_CHECK_REPARSE';verdict['error_class']=type(failure).__name__
  verdict['elapsed_seconds']=round(time.monotonic()-started,6)
  save(work/'check_reparse_receipt.json',verdict)
 if failure is not None:raise Refusal('EXACT_CHECK_REPARSE_OR_ROLLBACK_REFUSED') from None
 require(verdict['status']=='PASS_EXACT_TWO_CHECK_CANONICAL_REPARSE')
 return derived,verdict
