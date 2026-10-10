"""Final published package and source/output tampering, normal and optimized."""
import json
from pathlib import Path

import pytest

from batch10_packet_fixture import ROOT, PACKET, copy_packet, invoke, snapshot


@pytest.mark.parametrize('optimized', [False, True])
@pytest.mark.parametrize('mutation', ['none', 'source', 'log', 'generator', 'exit', 'empty'])
def test_published_package_refuses_tampering_without_writing_verdict(tmp_path, optimized, mutation):
    copy = tmp_path / 'candidate'
    packet, manifest = copy_packet(copy)
    check = manifest['checks'][0]
    receipt_path = packet / check['receipt']
    receipt = json.loads(receipt_path.read_text())
    if mutation == 'source':
        (copy / 'retained-source' / next(iter(manifest['source_sha256']))).write_text('tampered')
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
    before = snapshot(copy)
    result = invoke(packet, copy, optimized, retained_source=True)
    if mutation == 'none':
        assert result.returncode == 0 and json.loads(result.stdout)['verdict'] == 'PASSED', result.stderr
        assert json.loads(result.stdout)['current_checkout_acceptance'] is False
    else:
        assert result.returncode != 0 and 'PASSED' not in result.stdout
    assert snapshot(copy) == before
