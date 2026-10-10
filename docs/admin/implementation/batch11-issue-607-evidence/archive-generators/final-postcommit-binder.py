"""External postcommit readback; never updates the committed handoff/catalogue."""
import argparse,datetime,gzip,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--pr',required=True);p.add_argument('--issues',nargs='+',required=True);a=p.parse_args()
assert not a.output.exists() and not a.output.resolve().is_relative_to(a.checkout.resolve())
def git(*args):return subprocess.check_output(['git',*args],cwd=a.checkout,text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
head,tree=git('rev-parse','HEAD','HEAD^{tree}').splitlines();branch=git('branch','--show-current')
remote=git('ls-remote','--heads','origin',branch);assert remote.split()[0]==head
paths=git('ls-files','-z').strip('\0').split('\0');hashes={n:sha(a.checkout/n) for n in paths}
packet=a.checkout/'docs/admin/implementation/batch11-issue-607-evidence';manifest=json.loads((packet/'packet-v2.json').read_text());source=json.loads(gzip.decompress((packet/manifest['current_source_receipt']).read_bytes()))
changed=[n for n,h in source['source_hashes'].items() if hashes.get(n)!=h];assert not changed
status=git('status','--porcelain');assert not status
archives=[n for n in paths if n.startswith('docs/admin/implementation/batch10-scroll-evidence/') or n=='docs/admin/implementation/BATCH_10_SCROLL_HANDOFF.md'];unchanged=[]
for n in archives:
 old=subprocess.check_output(['git','show','bcb5ff99854de595bbe3f7d60cc8796b7ada5a20:'+n],cwd=a.checkout);assert hashlib.sha256(old).hexdigest()==hashes[n];unchanged.append(n)
data={'generated_by':Path(__file__).name,'generator_sha256':sha(Path(__file__)),'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'final_remote_head':head,'final_tree':tree,'branch':branch,'status':status,'tracked_hashes':hashes,'tested_source_files':len(source['source_hashes']),'tested_source_changed':changed,'manifest':'packet-v2.json','manifest_sha256':sha(packet/'packet-v2.json'),'archival_paths_unchanged':unchanged,'pull_request':a.pr,'new_issues':a.issues,'recorded_full_acceptance':False,'hosted_acceptance':False,'production_acceptance':False,'issue_601':'unresolved','integration':'pending coordinator explicit accepted HEAD/tree transfer'}
with a.output.open('x') as f:json.dump(data,f,indent=2);f.write('\n')
assert json.loads(a.output.read_text())==data
print(json.dumps({k:v for k,v in data.items() if k not in ['tracked_hashes','archival_paths_unchanged']}))
