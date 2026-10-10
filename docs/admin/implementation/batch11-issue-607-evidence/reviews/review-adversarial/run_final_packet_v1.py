"""Independent real-corpus verification. Execute only after the author freezes the packet."""
import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inventory(folder):
    return {p.relative_to(folder).as_posix():('SYMLINK:'+os.readlink(p) if p.is_symlink() else sha(p)) for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
def source_inventory(folder):
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=folder).decode().split('\0')
    return {p:sha(folder/p) for p in paths if p and (folder/p).is_file()}
def read(p):
    raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def write(p,data):
    raw=(json.dumps(data,indent=2)+'\n').encode()
    if p.suffix=='.gz':raw=gzip.compress(raw,mtime=0)
    if p.exists() or p.is_symlink():p.unlink()
    p.write_bytes(raw)
def raw(p,data):
    if p.exists() or p.is_symlink():p.unlink()
    p.write_bytes(data)
def mutate_json(p,fn):
    data=read(p);fn(data);write(p,data)
def first_spec(report):
    def visit(suite):
        if suite.get('specs'):return suite['specs'][0]
        for child in suite.get('suites',[]):
            found=visit(child)
            if found:return found
    for suite in report['suites']:
        found=visit(suite)
        if found:return found
    raise AssertionError('No test case in controlled report')
def first_result(report):return first_spec(report)['tests'][0]['results'][0]
def named(data,name):return next(r for r in data['runs'] if r['name']==name)

p=argparse.ArgumentParser()
p.add_argument('--checkout',type=Path,required=True)
p.add_argument('--packet',type=Path,required=True)
p.add_argument('--manifest',default='packet-v1.json')
a=p.parse_args()
checkout=a.checkout.resolve();packet=a.packet.resolve()
run=ROOT/('final-v1-'+time.strftime('%Y%m%dT%H%M%S'));run.mkdir()
verifier=packet/'tools/verify_packet.py'
verifier_hash=sha(verifier)
snapshot=ROOT/('verify_packet-'+verifier_hash+'.py')
if not snapshot.exists():snapshot.write_bytes(verifier.read_bytes())
assert sha(snapshot)==verifier_hash
spec=importlib.util.spec_from_file_location('final_packet_verifier',snapshot)
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
packet_before=inventory(packet);source_before=source_inventory(checkout)
canonical=run/'canonical-packet';shutil.copytree(packet,canonical)
assert inventory(canonical)==packet_before
results=[]
def record(name,expect_reject,callback):
    try:
        value=callback()
        entry={'name':name,'expected_rejection':expect_reject,'rejected':False,'return':value}
    except Exception as e:
        entry={'name':name,'expected_rejection':expect_reject,'rejected':True,'exception_type':type(e).__name__,'exception':str(e)}
    entry['matches_expectation']=entry['rejected']==expect_reject
    results.append(entry);print(json.dumps(entry))
record('real-packet/direct-verify',False,lambda:V.verify(packet,checkout,a.manifest))
environment={'PATH':os.defpath,'HOME':str(run),'LANG':'C.UTF-8'}
command=[sys.executable,'-B',str(verifier),'--packet',str(packet),'--checkout',str(checkout),'--manifest',a.manifest,'--output',str(run/'cli-result.json')]
child=subprocess.run(command,env=environment,capture_output=True,text=True)
(run/'cli.stdout.log').write_text(child.stdout);(run/'cli.stderr.log').write_text(child.stderr)
results.append({'name':'real-packet/cli-verify','expected_exit':0,'actual_exit':child.returncode,'matches_expectation':child.returncode==0,'command':command,
                'stdout_sha256':sha(run/'cli.stdout.log'),'stderr_sha256':sha(run/'cli.stderr.log')})
index=0
def attack(name,mutation,recatalog=True):
    global index
    index+=1
    fixture=run/('case-%02d-%s'%(index,name))
    # Hard links refer only to the reviewer-owned immutable canonical copy.
    # Every changed file is unlinked by write()/raw() before replacing bytes.
    shutil.copytree(canonical,fixture,copy_function=os.link)
    data=read(fixture/a.manifest)
    mutation(fixture,data)
    if recatalog:
        data['files']={n:h for n,h in inventory(fixture).items() if n!=a.manifest}
        write(fixture/a.manifest,data)
    record('mutated-real-packet/'+name,True,lambda:V.verify(fixture,checkout,a.manifest))
    assert inventory(canonical)==packet_before,'Controlled fixture changed canonical bytes'
def current_receipt(f,d):return f/named(d,'focused-green')['receipt']
def focus_report(f,d):return f/named(d,'focused-green')['report']
red_name=next(r['name'] for r in read(canonical/a.manifest)['runs'] if r['category']=='historical-red')
attacks=[
 ('bool-schema',lambda f,d:d.update(schema=True)),
 ('negative-schema',lambda f,d:d.update(schema=-1)),
 ('missing-full-public',lambda f,d:d.update(runs=[r for r in d['runs'] if r['name']!='full-public'])),
 ('duplicate-run-name',lambda f,d:d['runs'].append(copy.deepcopy(d['runs'][0]))),
 ('bool-declared-count',lambda f,d:named(d,'focused-green')['counts'].update(expected=True)),
 ('empty-case-ids',lambda f,d:named(d,'focused-green').update(case_ids=[])),
 ('duplicate-case-ids',lambda f,d:named(d,'focused-green')['case_ids'].append(named(d,'focused-green')['case_ids'][0])),
 ('same-count-report-substitution',lambda f,d:named(d,'focused-green').update(report=named(d,'full-operations')['report'],case_ids=named(d,'full-operations')['case_ids'])),
 ('null-report-path',lambda f,d:named(d,'focused-green').update(report=None)),
 ('outside-report-path',lambda f,d:named(d,'focused-green').update(report='../outside-report.json')),
 ('absent-report',lambda f,d:focus_report(f,d).unlink()),
 ('empty-report',lambda f,d:raw(focus_report(f,d),b'')),
 ('malformed-report',lambda f,d:raw(focus_report(f,d),b'{malformed')),
 ('hidden-top-errors',lambda f,d:mutate_json(focus_report(f,d),lambda r:r.update(errors=[{'message':'reviewer controlled hidden error'}]))),
 ('hidden-result-error',lambda f,d:mutate_json(focus_report(f,d),lambda r:first_result(r).update(error={'message':'reviewer controlled hidden error'}))),
 ('retry-bool',lambda f,d:mutate_json(focus_report(f,d),lambda r:first_result(r).update(retry=False))),
 ('retry-one',lambda f,d:mutate_json(focus_report(f,d),lambda r:first_result(r).update(retry=1))),
 ('result-duration-bool',lambda f,d:mutate_json(focus_report(f,d),lambda r:first_result(r).update(duration=True))),
 ('result-duration-negative',lambda f,d:mutate_json(focus_report(f,d),lambda r:first_result(r).update(duration=-1))),
 ('report-duration-negative',lambda f,d:mutate_json(focus_report(f,d),lambda r:r['stats'].update(duration=-1))),
 ('receipt-child-bool',lambda f,d:mutate_json(current_receipt(f,d),lambda r:r.update(child_exit=False))),
 ('receipt-child-nonzero',lambda f,d:mutate_json(current_receipt(f,d),lambda r:r.update(child_exit=1))),
 ('receipt-timed-out',lambda f,d:mutate_json(current_receipt(f,d),lambda r:r.update(timed_out=True))),
 ('receipt-source-drift',lambda f,d:mutate_json(current_receipt(f,d),lambda r:r.update(source_changed=['frontend/app/counties/CountiesPageClient.tsx']))),
 ('receipt-helper-drift',lambda f,d:mutate_json(current_receipt(f,d),lambda r:r.update(helpers_changed=['producer.py']))),
 ('receipt-generator-drift',lambda f,d:mutate_json(current_receipt(f,d),lambda r:r.update(generator_unchanged=False))),
 ('red-helper-drift',lambda f,d:mutate_json(f/named(d,red_name)['receipt'],lambda r:r.update(helpers_changed=['producer.py']))),
 ('source-inventory-empty',lambda f,d:mutate_json(f/d['current_source_receipt'],lambda r:r.update(source_hashes={}))),
]
for name,mutation in attacks:attack(name,mutation)
def duplicate_json(f,d):
    target=current_receipt(f,d)
    raw(target,gzip.compress(b'{"child_exit":1,"child_exit":0}',mtime=0) if target.suffix=='.gz' else b'{"child_exit":1,"child_exit":0}')
attack('duplicate-json-key',duplicate_json)
def symlink_report(f,d):
    target=focus_report(f,d);target.unlink();target.symlink_to(canonical/named(d,'focused-green')['report'])
attack('symlink-report',symlink_report)
packet_after=inventory(packet);source_after=source_inventory(checkout)
packet_changed=sorted(k for k in set(packet_before)|set(packet_after) if packet_before.get(k)!=packet_after.get(k))
source_changed=sorted(k for k in set(source_before)|set(source_after) if source_before.get(k)!=source_after.get(k))
for name,data in [('packet-before',packet_before),('packet-after',packet_after),('source-before',source_before),('source-after',source_after)]:
    (run/(name+'.json.gz')).write_bytes(gzip.compress(json.dumps(data,sort_keys=True).encode(),mtime=0))
receipt={'schema':1,'python_version':sys.version,'verifier_sha256':verifier_hash,'verifier_after':sha(verifier),'script_sha256':sha(Path(__file__)),
         'packet':str(packet),'checkout':str(checkout),'manifest':a.manifest,'manifest_sha256':sha(packet/a.manifest),'git_identity':subprocess.check_output(['git','rev-parse','HEAD','HEAD^{tree}'],cwd=checkout,text=True).splitlines(),
         'packet_changed':packet_changed,'source_changed':source_changed,'actual_git_dependencies':True,'no_browser_docker_database_calls':True,
         'measured_cases':len(results),'unexpected_results':sum(not r['matches_expectation'] for r in results),'results':results,
         'inventory_sha256':{p.name:sha(p) for p in run.glob('*-before.json.gz')}|{p.name:sha(p) for p in run.glob('*-after.json.gz')}}
write(run/'results.json',receipt)
print(json.dumps({'results':str(run/'results.json'),'unexpected_results':receipt['unexpected_results'],'packet_changed':packet_changed,'source_changed':source_changed,'verifier_sha256':verifier_hash}))
sys.exit(0 if not receipt['unexpected_results'] and not packet_changed and not source_changed else 1)
