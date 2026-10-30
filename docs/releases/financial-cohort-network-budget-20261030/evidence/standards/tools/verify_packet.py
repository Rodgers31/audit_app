"""Verify the portable archive, not a fresh acceptance run. Stdlib only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import stat
import sys
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(root, name):
    if type(name) is not str or not name or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Unsafe packet path: ' + repr(name))
    value = root
    for part in Path(name).parts:
        value = value / part
        if value.is_symlink():
            raise ValueError('Symlink refused: ' + name)
    if not value.is_file() or not stat.S_ISREG(value.stat().st_mode):
        raise ValueError('Missing/nonregular packet artifact: ' + name)
    return value


def load(path):
    return json.loads(path.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def verify(root):
    root = root.resolve()
    index = load(safe_file(root, 'index.json'))
    if index['schema_version'] != 1 or type(index['schema_version']) is not int or index['tests_rerun'] is not False:
        raise ValueError('Unknown packet contract')
    expected = index['packet_files']
    if type(expected) is not dict or not expected:
        raise ValueError('Empty packet inventory')
    actual = set()
    directories = set()
    for path in root.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('Nonregular inventory member: ' + str(path))
        if path.is_dir():
            directories.add(path.relative_to(root).as_posix())
        if path.is_file() and path != root / 'index.json':
            actual.add(path.relative_to(root).as_posix())
    if directories != set(index['packet_directories']):
        raise ValueError('Physical directory inventory differs')
    if actual != set(expected):
        raise ValueError('Physical inventory differs: ' + repr(sorted(actual ^ set(expected))))
    for name, entry in expected.items():
        path = safe_file(root, name)
        if type(entry['bytes']) is not int or path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
            raise ValueError('Artifact differs: ' + name)
    for key in ('generated_by', 'verifier'):
        if sha(safe_file(root, index[key]['path'])) != index[key]['sha256']:
            raise ValueError('Tool provenance differs: ' + key)
    declarations = index['declarations']
    if len({d['declared_by'] for d in declarations}) != len(declarations):
        raise ValueError('Duplicate declaration')
    mapped = {d['declared_by']: d for d in declarations}
    receipt = load(safe_file(root, 'original/FINAL7-RECEIPT.json'))
    if sha(safe_file(root, index['original_receipt']['path'])) != index['original_receipt']['sha256']:
        raise ValueError('Original receipt differs')
    for field, prefix in [('artifacts_sha256', 'FINAL7.artifacts.'), ('imported_independent_fixtures_sha256', 'FINAL7.fixtures.')]:
        for name, digest in receipt[field].items():
            entry = mapped[prefix + name]
            if entry['sha256'] != digest or sha(safe_file(root, entry['path'])) != digest:
                raise ValueError('Unresolved original declaration: ' + name)
    prior = load(safe_file(root, 'original/RECEIPT.json'))
    for name, digest in prior['artifacts_sha256'].items():
        entry = mapped['diagnostic.artifacts.' + name]
        if entry['sha256'] != digest or sha(safe_file(root, entry['path'])) != digest:
            raise ValueError('Unresolved diagnostic declaration: ' + name)
    fixture = mapped['diagnostic.fixture.test_cohort_guard.py']
    if sha(safe_file(root, fixture['path'])) != prior['imported_fixture_sha256']:
        raise ValueError('Diagnostic fixture differs')
    reference = index['reference_only']
    if (len(reference) != 1 or reference[0]['sha256'] != prior['parent_production_read_only_receipt_sha256']
            or reference[0]['disposition'] != 'reference_only_not_bundled_not_a_FINAL7_test_input'):
        raise ValueError('Historical reference classification differs')
    manifest_path = safe_file(root, 'source/original-manifest.json')
    manifest = load(manifest_path)
    canonical = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if len(manifest) != 5814 or canonical != receipt['manifest_mapping_sha256'] or sha(manifest_path) != receipt['manifest_file_sha256']:
        raise ValueError('Original source manifest differs')
    bridge = load(safe_file(root, 'source/source-bridge.json'))
    if bridge['commit'] != 'd0da4996327213049614cd8f09b373bcaa856a23' or bridge['source_file_count'] != len(bridge['source_files']):
        raise ValueError('Unknown source bridge')
    source_names = {n for n in manifest if n.startswith('backend/') or n == '.github/workflows/seed.yml'}
    if set(bridge['source_files']) != source_names or any(v['sha256'] != manifest[n] for n, v in bridge['source_files'].items()):
        raise ValueError('Incomplete source bridge')
    ledger = load(safe_file(root, 'original/FINAL7-case-ledger.json'))
    cases = ledger['cases']
    if type(receipt['cases']) is not int or receipt['cases'] != 74 or len(cases) != 74:
        raise ValueError('Wrong acceptance count')
    actual_cases = Counter()
    for xml_name, digest in ledger['junit_sha256'].items():
        path = safe_file(root, mapped['FINAL7.artifacts.' + xml_name]['path'])
        if sha(path) != digest:
            raise ValueError('JUnit pin differs')
        for case in ET.parse(path).getroot().iter('testcase'):
            if any(case.find(x) is not None for x in ('failure', 'error', 'skipped')):
                raise ValueError('Nonpass acceptance case')
            actual_cases[(xml_name, case.attrib['classname'] + '::' + case.attrib['name'])] += 1
    declared_cases = Counter((c['junit'], c['id']) for c in cases if c['outcome'] == 'passed')
    if actual_cases != declared_cases or len(actual_cases) != 74 or any(v != 1 for v in actual_cases.values()):
        raise ValueError('Incomplete/duplicate acceptance testcase mapping')
    commands = load(safe_file(root, 'original/FINAL7-commands.json'))
    if len(commands['runs']) != 4 or any(type(r['child_exit_code']) is not int or r['child_exit_code'] != 0 for r in commands['runs']):
        raise ValueError('Original child outcomes differ')
    return dict(status='verified_archive', tests_rerun=False, acceptance_cases=74,
                packet_files=len(expected), declarations=len(declarations),
                source_commit=bridge['commit'], source_bridge_files=len(source_names),
                historical_context_hash_not_bundled=index['reference_only'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.packet), indent=2))
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError) as error:
        print(json.dumps(dict(status='refused', tests_rerun=False, reason=str(error))))
        sys.exit(1)
