"""Independent publisher guard executions in owned disposable destinations."""
import gzip, hashlib, importlib.util, json, pathlib, shutil, subprocess, sys, tempfile

REPO = pathlib.Path('/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app')
ROOT = REPO / 'docs/admin/implementation/batch10-scroll-evidence'
OUT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / 'create_package.py'
HASH = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
WORK = pathlib.Path(tempfile.mkdtemp(prefix='batch10-scroll-publisher-attack-'))
RECORDS = []
FAILURE = 'smart-back-Smart-back-link-bed2a--preserved-after-smart-back-chromium-repeat79'

def fixture(name):
    attempt = WORK / name
    destination = attempt / 'publication'
    artifacts = attempt / 'artifacts'
    destination.mkdir(parents=True)
    artifacts.mkdir()
    shutil.copyfile(SOURCE, destination / 'create_package.py')
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    for entry in manifest['files']:
        name = pathlib.Path(entry['path']).name.removesuffix('.gz')
        raw = gzip.decompress((ROOT / entry['path']).read_bytes())
        target = artifacts / name
        if name.endswith('-full-report.json'):
            target = artifacts / 'full-original' / name.removesuffix('-full-report.json') / 'results.json'
        elif name.endswith('-full-receipt.json'):
            target = artifacts / 'full-original' / (name.removesuffix('-full-receipt.json') + '-receipt.json')
        elif name.endswith('-full.log'):
            target = artifacts / 'full-original' / (name.removesuffix('-full.log') + '.log')
        elif name.endswith('-report.json'):
            target = artifacts / (name.removesuffix('-report.json') + '-results.json')
        elif name.endswith('-receipt.json'):
            target = artifacts / (name.removesuffix('-receipt.json') + '.json')
        elif name in ('inventory.json', 'full-summary.json'):
            target = artifacts / 'full-original' / ('inventory.json' if name == 'inventory.json' else 'summary.json')
        elif name.startswith('node22-precondition-'):
            target = artifacts / 'original-node22-linux-100-output' / FAILURE / name.removeprefix('node22-precondition-')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    launch = json.loads((artifacts / 'launch.json').read_text())
    launch['historical_trace']['path'] = str(artifacts / 'historical-trace.zip')
    (artifacts / 'launch.json').write_text(json.dumps(launch))
    return destination, artifacts

def attack(name, mutate=None, hook=None, expected='reject'):
    destination, artifacts = fixture(name)
    if mutate:
        mutate(destination, artifacts)
    script = destination / 'create_package.py'
    record = dict(name=name, expected=expected, exact_call='publish(owned_artifacts)' if hook else [sys.executable, str(script), str(artifacts)])
    if hook:
        spec = importlib.util.spec_from_file_location('independent_publisher_' + name, script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        real = module.gzip.compress
        triggered = False
        def wrapped(*args, **kwargs):
            nonlocal triggered
            if not triggered:
                triggered = True
                hook(destination, artifacts)
            return real(*args, **kwargs)
        module.gzip.compress = wrapped
        try:
            module.publish(artifacts)
            record.update(exit=0, actual='published', diagnostic='publish returned')
        except Exception as error:
            record.update(exit=1, actual='rejected', diagnostic=str(error))
        finally:
            module.gzip.compress = real
    else:
        result = subprocess.run([sys.executable, str(script), str(artifacts)], capture_output=True, text=True, timeout=30)
        record.update(exit=result.returncode, actual='published' if result.returncode == 0 else 'rejected', stdout=result.stdout, stderr=result.stderr)
    record['data_exists'] = (destination / 'data').exists()
    record['manifest_exists'] = (destination / 'manifest.json').exists()
    if name == 'valid-publisher':
        shutil.copytree(destination, OUT / 'publisher-valid-readback')
    RECORDS.append(record)
    print(json.dumps(record))

attack('valid-publisher', expected='publish')
attack('absent-required-report', lambda d,a: (a / 'original-linux-20-results.json').unlink())
attack('existing-data', lambda d,a: (d / 'data').mkdir())
attack('existing-manifest', lambda d,a: (d / 'manifest.json').write_text('{}'))
attack('input-changes-during-publish', hook=lambda d,a: (a / 'probe-hooks.ts').write_text('changed during compression'))
attack('producer-changes-during-publish', hook=lambda d,a: (d / 'create_package.py').write_text((d / 'create_package.py').read_text() + '\n# changed during compression\n'))
result = dict(python=sys.version, source_path=str(SOURCE), source_before=HASH,
              source_after=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              harness_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(), records=RECORDS)
with (OUT / 'publisher-attack-results.json').open('x') as stream:
    json.dump(result, stream, indent=2)
shutil.rmtree(WORK)
