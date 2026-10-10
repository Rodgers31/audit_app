"""Publish a new immutable local evidence archive; never overwrite a packet."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

BASE = 'f6c31e271297eece52f34102dc40a1e2ed7069a8'
TREE = '69ddfad6deb814dd08fdaee2db2d512d73e14c78'
ROOT = Path(__file__).resolve().parents[4]


def main(output_root, destination):
    output = Path(output_root).resolve()
    dest = Path(destination).resolve()
    manifest_path = dest.with_suffix('.manifest.json')
    if dest.exists() or dest.is_symlink() or manifest_path.exists() or manifest_path.is_symlink():
        raise FileExistsError('packet or manifest already exists')
    files = {}

    def add(name, data):
        if name in files:
            raise ValueError('duplicate packet path: ' + name)
        files[name] = data

    records = {}
    for receipt in sorted((output / 'raw').glob('*.json')):
        record = json.loads(receipt.read_bytes())
        records[receipt.stem] = {k: record[k] for k in ('exit', 'verification_exit', 'source_stable', 'generator_sha256')}
        for suffix in ('.json', '.stdout', '.stderr'):
            path = receipt.with_suffix(suffix)
            add('raw/' + path.name, path.read_bytes())
    evidence = Path(__file__).resolve().parent
    for path in sorted(evidence.glob('*.py')):
        add('generators/' + path.name, path.read_bytes())
    for path in sorted((evidence / 'historical-generators').iterdir()):
        add('generators/historical/' + path.name, path.read_bytes())
    for path in sorted(evidence.glob('*.cjs')) + sorted(evidence.glob('*.mjs')):
        add('generators/' + path.name, path.read_bytes())
    for name in ('START.json', 'model-manifest.json', 'official-upgrade-changed-files.json', 'tailwind4-initial.json', 'tailwind-upgrade-initial.json'):
        add('observations/' + name, (output / name).read_bytes())
    for name in ('baseline.css', 'official.css'):
        add('outputs/' + name, (output / name).read_bytes())
    pairs = {
        'mac-builder.bin': 'builder-fixture/public/data/constitution/embeddings.bin',
        'mac-builder-index.json': 'builder-fixture/public/data/constitution/embeddings-index.json',
        'linux-builder.bin': 'linux/builder-embeddings.bin', 'linux-builder-index.json': 'linux/builder-index.json',
        'mac-jest.json': 'mac-jest-parity.json', 'linux-jest.json': 'linux/jest-results-parity.json',
    }
    for name, path in pairs.items():
        add('outputs/' + name, (output / path).read_bytes())
    for path in sorted((output / 'recorder-red').rglob('*')):
        if path.is_file() and '.git' not in path.parts:
            add('recorder-red/' + path.relative_to(output / 'recorder-red').as_posix(), path.read_bytes())
    source_paths = ['frontend/package.json', 'frontend/package-lock.json', 'frontend/app/globals.css',
        'frontend/postcss.config.js', 'frontend/tailwind.config.js', 'frontend/next.config.js',
        'frontend/scripts/build-embeddings.mjs', 'frontend/scripts/verify-native-dependencies.mjs',
        'frontend/scripts/verify-tooling-inputs.cjs', 'frontend/scripts/verify-runtime-dependencies.cjs',
        'frontend/data/constitution/semantic-search.ts', 'frontend/tests/batch7DependencyBrowser.cjs']
    for path in source_paths:
        data = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)
        if (ROOT / path).read_bytes() != data:
            raise ValueError('canonical application changed: ' + path)
        add('source/' + path, data)
    add('source/embeddings-index.json', (ROOT / 'frontend/public/data/constitution/embeddings-index.json').read_bytes())
    tracked = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE, 'frontend'], cwd=ROOT).decode().splitlines()
    changes = {}
    for candidate in ('tailwind4', 'tailwind-upgrade', 'tailwind-upgrade-fresh-resolution'):
        changed, deleted = [], []
        for path in tracked:
            local = output / 'candidates' / candidate / path
            if not local.is_file():
                deleted.append(path)
                continue
            data = local.read_bytes()
            original = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT)
            if data != original:
                changed.append(path)
                add('candidates/' + candidate + '/' + path, data)
        changes[candidate] = {'changed': changed, 'deleted': deleted}
    add('observations/candidate-deltas.json', (json.dumps(changes, indent=2) + '\n').encode())
    snapshots = Path('/Users/roger/.codex/visualizations/2026/10/03/01a1034a-4799-7f72-a9d1-28c8cfbea53f/BATCH_10_SESSIONS')
    for name in ('SPEC.md', 'ISSUE_494_LAUNCH.json'):
        add('spec/' + name, (snapshots / name).read_bytes())
    with zipfile.ZipFile(dest, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as packet:
        for name, data in sorted(files.items()):
            packet.writestr(name, data)
    manifest = {'schema': 1, 'base': BASE, 'base_tree': TREE,
        'archive_sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
        'files': {n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())},
        'records': records, 'candidate_change_counts': {n: len(v['changed']) + len(v['deleted']) for n, v in changes.items()},
        'scope': 'historical baseline and rejected candidate evidence; no remediation acceptance'}
    with manifest_path.open('x') as handle:
        handle.write(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'archive': str(dest), 'manifest': str(manifest_path), 'records': len(records),
                      'members': len(files), 'candidate_changes': manifest['candidate_change_counts']}))


if __name__ == '__main__':
    main(*sys.argv[1:])
