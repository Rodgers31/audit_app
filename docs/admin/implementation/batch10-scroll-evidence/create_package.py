"""Publish an exclusive, lossless archive of this author's completed attempts."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def publish(artifacts):
    artifacts = Path(artifacts).resolve()
    launch = json.loads((artifacts / 'launch.json').read_text())
    targets = [
        ('original-linux-20', 20, 'positive-diagnostic', 'run_record.py'),
        ('probe-linux-cpu1', 6, 'positive-diagnostic', 'run_record_v2.py'),
        ('probe-linux-cpu8', 10, 'positive-diagnostic', 'run_record_v2.py'),
        ('probe-native-absent-negative', 1, 'negative-detector', 'run_record_v2.py'),
        ('probe-chunk-delay1000', 10, 'positive-diagnostic', 'run_record_v2.py'),
        ('original-node22-linux-100', 100, 'observed-precondition-failure', 'run_record_v3.py'),
    ]
    inputs = {}
    target_records = []
    for name, count, role, generator in targets:
        inputs[name + '-report.json'] = artifacts / (name + '-results.json')
        inputs[name + '-receipt.json'] = artifacts / (name + '.json')
        inputs[name + '.log'] = artifacts / (name + '.log')
        inputs[generator] = artifacts / generator
        target_records.append(dict(name=name, count=count, role=role,
            report='data/' + name + '-report.json.gz',
            receipt='data/' + name + '-receipt.json.gz', generator='data/' + generator + '.gz'))
    cohorts = []
    for name in ('public', 'users', 'operations', 'overview-audit', 'etl-ui', 'coordinator'):
        inputs[name + '-full-report.json'] = artifacts / 'full-original' / name / 'results.json'
        inputs[name + '-full-receipt.json'] = artifacts / 'full-original' / (name + '-receipt.json')
        inputs[name + '-full.log'] = artifacts / 'full-original' / (name + '.log')
        cohorts.append(dict(name=name, report='data/' + name + '-full-report.json.gz',
                            receipt='data/' + name + '-full-receipt.json.gz'))
    for name in ('launch.json', 'resolved-runtime.json', 'node22-runtime.json', 'historical-run-readback.json',
                 'historical-browser-job.log', 'python-runtime.txt', 'probe-hooks.ts', 'probe-hooks-v1.ts',
                 'probe.spec.ts', 'probe.config.ts', 'run_full.py', 'full-original-chromium.json',
                 'full-original-chromium.log', 'original-inventory.json', 'original-inventory.log'):
        inputs[name] = artifacts / name
    inputs['inventory.json'] = artifacts / 'full-original/inventory.json'
    inputs['full-summary.json'] = artifacts / 'full-original/summary.json'
    inputs['historical-trace.zip'] = Path(launch['historical_trace']['path'])
    failure = artifacts / 'original-node22-linux-100-output' / 'smart-back-Smart-back-link-bed2a--preserved-after-smart-back-chromium-repeat79'
    for name in ('trace.zip', 'test-failed-1.png', 'error-context.md', 'video.webm'):
        inputs['node22-precondition-' + name] = failure / name
    inputs['publisher.py'] = Path(__file__)
    # Read every required input before touching the output destination. A live
    # incomplete attempt or missing prerequisite must not produce a package.
    originals = {name: path.read_bytes() for name, path in inputs.items()}
    producer_hash = digest(Path(__file__).read_bytes())
    output = ROOT / 'data'
    if output.exists() or (ROOT / 'manifest.json').exists():
        raise RuntimeError('Refusing inherited publication outputs')
    output.mkdir()
    files = []
    for name, raw in originals.items():
        encoded = gzip.compress(raw, mtime=0)
        destination = output / (name + '.gz')
        with destination.open('xb') as stream:
            stream.write(encoded)
        if gzip.decompress(destination.read_bytes()) != raw:
            raise RuntimeError('Archive readback mismatch: ' + name)
        files.append(dict(path='data/' + destination.name, compression='gzip',
                          sha256=digest(encoded), input_sha256=digest(raw)))
    if producer_hash != digest(Path(__file__).read_bytes()):
        raise RuntimeError('Publisher changed during archive creation')
    for name, path in inputs.items():
        if path.read_bytes() != originals[name]:
            raise RuntimeError('Input changed during publication: ' + name)
    source_receipt = json.loads(originals['full-original-chromium.json'])
    sources = {path: sha for path, sha in source_receipt['source_hashes'].items()
               if path.startswith(('frontend/app/', 'frontend/components/', 'frontend/lib/', 'frontend/e2e/'))
               or path in launch['source_hashes']
               or path in ('frontend/scripts/ci-browser-cohorts.mjs', 'frontend/scripts/legacy-e2e-env.mjs',
                           'frontend/playwright.ci-cohorts.config.ts', 'backend/tests/legacy_browser_fixture_api.py')}
    manifest = dict(schema=1, issue=601, status='unresolved', scope='historical local diagnostics; no causal fix or hosted acceptance',
                    generated_by='data/publisher.py.gz', generator_sha256=producer_hash,
                    target_commit=launch['base'], target_tree=launch['tree'], sources=sources, files=files,
                    targets=target_records, cohorts=cohorts, inventory='data/inventory.json.gz',
                    historical_run='data/historical-run-readback.json.gz', historical_trace='data/historical-trace.zip.gz')
    with (ROOT / 'manifest.json').open('x') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')
    if json.loads((ROOT / 'manifest.json').read_text()) != manifest:
        raise RuntimeError('Manifest readback mismatch')
    print(json.dumps({'files': len(files), 'sources': len(sources), 'status': 'unresolved'}))

if __name__ == '__main__':
    publish(sys.argv[1])
