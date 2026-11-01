from pathlib import Path
import base64
import concurrent.futures
import datetime
import hashlib
import io
import json
import subprocess
import tarfile
import urllib.request

base = Path(__file__).parent
front = Path('/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend')
node = '/Users/roger/.codex/visualizations/2026/10/31/01a193b2-b534-7a01-8250-1edf848b9ba5/dependencies/runtime/node-v24.22.1-darwin-arm64/bin/node'
script = "const p=require('node:path'),{createRequire}=require('node:module');const front=process.argv[1];console.log(JSON.stringify([['eslint','minimatch'],['flat-cache','rimraf'],['rimraf','glob']].map(([caller,name])=>{const r=createRequire(p.join(front,'node_modules',caller,'package.json')),metadata=r.resolve(name+'/package.json');return {caller,name,metadata,executable:r.resolve(name)}})));"
bindings = json.loads(subprocess.check_output([node, '-e', script, str(front)]))
lock = json.loads((front / 'package-lock.json').read_text())
helper = (front / 'scripts/apply-tooling-repairs.cjs').read_text()

def check(binding):
    package = Path(binding['metadata']).parent
    entry = str(Path(binding['executable']).relative_to(package))
    location = str(package.relative_to(front))
    record = lock['packages'][location]
    with urllib.request.urlopen(record['resolved'], timeout=30) as response:
        archive = response.read()
    assert 'sha512-' + base64.b64encode(hashlib.sha512(archive).digest()).decode() == record['integrity']
    (base / 'original-tars').mkdir(exist_ok=True)
    (base / 'original-tars' / (binding['name'] + '-' + record['version'] + '.tgz')).write_bytes(archive)
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        original = tar.extractfile('package/' + entry).read()
    actual = Path(binding['executable']).read_bytes()
    assert original == actual
    digest = hashlib.sha256(original).hexdigest()
    return {'caller': binding['caller'], 'name': binding['name'], 'version': record['version'], 'locked_location': location, 'url': record['resolved'], 'integrity': record['integrity'], 'archive_sha256': hashlib.sha256(archive).hexdigest(), 'actual_commonjs_export': entry, 'entry_sha256': digest, 'installed_entry_matches_official_tar': True, 'helper_contains_actual_entry_hash': digest in helper}

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(check, bindings))
output = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'helper_sha256': hashlib.sha256(helper.encode()).hexdigest(), 'bindings': results}
file = base / ('matcher-entry-verification-' + output['helper_sha256'][:12] + '.json')
file.write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps(output, indent=2))
