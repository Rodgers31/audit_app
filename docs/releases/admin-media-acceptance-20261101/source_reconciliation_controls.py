"""Offline negative controls for scoped source evidence; no product tests."""
from copy import deepcopy
import importlib.util
from io import BytesIO
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOL = HERE / 'reconcile_source_evidence.py'
full = json.loads((HERE / 'SOURCE_EVIDENCE.json').read_text())
minimal = deepcopy(full)
minimal['scopes'] = [deepcopy(full['scopes'][0])]
minimal['scopes'][0]['files'] = {k: v for k, v in minimal['scopes'][0]['files'].items() if k.endswith('test_media_cold_restore_acceptance.py')}
minimal['authoritative_scope'] = minimal['scopes'][0]['id']
minimal['historical_artifacts'] = [deepcopy(next(x for x in full['historical_artifacts'] if x['path'].endswith('status-sync-review-after.json')))]
minimal['historical_artifacts'][0]['source_fields'] = []
minimal['historical_artifacts'][0]['compare_to'] = []
results = []

def check(name, value, expected=None, raw=None):
    with tempfile.TemporaryDirectory(prefix='source-evidence-control-') as directory:
        receipt = Path(directory) / 'receipt.json'
        if name != 'missing receipt':
            receipt.write_text(raw if raw is not None else json.dumps(value))
        process = subprocess.run([sys.executable, str(TOOL), '--receipt', str(receipt)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=30)
        output = json.loads(process.stdout)
        if expected is None:
            assert process.returncode == 0 and output['status'] == 'VERIFIED_SOURCE_SCOPE_RECONCILIATION', (name, process.stderr, output)
        else:
            assert process.returncode == 2 and output['status'] == 'REFUSED' and output['reason'] == expected, (name, process.stderr, output)
        assert output['tests_executed'] is False and output['production_authorized'] is False
        results.append({'case': name, 'exit': process.returncode, 'reason': output.get('reason', output['status'])})

check('positive pinned-media source and preserved raw history', minimal)
check('missing receipt', None, 'SOURCE_RECEIPT_MISSING')
check('malformed JSON', None, 'SOURCE_RECEIPT_INVALID_JSON', raw='{')
check('duplicate JSON keys', None, 'DUPLICATE_JSON_KEY', raw='{"schema_version":1,"schema_version":1}')
check('oversized JSON', None, 'SOURCE_RECEIPT_TOO_LARGE', raw=' ' * (512 * 1024 + 1))
check('empty object', {}, 'INVALID_SOURCE_RECEIPT')
check('array root', [], 'INVALID_SOURCE_RECEIPT')
mutations = [
 ('boolean schema', lambda x: x.update(schema_version=True), 'INVALID_SOURCE_RECEIPT'),
 ('false test execution claim', lambda x: x.update(test_execution_during_reconciliation=True), 'INVALID_AUTHORITY_CLAIM'),
 ('production authorization', lambda x: x.update(production_authorized=True), 'INVALID_AUTHORITY_CLAIM'),
 ('no scopes', lambda x: x.update(scopes=[]), 'SOURCE_SCOPES_REQUIRED'),
 ('empty source map', lambda x: x['scopes'][0].update(files={}), 'SOURCE_FILES_REQUIRED'),
 ('wrong authoritative scope', lambda x: x.update(authoritative_scope='not_a_bound_scope'), 'AUTHORITATIVE_SCOPE_REQUIRED'),
 ('array authoritative scope', lambda x: x.update(authoritative_scope=[]), 'AUTHORITATIVE_SCOPE_REQUIRED'),
 ('object authoritative scope', lambda x: x.update(authoritative_scope={}), 'AUTHORITATIVE_SCOPE_REQUIRED'),
 ('short source commit', lambda x: x['scopes'][0].update(commit='bb3fa2b'), 'INVALID_SOURCE_COMMIT'),
 ('absent source commit', lambda x: x['scopes'][0].update(commit='f'*40), 'GIT_SOURCE_UNAVAILABLE'),
 ('wrong source hash', lambda x: x['scopes'][0].update(files={'backend/tests/social/test_media_cold_restore_acceptance.py':'0'*64}), 'SOURCE_BLOB_MISMATCH'),
 ('missing source blob', lambda x: x['scopes'][0].update(files={'backend/social/media/not-present.py':'0'*64}), 'GIT_SOURCE_UNAVAILABLE'),
 ('parent traversal source path', lambda x: x['scopes'][0].update(files={'../outside':'0'*64}), 'INVALID_SOURCE_PATH'),
 ('boolean source hash', lambda x: x['scopes'][0].update(files={'backend/tests/social/test_media_cold_restore_acceptance.py':True}), 'INVALID_SOURCE_HASH'),
 ('no raw history', lambda x: x.update(historical_artifacts=[]), 'HISTORICAL_INVENTORY_REQUIRED'),
 ('wrong raw historical hash', lambda x: x['historical_artifacts'][0].update(raw_sha256='0'*64), 'HISTORICAL_GIT_BYTES_CHANGED'),
 ('missing historical label', lambda x: x['historical_artifacts'][0].update(classification='current'), 'HISTORICAL_SCOPE_LABEL_REQUIRED'),
 ('malformed field selector', lambda x: x['historical_artifacts'][0].update(source_fields=None), 'INVALID_HISTORICAL_COMPARISON'),
 ('unhashable comparison scope', lambda x: x['historical_artifacts'][0].update(compare_to=[{}]), 'INVALID_HISTORICAL_COMPARISON'),
]
for name, mutate, reason in mutations:
    candidate = deepcopy(minimal); mutate(candidate); check(name, candidate, reason)

tree_bytes = subprocess.check_output(['git', 'show', minimal['scopes'][0]['commit'] + ':docs/releases'], cwd=ROOT)
tree = deepcopy(minimal)
tree['scopes'][0]['files'] = {'docs/releases': hashlib.sha256(tree_bytes).hexdigest()}
check('Git tree cannot count as a source file', tree, 'SOURCE_PATH_NOT_REGULAR_BLOB')

spec = importlib.util.spec_from_file_location('scoped_source_evidence', TOOL)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
original_open = Path.open
target = ROOT / minimal['historical_artifacts'][0]['path']
def changed_open(path, *args, **kwargs):
    return BytesIO(b'changed historical bytes') if path == target else original_open(path, *args, **kwargs)
with patch.object(Path, 'open', new=changed_open):
    try:
        module.verify(minimal, ROOT)
    except module.Refused as error:
        assert str(error) == 'HISTORICAL_WORKTREE_BYTES_CHANGED'
        results.append({'case':'direct API: modified historical bytes', 'reason':str(error)})
    else:
        raise AssertionError('Changed raw history was accepted')

comparison = deepcopy(minimal)
comparison['historical_artifacts'][0]['source_fields'] = ['sha256']
comparison['historical_artifacts'][0]['compare_to'] = [minimal['authoritative_scope']]
original_run = subprocess.run
def git_fault(arguments, *args, **kwargs):
    if 'ls-tree' in arguments and arguments[-1] == 'frontend/components/admin/social/SocialComposer.tsx':
        return subprocess.CompletedProcess(arguments, 128, stdout=b'', stderr=b'fatal: injected object database failure')
    return original_run(arguments, *args, **kwargs)
with patch.object(subprocess, 'run', new=git_fault):
    try:
        module.verify(comparison, ROOT)
    except module.Refused as error:
        assert str(error) == 'GIT_SOURCE_UNAVAILABLE'
        results.append({'case':'direct API: historical Git failure is not absence', 'reason':str(error)})
    else:
        raise AssertionError('Git failure was disguised as absent companion source')

original_history = target.read_bytes()
changed_history = json.loads(original_history)
source_path = 'frontend/components/admin/social/SocialComposer.tsx'
changed_history['sha256'][source_path] = hashlib.sha256(subprocess.check_output(
    ['git', 'show', minimal['scopes'][0]['commit'] + ':' + source_path], cwd=ROOT)).hexdigest()
replacement = json.dumps(changed_history).encode()
reads = [0]
def swapped_open(path, *args, **kwargs):
    if path != target:
        return original_open(path, *args, **kwargs)
    reads[0] += 1
    return BytesIO(original_history if reads[0] == 1 else replacement)
with patch.object(Path, 'open', new=swapped_open):
    observed = module.verify(comparison, ROOT)
assert reads[0] == 1, 'Historical maps must not be reopened after their raw hash passed'
assert source_path in observed['historical_artifacts'][0]['comparisons'][0]['different_files']
results.append({'case':'direct API: historical comparison uses the exact hashed byte snapshot',
                'historical_reads':reads[0]})
print(json.dumps({'status':'PASS','cases':len(results),'scope':'source_reconciliation_controls_only','product_tests_executed':False,'results':results},indent=2))
