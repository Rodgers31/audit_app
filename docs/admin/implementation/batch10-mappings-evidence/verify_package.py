"""Read-only package verification; explicit checks also run under Python -O."""
import hashlib
import gzip
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

REQUIRED_RECEIPTS = {
    'receipts/cohort-current-repaired.json': 519,
    'receipts/cohort-minimum-final.json': 519,
    'receipts/legacy-current-repaired.json': 275,
    'receipts/legacy-minimum-repaired.json': 275,
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def located(root, name):
    require(isinstance(name, str), 'Invalid path')
    path = (root / name).resolve()
    require(path.is_relative_to(root.resolve()), 'Path outside package')
    return path


def verify(root):
    packet = root / 'docs/admin/implementation/batch10-mappings-evidence'
    manifest = json.loads((packet / 'manifest.json').read_text())
    require(type(manifest['schema']) is int and manifest['schema'] == 1, 'Unknown package schema')
    require(bool(manifest['source_sha256']) and bool(manifest['assets_sha256']) and bool(manifest['checks']), 'Empty verification inventory')
    for name, expected in manifest['source_sha256'].items():
        path = located(root, name)
        require(path.is_file() and sha(path) == expected, 'Source mismatch: '+name)
    for name, expected in manifest['assets_sha256'].items():
        path = located(packet, name)
        require(path.is_file() and sha(path) == expected, 'Asset mismatch: '+name)
    require(len(manifest['checks']) == len(REQUIRED_RECEIPTS)
        and {c['receipt'] for c in manifest['checks']} == set(REQUIRED_RECEIPTS)
        == {str(p.relative_to(packet)) for p in (packet / 'receipts').glob('*.json')}, 'Receipt inventory mismatch')
    for check in manifest['checks']:
        receipt = json.loads(located(packet, check['receipt']).read_text())
        require(type(receipt['child_exit']) is int and type(check['expected_exit']) is int
            and receipt['child_exit'] == check['expected_exit'] == 0 and receipt['source_stable'] is True, 'Failed or unstable check: '+check['receipt'])
        require(receipt['source_before'] == receipt['source_after'], 'Source drift')
        require(sha(located(packet, receipt['generator'])) == receipt['generator_sha256'], 'Generator mismatch')
        require(sha(located(packet, receipt['log'])) == receipt['log_sha256'], 'Raw log mismatch')
        raw_log = gzip.decompress(located(packet, receipt['log']).read_bytes())
        require(hashlib.sha256(raw_log).hexdigest() == receipt['raw_log_sha256'], 'Decompressed log mismatch')
        original = json.loads(gzip.decompress(located(packet, receipt['original_receipt']).read_bytes()))
        require(type(original['child_exit']) is int and original['child_exit'] == receipt['child_exit']
            and original['source_stable'] is True and original['source_before'] == original['source_after']
            and original['command'] == receipt['command']
            and original['generator_sha256'] == receipt['generator_sha256']
            and original['log_sha256'] == receipt['raw_log_sha256'], 'Original execution mismatch')
        junit = located(packet, receipt['junit'])
        require(sha(junit) == receipt['junit_sha256'], 'JUnit mismatch')
        suites = list(ET.parse(junit).getroot().iter('testsuite'))
        counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
        cases = [case for suite in suites for case in suite.findall('testcase')]
        require(all(type(value) is int for value in receipt['counts'].values())
            and counts == receipt['counts'] and counts['tests'] == REQUIRED_RECEIPTS[check['receipt']] == len(cases)
            and all(case.find(tag) is None for case in cases for tag in ('failure', 'error', 'skipped'))
            and all(counts[key] == 0 for key in ('failures', 'errors', 'skipped')), 'Empty or failed actual cohort')
        require(bool(receipt['command']) and bool(receipt['source_before']), 'Empty execution identity')
        for name, expected in receipt['source_before'].items():
            require(manifest['source_sha256'].get(name) == original['source_before'].get(name) == expected, 'Executed source mismatch: '+name)
    return {'verdict': 'PASSED', 'checks': len(manifest['checks']), 'source_files': len(manifest['source_sha256'])}


if __name__ == '__main__':
    print(json.dumps(verify(Path(__file__).resolve().parents[4] if len(sys.argv) == 1 else Path(sys.argv[1]))))
