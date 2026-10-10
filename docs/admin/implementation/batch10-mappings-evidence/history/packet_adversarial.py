"""Independent execution of the actual published verifier over hostile copied packages."""
from datetime import datetime,timezone
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from uuid import uuid4
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
SOURCE=Path('/Users/roger/.codex/worktrees/batch10-etl-mappings/audit_app')
PACKET=Path('docs/admin/implementation/batch10-mappings-evidence')
OUT=ROOT/('packet-review-'+uuid4().hex);OUT.mkdir()
ENV={'PATH':'/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin','PYTHON_DOTENV_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1','DATABASE_URL':'sqlite:///'+str(OUT/'inert.sqlite')}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def inventory(root):return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def git(*a):return subprocess.check_output(['git',*a],cwd=SOURCE,text=True).strip()
manifest=json.loads((SOURCE/PACKET/'manifest.json').read_text())
paths={SOURCE/name for name in manifest['source_sha256']}
paths|={p for p in (SOURCE/PACKET).rglob('*') if p.is_file()}
before={str(p.relative_to(SOURCE)):sha(p) for p in sorted(paths)}
(OUT/'source-before.json').write_text(json.dumps(before,indent=2))
records=[]
cases=['none','schema_bool','duplicate_check','pruned_cohort','failed_testcase_with_zero_summary','bool_child_exit','empty_checks','source','log','generator','zero_tests']
for optimized in [False,True]:
    for attack in cases:
        copy=OUT/(attack+('-optimized' if optimized else '-normal'))
        shutil.copytree(SOURCE/PACKET,copy/PACKET)
        for name in manifest['source_sha256']:
            target=copy/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/name,target)
        packet=copy/PACKET
        m=json.loads((packet/'manifest.json').read_text())
        check=m['checks'][0]
        receipt_path=packet/check['receipt'];receipt=json.loads(receipt_path.read_text())
        if attack=='schema_bool':m['schema']=True
        elif attack=='duplicate_check':m['checks'].append(dict(m['checks'][0]))
        elif attack=='pruned_cohort':
            m['checks']=m['checks'][-1:]
            retained={c['receipt'] for c in m['checks']}
            for p in (packet/'receipts').glob('*.json'):
                name=str(p.relative_to(packet))
                if name not in retained:p.unlink();m['assets_sha256'].pop(name,None)
        elif attack in ('failed_testcase_with_zero_summary','zero_tests'):
            junit=packet/receipt['junit'];tree=ET.parse(junit)
            if attack=='failed_testcase_with_zero_summary':
                testcase=next(tree.getroot().iter('testcase'))
                ET.SubElement(testcase,'failure',{'message':'Inert hostile failing result'}).text='Actual JUnit failure while summary attributes remain zero'
            else:
                suite=next(tree.getroot().iter('testsuite'));suite.set('tests','0');receipt['counts']['tests']=0
            tree.write(junit,encoding='utf-8',xml_declaration=True)
            receipt['junit_sha256']=sha(junit)
            m['assets_sha256'][receipt['junit']]=sha(junit)
            receipt_path.write_text(json.dumps(receipt));m['assets_sha256'][check['receipt']]=sha(receipt_path)
        elif attack=='bool_child_exit':
            receipt['child_exit']=False;check['expected_exit']=False
            receipt_path.write_text(json.dumps(receipt));m['assets_sha256'][check['receipt']]=sha(receipt_path)
        elif attack=='empty_checks':m['checks']=[]
        elif attack=='source':(copy/next(iter(m['source_sha256']))).write_text('Tampered source')
        elif attack in ('log','generator'):(packet/receipt[attack]).write_text('Tampered '+attack)
        (packet/'manifest.json').write_text(json.dumps(m,indent=2))
        inherited=packet/'inherited-verdict.json';inherited.write_bytes(b'{"historical":true}')
        input_before=inventory(copy)
        command=[sys.executable,*(['-O'] if optimized else []),str(packet/'verify_package.py'),str(copy)]
        start=datetime.now(timezone.utc).isoformat()
        child=subprocess.run(command,cwd=ROOT,env=ENV,capture_output=True,text=True,timeout=20)
        log=OUT/(attack+('-optimized' if optimized else '-normal')+'.txt')
        with log.open('x') as f:f.write(child.stdout+'\nSTDERR:\n'+child.stderr)
        stable=input_before==inventory(copy)
        passed=child.returncode==0 and 'PASSED' in child.stdout
        record={'case':attack,'optimized':optimized,'command':command,'start':start,'end':datetime.now(timezone.utc).isoformat(),'child_exit':child.returncode,'stdout':child.stdout.strip(),'log':str(log.relative_to(OUT)),'log_sha256':sha(log),'input_sha256':input_before,'input_stable':stable,'unexpected_success':attack!='none' and passed}
        records.append(record)
        print(json.dumps({k:record[k] for k in ['case','optimized','child_exit','stdout','input_stable','unexpected_success']}),flush=True)
        if not stable:raise RuntimeError('Actual verifier mutated copied inputs')
after={str(p.relative_to(SOURCE)):sha(p) if p.exists() else None for p in sorted(paths)}
(OUT/'source-after.json').write_text(json.dumps(after,indent=2))
drift={k:{'before':v,'after':after.get(k)} for k,v in before.items() if after.get(k)!=v}
result={'generated_by':str(Path(__file__)),'generator_sha256':sha(Path(__file__)),'target':str(SOURCE),'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),'status':git('status','--short'),'verifier_sha256':sha(SOURCE/PACKET/'verify_package.py'),'packet_manifest_sha256':sha(SOURCE/PACKET/'manifest.json'),'records':records,'source_drift':drift,'source_inventory_count':len(before),'verdict':'FAIL' if drift or any(r['unexpected_success'] for r in records) else 'PASS'}
with (OUT/'manifest.json').open('x') as f:json.dump(result,f,indent=2)
read=json.loads((OUT/'manifest.json').read_text())
if read['generator_sha256']!=result['generator_sha256'] or read['verdict']!=result['verdict']:raise RuntimeError('Receipt readback mismatch')
print(json.dumps({'output':str(OUT),'verdict':result['verdict'],'unexpected_successes':[r['case']+('/-O' if r['optimized'] else '') for r in records if r['unexpected_success']],'source_drift':list(drift)}))
