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

ROOT = Path(__file__).resolve().parent
CHECKOUT = Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
VERIFIER = CHECKOUT / 'docs/admin/implementation/batch11-issue-607-evidence/tools/verify_packet.py'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
verifier_hash = sha(VERIFIER)
SNAPSHOT = ROOT / ('verify_packet-' + verifier_hash + '.py')
if not SNAPSHOT.exists(): SNAPSHOT.write_bytes(VERIFIER.read_bytes())
assert sha(SNAPSHOT) == verifier_hash
module_spec = importlib.util.spec_from_file_location('tested_packet_verifier', SNAPSHOT)
V = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(V)
RUN = ROOT / ('attack-v5-' + time.strftime('%Y%m%dT%H%M%S'))
RUN.mkdir()
results = []
def record(name, expect_reject, callback):
    try:
        value = callback()
        rejected = False
        entry = {'name': name, 'expected_rejection': expect_reject, 'rejected': False, 'return': value}
    except Exception as e:
        rejected = True
        entry = {'name': name, 'expected_rejection': expect_reject, 'rejected': True, 'exception_type': type(e).__name__, 'exception': str(e)}
    entry['matches_expectation'] = rejected == expect_reject
    results.append(entry)
    print(json.dumps(entry, allow_nan=False))

def report(status='passed'):
    return {'errors': [], 'suites': [{'specs': [{'id': 'fixture-id-1', 'file': 'county.spec.ts', 'title': 'fixture case', 'line': 1, 'column': 1,
       'tests': [{'projectName': 'chromium', 'expectedStatus': 'skipped' if status == 'skipped' else 'passed',
                  'status': 'expected' if status == 'passed' else 'skipped' if status == 'skipped' else 'unexpected',
                  'results': [{'status': status, 'retry': 0, 'duration': 1, 'errors': [] if status != 'failed' else [{'message': 'fixture failure'}]}]}]}], 'suites': []}],
       'stats': {'expected': int(status == 'passed'), 'unexpected': int(status == 'failed'), 'skipped': int(status == 'skipped'), 'flaky': 0, 'duration': 1}}
def result(r): return r['suites'][0]['specs'][0]['tests'][0]['results'][0]
def test(r): return r['suites'][0]['specs'][0]['tests'][0]
def spec(r): return r['suites'][0]['specs'][0]
def multi_report(size, status='passed'):
    r=report(status)
    prototype=copy.deepcopy(spec(r))
    r['suites'][0]['specs']=[]
    for i in range(size):
        row=copy.deepcopy(prototype)
        row.update(id='fixture-id-%d' % (i+1), title='fixture case %d' % (i+1), line=i+1)
        if size == 6:
            row.update(file=sorted(V.NEW_TESTS)[i // 3][len('frontend/e2e/'):], line=(i % 3) + 1)
        if size == 3:
            row.update(file='smart-back.spec.ts', line=72, column=7, title='scroll position is roughly preserved after smart-back')
        r['suites'][0]['specs'].append(row)
    for key in ['expected','unexpected','skipped']:
        r['stats'][key]*=size
    r['stats']['duration']=size
    r['config']={'rootDir':'/app/frontend/e2e'}
    return r
def attack_case(name, mutate):
    r = report()
    mutate(r)
    record('cases/' + name, True, lambda: V.cases(r))
record('cases/valid-passing-control', False, lambda: V.cases(report()))
record('cases/valid-failed-control', False, lambda: V.cases(report('failed')))
for name, value in [('none', None), ('empty-object', {}), ('empty-list', []), ('primitive-true', True), ('primitive-zero', 0), ('primitive-string', 'passed')]:
    record('cases/' + name, True, lambda value=value: V.cases(value))
for name, mutate in [
 ('empty-suites', lambda r: r.update(suites=[])),
 ('empty-specs', lambda r: r['suites'][0].update(specs=[])),
 ('missing-errors', lambda r: r.pop('errors')),
 ('top-error', lambda r: r.update(errors=[{'message':'hidden failure'}])),
 ('duplicate-case-id', lambda r: r['suites'][0]['specs'].append(copy.deepcopy(spec(r)))),
 ('bool-line', lambda r: spec(r).update(line=True)),
 ('bool-column', lambda r: spec(r).update(column=True)),
 ('zero-line', lambda r: spec(r).update(line=0)),
 ('negative-line', lambda r: spec(r).update(line=-1)),
 ('null-title', lambda r: spec(r).update(title=None)),
 ('empty-id', lambda r: spec(r).update(id='')),
 ('missing-results', lambda r: test(r).pop('results')),
 ('empty-results', lambda r: test(r).update(results=[])),
 ('duplicate-results', lambda r: test(r)['results'].append(copy.deepcopy(result(r)))),
 ('retry-one', lambda r: result(r).update(retry=1)),
 ('retry-bool', lambda r: result(r).update(retry=False)),
 ('duration-bool', lambda r: result(r).update(duration=True)),
 ('duration-negative', lambda r: result(r).update(duration=-1)),
 ('duration-nan', lambda r: result(r).update(duration=float('nan'))),
 ('duration-infinity', lambda r: result(r).update(duration=float('inf'))),
 ('duration-negative-infinity', lambda r: result(r).update(duration=float('-inf'))),
 ('duration-null', lambda r: result(r).update(duration=None)),
 ('status-interrupted', lambda r: result(r).update(status='interrupted')),
 ('status-bool', lambda r: result(r).update(status=True)),
 ('hidden-error', lambda r: result(r).update(error={'message':'hidden failure'})),
 ('hidden-errors', lambda r: result(r).update(errors=[{'message':'hidden failure'}])),
 ('invalid-errors-bool', lambda r: result(r).update(errors=False)),
 ('counter-bool', lambda r: r['stats'].update(expected=True)),
 ('counter-negative', lambda r: r['stats'].update(expected=-1)),
 ('counter-nan', lambda r: r['stats'].update(expected=float('nan'))),
 ('counter-infinity', lambda r: r['stats'].update(expected=float('inf'))),
 ('counter-mismatch', lambda r: r['stats'].update(expected=2)),
 ('stats-duration-negative', lambda r: r['stats'].update(duration=-1)),
 ('stats-duration-bool', lambda r: r['stats'].update(duration=True)),
 ('stats-duration-nan', lambda r: r['stats'].update(duration=float('nan'))),
 ('stats-duration-infinity', lambda r: r['stats'].update(duration=float('inf'))),
]: attack_case(name, mutate)

BASE = RUN / 'base'
PACKET = BASE / 'packet'
SOURCE = BASE / 'checkout'
PACKET.mkdir(parents=True)
SOURCE.mkdir()
(SOURCE / 'source.ts').write_text('fixture source\n')
for name in V.NEW_TESTS:
    (SOURCE / name).parent.mkdir(parents=True, exist_ok=True)
    (SOURCE / name).write_text('fixture regression source\n')
def write(p, data): p.write_text(json.dumps(data, indent=2, allow_nan=True) + '\n')
write(PACKET / 'red-report.json', report('failed'))
write(PACKET / 'green-report.json', multi_report(6))
write(PACKET / 'pending-report.json', multi_report(3))
write(PACKET / 'diagnostic-report.json', multi_report(6))
source_receipt = {'source_changed': [], 'helpers_changed': [], 'generator_unchanged': True, 'timed_out': False, 'child_exit': 0,
                  'source_hashes': {name: sha(SOURCE / name) for name in {'source.ts'} | V.NEW_TESTS}}
write(PACKET / 'current-source.json', source_receipt)
write(PACKET / 'green-receipt.json', source_receipt)
write(PACKET / 'red-receipt.json', dict(source_receipt, child_exit=1))
write(PACKET / 'diagnostic-receipt.json', source_receipt)
write(PACKET / 'cohort-receipt.json', {'child_exit': 0, 'verification_exit': 0})
manifest = {'schema': 1, 'current_source_receipt': 'current-source.json', 'current_inventory': 'inventory.json', 'files': {},
 'runs': [{'name':'fixture-red', 'category': 'historical-red', 'report': 'red-report.json', 'receipt':'red-receipt.json', 'counts': {'expected': 0, 'unexpected': 1, 'skipped': 0, 'flaky': 0}, 'case_ids': ['fixture-id-1']},
          {'name':'focused-green', 'category': 'current-acceptance', 'report': 'green-report.json', 'receipt': 'green-receipt.json', 'counts': {'expected': 6, 'unexpected': 0, 'skipped': 0, 'flaky': 0}, 'case_ids': ['fixture-id-%d' % i for i in range(1,7)]},
          {'name':'pending-original-green', 'category': 'current-acceptance', 'report': 'pending-report.json', 'receipt': 'green-receipt.json', 'counts': {'expected': 3, 'unexpected': 0, 'skipped': 0, 'flaky': 0}, 'case_ids': ['fixture-id-%d' % i for i in range(1,4)]}]}
manifest['runs'].append({'name':'fixture-diagnostic-positive','category':'diagnostic-positive','report':'diagnostic-report.json','receipt':'diagnostic-receipt.json',
                         'counts':{'expected':6,'unexpected':0,'skipped':0,'flaky':0},'case_ids':['fixture-id-%d' % i for i in range(1,7)]})
groups = []
baseline = []
ordinal = 0
for cohort, size in [('public',275), ('users',4), ('operations',6), ('overview-audit',5), ('etl-ui',28), ('coordinator',11)]:
    specs = []
    descriptors = []
    skipped = 0
    for local_index in range(size):
        ordinal += 1
        status = 'skipped' if 7 <= ordinal <= 17 else 'passed'
        skipped += int(status == 'skipped')
        row = spec(report(status))
        row.update(id='fixture-id-%d' % ordinal, line=ordinal, title='fixture case %d' % ordinal)
        if ordinal <= 6:
            row.update(file=sorted(V.NEW_TESTS)[(ordinal - 1) // 3][len('frontend/e2e/'):], line=((ordinal - 1) % 3) + 1)
        specs.append(row)
        descriptor = json.dumps({key:row[key] for key in ['file','line','column','title']}, separators=(',',':'), ensure_ascii=False)
        descriptors.append(descriptor)
    full_report = {'errors':[], 'suites':[{'specs':specs, 'suites':[]}], 'config':{'rootDir':'/app/frontend/e2e'},
                   'stats':{'expected':size-skipped, 'unexpected':0, 'skipped':skipped, 'flaky':0, 'duration':size}}
    filename = 'full-' + cohort + '.json'
    write(PACKET / filename, full_report)
    groups.append({'name':cohort, 'cases':descriptors})
    baseline.extend(descriptors)
    manifest['runs'].append({'name':'full-' + cohort, 'category':'current-acceptance', 'report':filename, 'receipt':'green-receipt.json',
                            'cohort_receipt':'cohort-receipt.json', 'counts':full_report['stats'].copy(), 'case_ids':[s['id'] for s in specs]})
    manifest['runs'][-1]['counts'].pop('duration')
write(PACKET / 'inventory.json', {'total':329, 'originalTotal':323, 'cohorts':groups, 'baseline':baseline})
real_check_output = subprocess.check_output
def controlled_git(args, *a, **kw):
    if args == ['git','ls-tree','-r','--name-only',V.BASE] and Path(kw.get('cwd')) != CHECKOUT:
        return 'source.ts\n'
    return real_check_output(args, *a, **kw)
subprocess.check_output = controlled_git
def catalogue(packet, data):
    data['files'] = {p.relative_to(packet).as_posix(): sha(p) for p in packet.rglob('*') if p.is_file() and p.name != 'packet-v1.json'}
    write(packet / 'packet-v1.json', data)
catalogue(PACKET, manifest)
record('verify/valid-controlled-fixture', False, lambda: V.verify(PACKET, SOURCE))
index = 0
def attack_packet(name, mutate, refresh=True):
    global index
    index += 1
    folder = RUN / ('fixture-%02d-%s' % (index, name))
    shutil.copytree(BASE, folder)
    packet, source = folder / 'packet', folder / 'checkout'
    data = json.loads((packet / 'packet-v1.json').read_text())
    mutate(packet, source, data)
    if refresh: catalogue(packet, data)
    record('verify/' + name, True, lambda: V.verify(packet, source))
def edit_json(path, mutate):
    data = json.loads(path.read_text())
    mutate(data)
    write(path, data)
for name, mutate in [
 ('manifest-schema-bool', lambda p,s,d: d.update(schema=True)),
 ('manifest-schema-negative', lambda p,s,d: d.update(schema=-1)),
 ('empty-runs', lambda p,s,d: d.update(runs=[])),
 ('missing-red-category', lambda p,s,d: d.update(runs=d['runs'][1:])),
 ('missing-acceptance-category', lambda p,s,d: d.update(runs=d['runs'][:1])),
 ('missing-report', lambda p,s,d: (p / 'green-report.json').unlink()),
 ('missing-receipt', lambda p,s,d: (p / 'green-receipt.json').unlink()),
 ('empty-report', lambda p,s,d: (p / 'green-report.json').write_text('')),
 ('malformed-report', lambda p,s,d: (p / 'green-report.json').write_text('{oops')),
 ('wrong-report-schema', lambda p,s,d: write(p / 'green-report.json', {'success': True})),
 ('duplicate-json-keys', lambda p,s,d: (p / 'green-receipt.json').write_text('{"child_exit":2,"child_exit":0}')),
 ('bool-declared-counts', lambda p,s,d: d['runs'][1]['counts'].update(expected=True, unexpected=False, skipped=False, flaky=False)),
 ('null-case-inventory', lambda p,s,d: d['runs'][1].update(case_ids=None)),
 ('empty-case-inventory', lambda p,s,d: d['runs'][1].update(case_ids=[])),
 ('duplicate-case-inventory', lambda p,s,d: d['runs'][1].update(case_ids=['fixture-id-1','fixture-id-1'])),
 ('substituted-case-inventory', lambda p,s,d: d['runs'][1].update(case_ids=['substitute'])),
 ('substituted-green-report', lambda p,s,d: d['runs'][1].update(report='red-report.json')),
 ('acceptance-child-bool', lambda p,s,d: edit_json(p / 'green-receipt.json', lambda j:j.update(child_exit=False))),
 ('acceptance-child-nonzero', lambda p,s,d: edit_json(p / 'green-receipt.json', lambda j:j.update(child_exit=1))),
 ('acceptance-timed-out', lambda p,s,d: edit_json(p / 'green-receipt.json', lambda j:j.update(timed_out=True))),
 ('acceptance-source-drift', lambda p,s,d: edit_json(p / 'green-receipt.json', lambda j:j.update(source_changed=['source.ts']))),
 ('acceptance-helper-drift', lambda p,s,d: edit_json(p / 'green-receipt.json', lambda j:j.update(helpers_changed=['verifier.py']))),
 ('acceptance-generator-changed', lambda p,s,d: edit_json(p / 'green-receipt.json', lambda j:j.update(generator_unchanged=False))),
 ('source-child-bool', lambda p,s,d: edit_json(p / 'current-source.json', lambda j:j.update(child_exit=False))),
 ('source-timed-out', lambda p,s,d: edit_json(p / 'current-source.json', lambda j:j.update(timed_out=True))),
 ('source-drift', lambda p,s,d: edit_json(p / 'current-source.json', lambda j:j.update(source_changed=['source.ts']))),
 ('source-empty-inventory', lambda p,s,d: edit_json(p / 'current-source.json', lambda j:j.update(source_hashes={}))),
 ('source-mismatch', lambda p,s,d: (s / 'source.ts').write_text('substituted\n')),
 ('red-helper-drift', lambda p,s,d: edit_json(p / 'red-receipt.json', lambda j:j.update(helpers_changed=['producer.py']))),
 ('red-source-drift', lambda p,s,d: edit_json(p / 'red-receipt.json', lambda j:j.update(source_changed=['source.ts']))),
 ('red-generator-drift', lambda p,s,d: edit_json(p / 'red-receipt.json', lambda j:j.update(generator_unchanged=False))),
 ('red-timed-out', lambda p,s,d: edit_json(p / 'red-receipt.json', lambda j:j.update(timed_out=True))),
 ('red-child-bool', lambda p,s,d: edit_json(p / 'red-receipt.json', lambda j:j.update(child_exit=True))),
 ('red-child-zero', lambda p,s,d: edit_json(p / 'red-receipt.json', lambda j:j.update(child_exit=0))),
 ('diagnostic-helper-drift', lambda p,s,d: edit_json(p / 'diagnostic-receipt.json', lambda j:j.update(helpers_changed=['producer.py']))),
 ('diagnostic-all-skipped', lambda p,s,d: (write(p / 'diagnostic-report.json', multi_report(6,'skipped')), d['runs'][3].update(counts={'expected':0,'unexpected':0,'skipped':6,'flaky':0}))),
 ('diagnostic-failed-report', lambda p,s,d: d['runs'][3].update(report='red-report.json',receipt='red-receipt.json',counts={'expected':0,'unexpected':1,'skipped':0,'flaky':0},case_ids=['fixture-id-1'])),
 ('focused-same-count-operations-substitution', lambda p,s,d: d['runs'][1].update(report='full-operations.json',case_ids=next(r['case_ids'] for r in d['runs'] if r['name']=='full-operations'))),
 ('report-traversal', lambda p,s,d: d['runs'][1].update(report='../outside.json')),
 ('source-traversal', lambda p,s,d: edit_json(p / 'current-source.json', lambda j:j.update(source_hashes={'../outside.ts': '0'*64}))),
 ('report-absolute', lambda p,s,d: d['runs'][1].update(report='/tmp/outside.json')),
 ('report-symlink', lambda p,s,d: ((p / 'green-report.json').unlink(), (p / 'green-report.json').symlink_to(PACKET / 'green-report.json'))),
 ('source-symlink', lambda p,s,d: ((s / 'source.ts').unlink(), (s / 'source.ts').symlink_to(SOURCE / 'source.ts'))),
 ('historical-red-all-passed', lambda p,s,d: (write(p / 'red-report.json', report()), d['runs'][0].update(counts={'expected':1,'unexpected':0,'skipped':0,'flaky':0}))),
 ('current-acceptance-all-skipped', lambda p,s,d: (write(p / 'green-report.json', multi_report(6, 'skipped')), d['runs'][1].update(counts={'expected':0,'unexpected':0,'skipped':6,'flaky':0}))),
 ('historical-substituted-same-green-report', lambda p,s,d: d['runs'][0].update(report='green-report.json', counts={'expected':1,'unexpected':0,'skipped':0,'flaky':0})),
]: attack_packet(name, mutate)
record('verify/absent-packet', True, lambda: V.verify(RUN / 'absent', SOURCE))
record('verify/null-packet', True, lambda: V.verify(None, SOURCE))
record('verify/null-checkout', True, lambda: V.verify(PACKET, None))
record('verify/unsafe-manifest', True, lambda: V.verify(PACKET, SOURCE, '../outside.json'))

def cli_output(name, path):
    command = [sys.executable, str(SNAPSHOT), '--packet', str(PACKET), '--checkout', str(SOURCE), '--output', str(path)]
    proc = subprocess.run(command, capture_output=True, text=True)
    results.append({'name':'cli-output/' + name, 'expected_rejection':True, 'rejected':proc.returncode != 0,
                    'matches_expectation':proc.returncode != 0, 'command':command, 'exit':proc.returncode, 'stdout':proc.stdout, 'stderr':proc.stderr})
cli_output('inside-packet', PACKET / 'output.json')
cli_output('inside-checkout', SOURCE / 'output.json')
existing = RUN / 'existing.json'
existing.write_text('{}')
cli_output('existing-output', existing)
cli_output('missing-parent', RUN / 'missing-parent' / 'output.json')
out_link = RUN / 'output-link.json'
out_link.symlink_to(existing)
cli_output('symlinked-output', out_link)
dir_link = RUN / 'linked-directory'
dir_link.symlink_to(BASE, target_is_directory=True)
cli_output('symlinked-output-parent', dir_link / 'output.json')

tracked = subprocess.check_output(['git','ls-files','-z'], cwd=CHECKOUT).decode().split('\0')
inventory = {name: sha(CHECKOUT / name) for name in tracked if name and (CHECKOUT / name).is_file()}
inventory[VERIFIER.relative_to(CHECKOUT).as_posix()] = verifier_hash
(RUN / 'source-inventory.json.gz').write_bytes(gzip.compress(json.dumps(inventory, sort_keys=True).encode(), mtime=0))
receipt = {'schema':1, 'python_version':sys.version, 'verifier_original':str(VERIFIER), 'verifier_sha256':verifier_hash, 'verifier_snapshot':str(SNAPSHOT),
           'attack_script':str(Path(__file__)), 'attack_script_sha256':sha(Path(__file__)),
           'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=CHECKOUT,text=True).strip(),
           'git_tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=CHECKOUT,text=True).strip(),
           'source_inventory':str(RUN / 'source-inventory.json.gz'), 'source_inventory_sha256':sha(RUN / 'source-inventory.json.gz'),
           'tested_cases':len(results), 'unexpected_acceptances':sum(not r['matches_expectation'] for r in results),
           'verifier_original_hash_after':sha(VERIFIER), 'results':results}
write(RUN / 'results.json', receipt)
print(json.dumps({'results':str(RUN / 'results.json'), 'tested_cases':len(results), 'unexpected_acceptances':receipt['unexpected_acceptances'], 'verifier_sha256':verifier_hash}))
