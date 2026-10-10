"""Read back final delivery receipts, immutable generators and archived output."""
import hashlib
import json
from pathlib import Path
import tarfile
import argparse
root = Path(__file__).resolve().parents[1]
evidence = root / 'batch9-legacy-etl-evidence'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--historical-only', action='store_true', help='Verify author history without certifying edited candidate sources')
args = parser.parse_args()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(name):
    return json.loads((evidence / name).read_text())
HISTORICAL_ARCHIVE_SHA256 = '64fbeba3b51ffac41257609e2513e6537d3db457806de460ee30625078420ef6'
AUTHOR_COMMIT = 'b4128f7012951d79e0fc4c58305a60a3baafd7aa'
CURRENT_SOURCE_PATHS = {
    'backend/requirements.txt', 'backend/requirements-dev.txt', 'etl/requirements.txt',
    'etl/database_loader.py', 'etl/writer_ownership.py', 'etl/worker.py', 'etl/backfill.py',
    'etl/kenya_pipeline.py', 'etl/monitored_runner.py', 'etl/scheduler.py',
    'backend/tests/test_batch9_legacy_etl_ownership.py', 'backend/tests/test_batch9_legacy_etl_sessions.py',
    'backend/tests/test_batch9_legacy_receipt_integrity.py',
    'backend/tests/batch9_legacy_fixture/entry.py', 'backend/tests/batch9_legacy_fixture/sitecustomize.py',
    'backend/tests/batch9_legacy_fixture/batch9_legacy_target.py',
    '.github/scripts/run_backend_tests.py', '.github/scripts/tests/test_backend_test_launcher.py',
    'batch9-legacy-etl-evidence/run_receipt.py', 'batch9-legacy-etl-evidence/verify_delivery.py',
    'batch9-legacy-etl-evidence/review_receipt_generator.py',
    'batch9-legacy-etl-evidence/historical-source.tar.gz', 'batch9-legacy-etl-evidence/historical-source-manifest.json',
    'backend/seeding/exclusion.py', 'backend/models.py', 'backend/database.py',
    'backend/admin_etl_dispatch.py', 'backend/admin_etl_dispatch_worker.py',
}

def require(condition, detail):
    if not condition:
        raise ValueError(f'Delivery verification failed: {detail}')
historical_archive = evidence / 'historical-source.tar.gz'
require(digest(historical_archive) == HISTORICAL_ARCHIVE_SHA256, 'historical archive identity')
with tarfile.open(historical_archive, 'r:gz') as archive:
    historical_sources = {member.name: archive.extractfile(member).read() for member in archive.getmembers() if member.isfile()}

def historical_bytes(path, cohort='final'):
    key = cohort + '/' + path
    require(key in historical_sources, f'historical source unavailable: {key}')
    return historical_sources[key]

def historical_digest(path):
    return hashlib.sha256(historical_bytes(path)).hexdigest()
writer = historical_digest('etl/writer_ownership.py')
wrapper = historical_digest('batch9-legacy-etl-evidence/run_receipt.py')
require(wrapper == '519b548f3760f324c3a44fa2616a2e56ff4819d6fa9f5909a94e0d14868011bd', 'integrity condition at original line 38')
finals = ['process-final-minimum.json', 'process-final-current.json', 'critical-lint-final.json', 'refusal-storage-green-current.json', 'refusal-storage-green-minimum.json', 'refusal-storage-final-spec-independent.json', 'spec-refusal-final-independent-green.json', 'spec-session-final-independent-green.json', 'spec-scheduler-final-independent-green.json']
finals += [f'standards-{kind}-final2-{runtime}independent.json' for kind in ('session', 'readiness', 'refusal') for runtime in ('', 'minimum-')]
checked = []
for name in finals:
    receipt = read(name)
    require(receipt['verdict'] == 'PASSED', name)
    if 'exit_code' in receipt:
        require(receipt['exit_code'] == 0, name)
    require(historical_digest(receipt['generated_by']) == receipt['generator_sha256'], name)
    if 'etl/writer_ownership.py' in receipt['source_sha256']:
        require(receipt['source_sha256']['etl/writer_ownership.py'] == writer, name)
    for (path, expected) in receipt['source_sha256'].items():
        require(historical_digest(path) == expected, (name, path))
    if name.startswith('process-final'):
        require('77 passed' in receipt['output'] and 'skipped' not in receipt['output'] and ('xfailed' not in receipt['output']), 'integrity condition at original line 57')
    checked.append(name)
for name in ('behavior-review-recheck-acceptance.json', 'standards-final-replay-readback.json'):
    assessment = read(name)
    require(assessment['verdict'] == 'PASSED', name)
    require(historical_digest(assessment['generated_by']) == assessment['generator_sha256'], name)
    checked.append(name)
for runtime in ('minimum', 'current'):
    for kind in ('', 'cancellation-', 'dynamic-binds-', 'refusal-storage-'):
        name = f'behavior-review-recheck-{kind}{runtime}.json'
        receipt = read(name)
        require(receipt['source_sha256']['etl/writer_ownership.py'] == writer, name)
        require(receipt['start_source_sha256'] == receipt['source_sha256'], name)
        require(historical_digest(receipt['generated_by']) == receipt['generator_sha256'], name)
        for (path, expected) in receipt['source_sha256'].items():
            require(historical_digest(path) == expected, (name, path))
        checked.append(name)
red = read('baseline-final-red.json')
require(red['exit_code'] == 1 and '3 failed, 57 deselected' in red['output'], 'integrity condition at original line 75')
require('etl/writer_ownership.py' not in red['source_sha256'], 'integrity condition at original line 76')
base = '9e97ca3f1ca43f103a8655447a86d889456a218a'
for path in ('etl/backfill.py', 'etl/database_loader.py', 'etl/kenya_pipeline.py', 'etl/monitored_runner.py', 'etl/scheduler.py', 'etl/worker.py'):
    actual = historical_bytes(path, 'baseline')
    require(hashlib.sha256(actual).hexdigest() == red['source_sha256'][path], path)
for path in ('backend/tests/test_batch9_legacy_etl_ownership.py', 'backend/tests/batch9_legacy_fixture/sitecustomize.py', 'backend/tests/batch9_legacy_fixture/entry.py'):
    require(red['source_sha256'][path] == read('process-final-current.json')['source_sha256'][path] == historical_digest(path), path)
require(read('baseline-replay-execution.json')['exit_code'] == 0, 'integrity condition at original line 83')
require('owned_candidate_bytes_restored=true' in read('baseline-replay-execution.json')['output'], 'integrity condition at original line 84')
manifest = json.loads((evidence / 'process-logs/manifest.json').read_text())
require(historical_digest(manifest['generated_by']) == manifest['generator_sha256'], 'integrity condition at original line 86')
for record in manifest['records']:
    require(digest(root / record['archive']) == record['archive_sha256'], 'integrity condition at original line 88')
    with tarfile.open(root / record['archive'], 'r:gz') as archive:
        for (member, expected) in record['files'].items():
            require(hashlib.sha256(archive.extractfile(member).read()).hexdigest() == expected, 'integrity condition at original line 91')
current = None
if not args.historical_only:
    current_path = evidence / 'review-verification-manifest.json'
    require(current_path.is_file(), 'fresh source-bound candidate verification manifest required')
    current = read('review-verification-manifest.json')
    require(current.get('scope') == 'PR596 scoped review verification; no hosted or production acceptance', 'candidate scope')
    sources = current.get('source_sha256')
    require(isinstance(sources, dict) and set(sources) == CURRENT_SOURCE_PATHS, 'complete candidate sources required')
    for relative, expected in sources.items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'relative candidate source required')
        require(digest(root / relative) == expected, ('candidate source changed', relative))
    checks = current.get('checks', {})
    require(set(checks) == {'current', 'minimum', 'launcher-current', 'launcher-minimum', 'complete-collection', 'runtime-current', 'runtime-minimum'}, 'complete scoped verification checks required')
    for label, check in checks.items():
        require(set(check['source_paths']) == set(sources), (label, 'complete candidate source binding required'))
        receipt_path = root / check['receipt']
        output_path = root / check['output']
        require(digest(receipt_path) == check['receipt_sha256'], (label, 'receipt bytes'))
        require(digest(output_path) == check['output_sha256'], (label, 'raw output bytes'))
        receipt = json.loads(receipt_path.read_text())
        require(receipt.get('generator_sha256') == sources['batch9-legacy-etl-evidence/review_receipt_generator.py'], (label, 'archived execution generator identity'))
        require(receipt.get('exit_code') == 0 and receipt.get('source_stable') is True and receipt.get('verdict') == 'PASSED', (label, 'successful stable execution required'))
        require(receipt.get('output_sha256') == check['output_sha256'], (label, 'output binding'))
        for relative in check['source_paths']:
            require(relative in sources, (label, 'undeclared source'))
            require(receipt['source_before'][relative] == receipt['source_after'][relative] == sources[relative], (label, relative))
        require(check['expected_output'] in output_path.read_text(), (label, 'expected execution outcome'))
artifacts = {str(path.relative_to(root)): digest(path) for path in sorted(evidence.rglob('*')) if path.is_file() and path.name not in ('delivery-provenance.json', 'historical-delivery-provenance.json', 'review-delivery-provenance.json')}
output = {'generated_by': str(Path(__file__).relative_to(root)), 'generator_sha256': digest(Path(__file__)), 'command': ['python', str(Path(__file__).relative_to(root))], 'base': base, 'verified_author_commit': AUTHOR_COMMIT, 'scope': 'historical author receipts only; current candidate requires new execution', 'historical_archive_sha256': HISTORICAL_ARCHIVE_SHA256, 'historical_implementation_source_sha256': {path: historical_digest(path) for path in read('process-final-current.json')['source_sha256']}, 'checked_receipts': checked, 'unchanged_red_green_measurements': True, 'expected_baseline_failures': 3, 'final_passes_each_runtime': 77, 'artifact_sha256': artifacts, 'verdict': 'PASSED'}
if current is not None:
    output['scope'] = current['scope']
    output['candidate_source_sha256'] = current['source_sha256']
    output['candidate_checks'] = current['checks']
path = evidence / ('historical-delivery-provenance.json' if args.historical_only else 'review-delivery-provenance.json')
path.write_text(json.dumps(output, indent=2) + '\n')
require(json.loads(path.read_text()) == output, 'integrity condition at original line 104')
print(f'PASSED {output["scope"]}: {len(checked)} historical receipts/assessments, {len(artifacts)} artifact hashes')
