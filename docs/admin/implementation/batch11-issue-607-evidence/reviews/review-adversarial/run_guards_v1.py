import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
CHECKOUT = Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
TOOLS = CHECKOUT / 'docs/admin/implementation/batch11-issue-607-evidence/tools'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def snapshot(name):
    path = TOOLS / name
    digest = sha(path)
    target = ROOT / (path.stem + '-' + digest + '.py')
    if not target.exists(): target.write_bytes(path.read_bytes())
    assert sha(target) == digest
    spec = importlib.util.spec_from_file_location(path.stem, target)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module, digest
V, verifier_hash = snapshot('verify_packet.py')
R, replay_hash = snapshot('replay.py')
RUN = ROOT / ('guards-v1-' + time.strftime('%Y%m%dT%H%M%S'))
RUN.mkdir()
results = []
def record(name, expect_reject, callback):
    try:
        value = callback()
        rejected = False
        entry = {'name':name, 'expected_rejection':expect_reject, 'rejected':False, 'return':str(value)}
    except Exception as e:
        rejected = True
        entry = {'name':name, 'expected_rejection':expect_reject, 'rejected':True, 'exception_type':type(e).__name__, 'exception':str(e)}
    entry['matches_expectation'] = rejected == expect_reject
    results.append(entry)
    print(json.dumps(entry))

files = RUN / 'files'
files.mkdir()
(files / 'valid.json').write_text('{"ok":true}')
(files / 'nested').mkdir()
(files / 'nested' / 'file.json').write_text('{}')
(RUN / 'outside.json').write_text('{}')
(files / 'link.json').symlink_to(RUN / 'outside.json')
(files / 'linked-directory').symlink_to(files / 'nested', target_is_directory=True)
(RUN / 'root-link').symlink_to(files, target_is_directory=True)
record('relative_file/valid-control', False, lambda: V.relative_file(files, 'valid.json'))
for name, value in [('absent','absent.json'), ('empty',''), ('none',None), ('bool',True), ('zero',0), ('absolute',str(RUN / 'outside.json')),
                    ('outside','../outside.json'), ('noncanonical','nested/../valid.json'), ('dot','./valid.json'), ('double-slash','nested//file.json'),
                    ('trailing-slash','nested/file.json/'), ('symlink-file','link.json'), ('symlink-parent','linked-directory/file.json'), ('directory','nested'), ('null-byte','a\0b')]:
    record('relative_file/' + name, True, lambda value=value: V.relative_file(files, value))
record('relative_file/symlink-root', True, lambda: V.relative_file(RUN / 'root-link', 'valid.json'))
load_values = [('valid','{"x":1}',False), ('empty','',True), ('malformed','{oops',True), ('duplicate','{"x":1,"x":2}',True),
               ('nested-duplicate','{"outer":{"x":1,"x":2}}',True), ('nan','{"x":NaN}',True), ('infinity','{"x":Infinity}',True),
               ('negative-infinity','{"x":-Infinity}',True), ('primitive-bool','true',False), ('primitive-null','null',False)]
for name, raw, rejected in load_values:
    path = files / ('load-' + name + '.json')
    path.write_text(raw)
    record('load/' + name, rejected, lambda path=path:V.load(path))
record('load/absent', True, lambda: V.load(files / 'absent.json'))
badgzip = files / 'bad.json.gz'
badgzip.write_bytes(b'not gzip')
record('load/invalid-gzip', True, lambda: V.load(badgzip))
goodgzip = files / 'valid.json.gz'
goodgzip.write_bytes(gzip.compress(b'{"x":1}'))
record('load/gzip-control', False, lambda: V.load(goodgzip))

# Replay dependencies are controlled fakes. This never calls Docker or a browser.
fixture_source = RUN / 'checkout'
(fixture_source / 'frontend').mkdir(parents=True)
(fixture_source / 'source.ts').write_text('fixture source\n')
output_root = RUN / 'outputs'
output_root.mkdir()
default_meta = {'Config':{'Labels':{'audit_app.owner':'batch11-navigation'}}, 'State':{'Running':True},
                'HostConfig':{'PortBindings':{}}, 'Mounts':[{'Source':str(fixture_source),'Destination':'/app'}, {'Source':str(output_root),'Destination':'/evidence'}]}
context = {'meta':default_meta, 'child_exit':0, 'report_variant':'valid', 'run_calls':0, 'inspect_calls':0}
real_which, real_check_output, real_run = R.shutil.which, R.subprocess.check_output, R.subprocess.run
R.shutil.which = lambda name:'/fixture/docker' if name == 'docker' else real_which(name)
def fake_output(command, **kwargs):
    if command[0] == '/fixture/docker':
        context['inspect_calls'] += 1
        return json.dumps([context['meta']]).encode()
    if command[:3] == ['git','ls-files','-z']:
        return b'source.ts\0'
    if command[:2] == ['git','rev-parse']:
        return '0'*40 + '\n' + '1'*40 + '\n'
    raise AssertionError('Unexpected subprocess: ' + repr(command))
R.subprocess.check_output = fake_output
def fake_run(command, **kwargs):
    context['run_calls'] += 1
    log = Path(kwargs['stdout'].name)
    out = log.parent
    kwargs['stdout'].write('Controlled fake child; no browser or Docker execution.\n')
    if context['report_variant'] == 'missing':
        return SimpleNamespace(returncode=context['child_exit'])
    specs=[]
    for index in range(6):
        specs.append({'id':'fake-%d'%index,'file':'fixture.spec.ts','title':'fixture case %d'%index,'line':index+1,'column':1,
                      'tests':[{'projectName':'chromium','expectedStatus':'passed','status':'expected','results':[{'status':'passed','retry':0,'duration':1,'errors':[]}]}]})
    report = {'errors':[],'suites':[{'specs':specs,'suites':[]}], 'stats':{'expected':6,'unexpected':0,'skipped':0,'flaky':0,'duration':6}}
    variant = context['report_variant']
    if variant == 'empty': report = {'errors':[],'suites':[],'stats':{'expected':0,'unexpected':0,'skipped':0,'flaky':0,'duration':0}}
    elif variant == 'hidden-errors': report['errors']=[{'message':'hidden failure'}]
    elif variant == 'retry': report['suites'][0]['specs'][0]['tests'][0]['results'][0]['retry']=1
    elif variant == 'counter-bool': report['stats']['expected']=True
    elif variant == 'duration-bool': report['stats']['duration']=True
    elif variant == 'duplicate': report['suites'][0]['specs'][1]['id']=report['suites'][0]['specs'][0]['id']
    elif variant == 'missing-case': report['suites'][0]['specs'].pop(); report['stats']['expected']=5
    elif variant == 'source-drift': (fixture_source / 'source.ts').write_text('drifted source\n')
    (out / 'report.json').write_text(json.dumps(report))
    return SimpleNamespace(returncode=context['child_exit'])
R.subprocess.run = fake_run
index = 0
def replay_attack(name, mutation=None, expect_reject=True, output=None, checkout=None, cohort='public', mode='focused'):
    global index
    index += 1
    context.update(meta=copy.deepcopy(default_meta), child_exit=0, report_variant='valid', run_calls=0, inspect_calls=0)
    (fixture_source / 'source.ts').write_text('fixture source\n')
    if mutation: mutation()
    target = output if output is not None else output_root / ('run-%02d-%s' % (index,name))
    record('replay/' + name, expect_reject, lambda:R.execute(checkout if checkout is not None else fixture_source,target,'fake-owned-container','unix:///fixture/docker.sock',cohort,mode))
    results[-1].update(fake_child_calls=context['run_calls'],fake_inspect_calls=context['inspect_calls'])
replay_attack('valid-control',expect_reject=False)
for name, cohort, mode in [('unsupported-cohort','other','focused'),('null-cohort',None,'focused'),('bool-cohort',True,'focused'),
                          ('unsupported-mode','public','wrong'),('null-mode','public',None),('bool-mode','public',True),('wrong-mode-cohort','users','focused')]:
    replay_attack(name,cohort=cohort,mode=mode)
replay_attack('inside-checkout',output=fixture_source / 'inside')
replay_attack('missing-output-parent',output=RUN / 'missing-parent' / 'output')
existing = output_root / 'existing'; existing.mkdir()
replay_attack('existing-output',output=existing)
output_link = output_root / 'linked'; output_link.symlink_to(existing,target_is_directory=True)
replay_attack('symlink-output',output=output_link)
parent_link = RUN / 'linked-outputs'; parent_link.symlink_to(output_root,target_is_directory=True)
replay_attack('symlink-output-parent',output=parent_link / 'fresh')
for name, mutation in [
 ('unowned-container',lambda:context['meta']['Config']['Labels'].update({'audit_app.owner':'other'})),
 ('missing-ownership',lambda:context['meta']['Config']['Labels'].clear()),
 ('stopped-container',lambda:context['meta']['State'].update(Running=False)),
 ('running-bool-string',lambda:context['meta']['State'].update(Running='false')),
 ('published-ports',lambda:context['meta']['HostConfig'].update(PortBindings={'3141/tcp':[{'HostPort':'13032'}]})),
 ('source-mount-mismatch',lambda:context['meta']['Mounts'][0].update(Source=str(RUN / 'other-checkout'))),
 ('outside-evidence-mount',lambda:context['meta']['Mounts'][1].update(Source=str(RUN / 'other-evidence'))),
 ('duplicate-evidence-mount',lambda:context['meta']['Mounts'].append(copy.deepcopy(context['meta']['Mounts'][1]))),
 ('child-nonzero',lambda:context.update(child_exit=1)),
 ('child-bool',lambda:context.update(child_exit=False)),
 ('missing-report',lambda:context.update(report_variant='missing')),
 ('empty-report',lambda:context.update(report_variant='empty')),
 ('hidden-report-errors',lambda:context.update(report_variant='hidden-errors')),
 ('retried-report',lambda:context.update(report_variant='retry')),
 ('bool-report-counter',lambda:context.update(report_variant='counter-bool')),
 ('bool-report-duration',lambda:context.update(report_variant='duration-bool')),
 ('duplicate-report-case',lambda:context.update(report_variant='duplicate')),
 ('missing-report-case',lambda:context.update(report_variant='missing-case')),
 ('source-drift',lambda:context.update(report_variant='source-drift')),
]: replay_attack(name,mutation)
replay_attack('absent-checkout',checkout=RUN / 'absent-checkout')
R.shutil.which, R.subprocess.check_output, R.subprocess.run = real_which, real_check_output, real_run
receipt={'schema':1,'python_version':sys.version,'verifier_sha256':verifier_hash,'replay_sha256':replay_hash,
         'script_sha256':sha(Path(__file__)),'no_real_docker_browser_or_database_calls':True,
         'results':results,'tested_cases':len(results),'unexpected_acceptances':sum(not r['matches_expectation'] for r in results),
         'verifier_after':sha(TOOLS / 'verify_packet.py'),'replay_after':sha(TOOLS / 'replay.py')}
(RUN / 'results.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'results':str(RUN / 'results.json'),'tested_cases':len(results),'unexpected_acceptances':receipt['unexpected_acceptances'],
                  'verifier_sha256':verifier_hash,'replay_sha256':replay_hash}))
