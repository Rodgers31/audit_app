"""Final published package and source/output tampering, normal and optimized."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKET = Path('docs/admin/implementation/batch10-mappings-evidence')


@pytest.mark.parametrize('optimized', [False, True])
@pytest.mark.parametrize('mutation', ['none', 'source', 'log', 'generator', 'exit', 'empty'])
def test_published_package_refuses_tampering_without_writing_verdict(tmp_path, optimized, mutation):
    manifest = json.loads((ROOT / PACKET / 'manifest.json').read_text())
    copy = tmp_path / 'candidate'
    shutil.copytree(ROOT / PACKET, copy / PACKET)
    for name in manifest['source_sha256']:
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    packet = copy / PACKET
    check = manifest['checks'][0]
    receipt_path = packet / check['receipt']
    receipt = json.loads(receipt_path.read_text())
    if mutation == 'source':
        (copy / next(iter(manifest['source_sha256']))).write_text('tampered')
    elif mutation in ('log', 'generator'):
        (packet / receipt[mutation]).write_text('tampered')
    elif mutation == 'exit':
        receipt['child_exit'] = 999
        receipt_path.write_text(json.dumps(receipt))
    elif mutation == 'empty':
        manifest['checks'] = []
        (packet / 'manifest.json').write_text(json.dumps(manifest))
    inherited = packet / 'inherited-verdict.json'
    inherited.write_bytes(b'{"historical":true}')
    before = {str(p.relative_to(copy)): p.read_bytes() for p in copy.rglob('*') if p.is_file()}
    result = subprocess.run([sys.executable, *(['-O'] if optimized else []), str(packet / 'verify_package.py'), str(copy)],
        capture_output=True, text=True, timeout=15)
    if mutation == 'none':
        assert result.returncode == 0 and json.loads(result.stdout)['verdict'] == 'PASSED', result.stderr
    else:
        assert result.returncode != 0 and 'PASSED' not in result.stdout
    assert before == {str(p.relative_to(copy)): p.read_bytes() for p in copy.rglob('*') if p.is_file()}
