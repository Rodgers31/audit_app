from pathlib import Path
import base64
import concurrent.futures
import datetime
import hashlib
import io
import json
import tarfile
import urllib.request

base = Path(__file__).parent
front = Path('/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend')
manifest_bytes = (front / 'scripts/tooling-repairs.json').read_bytes()
lock_bytes = (front / 'package-lock.json').read_bytes()
manifest = json.loads(manifest_bytes)
lock = json.loads(lock_bytes)
new_names = {'@eslint/eslintrc', 'eslint-plugin-import', 'eslint-plugin-react', 'eslint-plugin-jsx-a11y'}
groups = {}
for inventory in manifest['packages']:
    if inventory['name'] not in new_names:
        continue
    for entry in inventory['entries']:
        roots = [entry] + [name for name in lock['packages'] if name.startswith(entry + '/node_modules/')]
        for file, identity in inventory['files'].items():
            full = entry + '/' + file
            package = max((name for name in roots if full.startswith(name + '/')), key=len)
            groups.setdefault(package, {})[full.removeprefix(package + '/')] = identity['original_sha256']

def check(item):
    entry, expected = item
    record = lock['packages'][entry]
    url = record['resolved']
    assert url.startswith('https://registry.npmjs.org/'), url
    with urllib.request.urlopen(url, timeout=30) as response:
        archive = response.read()
    algorithm, checksum = record['integrity'].split('-', 1)
    assert algorithm in {'sha512', 'sha1'}
    assert base64.b64encode(hashlib.new(algorithm, archive).digest()).decode() == checksum
    filename = entry.removeprefix('node_modules/').replace('/', '__') + '.tgz'
    (base / 'original-tars').mkdir(exist_ok=True)
    (base / 'original-tars' / filename).write_bytes(archive)
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        actual = {}
        for member in tar.getmembers():
            assert member.name.startswith('package/'), member.name
            if member.isdir():
                continue
            assert member.isfile(), member.name
            actual[member.name.removeprefix('package/')] = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
    assert actual == expected, {'entry': entry, 'extra': sorted(actual.keys() - expected.keys()), 'missing': sorted(expected.keys() - actual.keys()), 'different': [file for file in actual.keys() & expected.keys() if actual[file] != expected[file]]}
    return {'entry': entry, 'version': record['version'], 'url': url, 'integrity': record['integrity'], 'archive_sha256': hashlib.sha256(archive).hexdigest(), 'files': len(actual), 'all_original_hashes_and_file_paths_match': True}

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    results = list(pool.map(check, sorted(groups.items())))
assert (front / 'scripts/tooling-repairs.json').read_bytes() == manifest_bytes
assert (front / 'package-lock.json').read_bytes() == lock_bytes
output = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'lock_sha256': hashlib.sha256(lock_bytes).hexdigest(), 'results': results, 'original_files_verified': sum(r['files'] for r in results)}
(base / 'original-inventory-verification.json').write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps(output, indent=2))
