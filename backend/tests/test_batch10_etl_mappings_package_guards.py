"""Actual copied-package shape/coverage/JUnit guards, including optimized Python."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from test_batch10_etl_mappings_receipts import ROOT, PACKET
from batch10_packet_fixture import copy_packet, invoke, snapshot


@pytest.mark.parametrize('optimized', [False, True])
@pytest.mark.parametrize('attack', ['schema_bool', 'duplicate', 'pruned', 'hidden_failure'])
def test_published_package_refuses_false_coverage(tmp_path, optimized, attack):
    copy = tmp_path / 'copy'
    packet, manifest = copy_packet(copy)
    if attack == 'schema_bool':
        manifest['schema'] = True
    elif attack == 'duplicate':
        manifest['checks'].append(dict(manifest['checks'][0]))
    elif attack == 'pruned':
        manifest['checks'] = manifest['checks'][-1:]
        retained = {c['receipt'] for c in manifest['checks']}
        for path in (packet / 'receipts').glob('*.json'):
            name = str(path.relative_to(packet))
            if name not in retained:
                path.unlink()
                manifest['assets_sha256'].pop(name)
    else:
        check = manifest['checks'][0]
        path = packet / check['receipt']
        receipt = json.loads(path.read_text())
        junit = packet / receipt['junit']
        tree = ET.parse(junit)
        case = next(tree.getroot().iter('testcase'))
        ET.SubElement(case, 'failure', {'message': 'inert hostile failure'})
        tree.write(junit, encoding='utf-8', xml_declaration=True)
        receipt['junit_sha256'] = hashlib.sha256(junit.read_bytes()).hexdigest()
        manifest['assets_sha256'][receipt['junit']] = receipt['junit_sha256']
        path.write_text(json.dumps(receipt))
        manifest['assets_sha256'][check['receipt']] = hashlib.sha256(path.read_bytes()).hexdigest()
    (packet / 'manifest.json').write_text(json.dumps(manifest))
    inherited = packet / 'inherited-verdict.json'
    inherited.write_bytes(b'{"historical":true}')
    before = snapshot(copy)
    result = invoke(packet, copy, optimized, retained_source=True)
    assert result.returncode != 0 and 'PASSED' not in result.stdout
    assert snapshot(copy) == before
