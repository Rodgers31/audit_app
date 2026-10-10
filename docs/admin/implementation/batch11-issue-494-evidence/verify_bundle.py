"""Validate retained bytes and command receipts; never grants current acceptance."""
import hashlib,json,math,re,stat,sys,zipfile
from pathlib import Path,PurePosixPath

def need(ok,message):
 if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def digest(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None
def relative_name(value):
 return type(value) is str and bool(value) and '\\' not in value and not value.startswith('/') and value==str(PurePosixPath(value)) and all(part not in ('','..','.') for part in PurePosixPath(value).parts)
def object_json(data):
 def pairs(items):
  result={}
  for key,value in items:
   need(key not in result,'duplicate JSON key');result[key]=value
  return result
 return json.loads(data,object_pairs_hook=pairs,parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite JSON number')))
def source(value):
 need(type(value) is dict and set(value)=={'head','tree','status','files'},'invalid source identity')
 for key in ('head','tree'):need(type(value[key]) is str and re.fullmatch('[0-9a-f]{40}',value[key]),'invalid git identity')
 need(type(value['status']) is str and type(value['files']) is dict and value['files'],'missing source inventory')
 for name,d in value['files'].items():need(relative_name(name) and digest(d),'invalid source file digest')
def environment(value,mode,executable,name,runtime):
 fixed={'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','PYTHON_DOTENV_DISABLED':'1','NEXT_TELEMETRY_DISABLED':'1','ONNXRUNTIME_NODE_INSTALL':'skip','npm_config_engine_strict':'true'}
 paths=('HOME','TMPDIR','npm_config_cache','npm_config_userconfig','npm_config_globalconfig','PLAYWRIGHT_BROWSERS_PATH','NATIVE_VERIFY_CACHE_DIR')
 if mode=='build':fixed.update({'NEXT_PUBLIC_API_URL':'http://127.0.0.1:18033','INTERNAL_API_URL':'http://127.0.0.1:18033','NEXT_PUBLIC_SUPABASE_URL':'http://127.0.0.1:18033','NEXT_PUBLIC_SUPABASE_ANON_KEY':'batch11-inert-anon-key'})
 need(type(value) is dict and set(value)==set(fixed)|set(paths)|{'PATH'},'incomplete resolved environment')
 need(all(type(v) is str and v for v in value.values()),'invalid environment value')
 need(all(value[k]==v for k,v in fixed.items()),'wrong captured environment policy')
 need(all(Path(value[k]).is_absolute() for k in paths),'relative environment path')
 work=Path(value['HOME']).parent;base=work.parent
 need(work.name==Path(name).stem+'-runtime' and Path(value['HOME']).name=='home','wrong owned command home')
 expected={'HOME':work/'home','TMPDIR':work/'tmp','npm_config_userconfig':work/'npm-user','npm_config_globalconfig':work/'npm-global','npm_config_cache':base/'npm-cache','PLAYWRIGHT_BROWSERS_PATH':base/'browsers','NATIVE_VERIFY_CACHE_DIR':base/'model-cache'}
 need(all(value[k]==str(p) for k,p in expected.items()),'wrong owned environment paths')
 need(runtime.get('platform')=='darwin','unsupported historical recorder platform')
 need(value['PATH']==str(Path(executable).parent)+':/bin:/usr/bin','wrong captured executable PATH')
def receipt(value,members,name,expectation):
 need(type(expectation) is dict and set(expectation)=={'exit','source_stable','error'},'incomplete receipt expectation')
 need(type(value) is dict and 'error' in value,'missing execution error')
 need(type(value) is dict and type(value.get('schema')) is int and value['schema']==1,'invalid receipt schema')
 need(value.get('generated_by')=='run.py' and digest(value.get('generator_sha256')),'invalid recorder identity')
 need(value['generator_sha256']==sha(members['producers/run.py']),'unbound historical producer')
 source(value.get('source_before'));source(value.get('source_after'))
 need(type(value.get('source_stable')) is bool,'invalid stability type')
 need(value['source_stable']==(value['source_before']==value['source_after']),'contradictory stability')
 need(type(value.get('exit')) is int and type(expectation.get('exit')) is int and value['exit']==expectation['exit'],'wrong historical exit')
 need(type(expectation.get('source_stable')) is bool and value['source_stable']==expectation['source_stable'],'wrong historical stability')
 need(value['error']==expectation['error'],'wrong execution error')
 need(value['error'] is None or type(value['error']) is str,'malformed execution error')
 for key in ('started_at','ended_at'):need(type(value.get(key)) in (int,float) and math.isfinite(value[key]) and value[key]>0,'invalid execution time')
 need(value['ended_at']>=value['started_at'],'reversed execution time')
 need(type(value.get('command')) is list and value['command'] and all(type(x) is str for x in value['command']) and Path(value['command'][0]).is_absolute(),'missing actual command')
 need(type(value.get('cwd')) is str and Path(value['cwd']).is_absolute(),'missing actual cwd')
 need(value.get('mode') in ('unit','build','native','plain'),'invalid environment mode')
 need(type(value.get('runtime')) is dict and all(type(value['runtime'].get(k)) is str and value['runtime'][k] for k in ('python','platform','machine')),'missing observed runtime')
 environment(value.get('resolved_environment'),value['mode'],value['command'][0],name,value['runtime'])
 need(value.get('classification')=='CURRENT_COMMAND_CAPTURE' and value.get('current_checkout_acceptance') is False,'invalid scope classification')
 for extension in ('stdout','stderr'):
  stream=name[:-5]+'.'+extension
  need(stream in members and value.get(extension+'_sha256')==sha(members[stream]),'unbound actual stream')
def verify(archive,manifest_path):
 for p in (archive,manifest_path):need(Path(p).is_file() and not Path(p).is_symlink(),'regular packet input required')
 manifest=object_json(Path(manifest_path).read_bytes())
 need(type(manifest) is dict and type(manifest.get('schema')) is int and manifest['schema'] in (1,2),'invalid manifest schema')
 need(manifest.get('classification')=='HISTORICAL_PACKET_INTEGRITY' and manifest.get('current_checkout_acceptance') is False,'invalid packet classification')
 need(digest(manifest.get('archive_sha256')) and sha(Path(archive).read_bytes())==manifest['archive_sha256'],'archive hash mismatch')
 need(type(manifest.get('members')) is dict and manifest['members'],'missing member inventory')
 members={}
 with zipfile.ZipFile(archive) as z:
  need(sum(info.file_size for info in z.infolist())<=256*1024*1024,'oversized archive')
  for info in z.infolist():
   name=info.filename;parts=PurePosixPath(name).parts
   need(name and '\\' not in name and not name.startswith('/') and all(part not in ('','..','.') for part in parts) and name==str(PurePosixPath(name)),'unsafe archive member')
   need(name not in members and not info.is_dir() and stat.S_IFMT(info.external_attr>>16)!=stat.S_IFLNK,'duplicate/link/directory member')
   members[name]=z.read(info)
 need(set(members)==set(manifest['members']),'member inventory mismatch')
 for name,data in members.items():need(digest(manifest['members'][name]) and sha(data)==manifest['members'][name],'member hash mismatch')
 need(digest(manifest.get('producer_sha256')),'missing packet producer identity')
 if manifest['schema']==2:need('producers/pack.py' in members and manifest['producer_sha256']==sha(members['producers/pack.py']),'unbound packet producer')
 need(type(manifest.get('receipts')) is dict and manifest['receipts'],'missing receipt inventory')
 need(set(manifest['receipts'])=={name for name in members if name.startswith('commands/') and name.endswith('.json')},'incomplete receipt inventory')
 for name,expectation in manifest['receipts'].items():
  need(name in members and type(expectation) is dict,'invalid receipt entry');receipt(object_json(members[name]),members,name,expectation)
 return {'classification':'HISTORICAL_PACKET_INTEGRITY','current_checkout_acceptance':False,'issue_494':'OPEN_UNRESOLVED','manifest_schema':manifest['schema'],'members':len(members),'command_receipts':len(manifest['receipts']),'archive_sha256':manifest['archive_sha256'],'verifier_sha256':sha(Path(__file__).read_bytes())}
def external_output(output,checkout):
 output=Path(output).absolute();checkout=Path(checkout).resolve()
 for p in [output,*output.parents]:need(not p.is_symlink(),'output symlink refused')
 need(output.is_dir() and not any(output.iterdir()),'empty external output required')
 resolved=output.resolve();need(not resolved.is_relative_to(checkout) and not checkout.is_relative_to(resolved),'external output required')
 return resolved
if __name__=='__main__':
 try:
  need(len(sys.argv) in (3,4),'ARCHIVE MANIFEST [EMPTY_EXTERNAL_OUTPUT] required')
  destination=external_output(sys.argv[3],Path(__file__).resolve().parents[4]) if len(sys.argv)==4 else None
  result=verify(sys.argv[1],sys.argv[2]);data=json.dumps(result,indent=2)+'\n'
  if destination:
   with (destination/'verification.json').open('x') as f:f.write(data)
   need(object_json((destination/'verification.json').read_bytes())==result,'result readback failure')
  print(data,end='')
 except Exception as error:print(str(error),file=sys.stderr);sys.exit(1)
