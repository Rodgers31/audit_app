"""Independently verify preserved historical failure bytes, without acceptance claims."""
from pathlib import Path
import gzip
import hashlib
import json
import platform
import subprocess
import sys
import time

sys.dont_write_bytecode = True
REPO = Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
ROOT = REPO / 'docs/admin/implementation/batch10-scroll-evidence'
OUT = Path(__file__).resolve().parent
BASE = 'bcb5ff99854de595bbe3f7d60cc8796b7ada5a20'
sha = lambda data: hashlib.sha256(data).hexdigest()
manifest = json.loads((ROOT / 'manifest.json').read_text())
files = {}
for entry in manifest['files']:
    p = ROOT / entry['path']
    assert p.is_file() and not p.is_symlink()
    data = p.read_bytes()
    assert sha(data) == entry['sha256']
    raw = gzip.decompress(data) if entry['compression'] == 'gzip' else data
    assert sha(raw) == entry['input_sha256']
    pinned = subprocess.check_output(['git', 'show', BASE + ':docs/admin/implementation/batch10-scroll-evidence/' + entry['path']], cwd=REPO)
    assert pinned == data
    files[entry['path']] = {'compressed_sha256': sha(data), 'original_sha256': sha(raw)}
expected = {'data/historical-trace.zip.gz': '75522647fc9dbe493b54c8670e79baabf8c67e1a2fc86f17886e9e67963572b4', 'data/node22-precondition-trace.zip.gz': '632bd83708061ba281d908c4b1ad40acb4db5707277ce8f88ca5b150b8cc9585'}
assert all(files[p]['original_sha256'] == digest for p, digest in expected.items())
report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(), 'base': BASE, 'completed': time.time(), 'generator_sha256': sha(Path(__file__).read_bytes()), 'manifest_sha256': sha((ROOT / 'manifest.json').read_bytes()), 'files': files, 'failure_traces': expected, 'runtime': {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform()}, 'scope': 'Historical archive integrity and equality to pinned base only; no new execution or resolution of #601/#607.'}
with (OUT / 'preserved-history.json').open('x') as f:
    json.dump(report, f, indent=2)
assert json.loads((OUT / 'preserved-history.json').read_text()) == report
print(json.dumps({'verified_archive_files': len(files), 'failure_traces': expected, 'scope': report['scope']}))
