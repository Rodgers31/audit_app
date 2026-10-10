"""Read-only integrity of retained historical execution, also under -O.

This packet never certifies the current checkout; fresh acceptance is separate.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import xml.etree.ElementTree as ET
import zipfile

PACKET = Path('docs/admin/implementation/batch10-mappings-evidence')
FROZEN = '86aa4c3a7a29383ed256273bd0097cfc81b3336d'
TREE = '051cd539ef2219e9659dd339c720b3ba9e2596c7'
PREVIOUS_MANIFEST = 'history/coordinator-610/previous-manifest.json'
PREVIOUS_SHA256 = '2c946719ccedeca661165acfcd6b34b433532002f20b62d2518c270d59177ff4'
PUBLISHER = 'publish_coordinator_610_v2.py'
RECORDER = 'generators/record_v2.py'
REQUIRED_RECEIPTS = {
    'receipts/cohort-current-repaired.json': 519,
    'receipts/cohort-minimum-final.json': 519,
    'receipts/legacy-current-repaired.json': 275,
    'receipts/legacy-minimum-repaired.json': 275,
}
PUBLICATION_ONLY = {
    'backend/tests/test_batch10_etl_mappings_package_guards.py',
    str(PACKET / 'verify_package.py'),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(body):
    return hashlib.sha256(body).hexdigest()


def sha(path):
    return digest(path.read_bytes())


def relative_name(name):
    require(type(name) is str and bool(name) and '\\' not in name and '\x00' not in name,
            'Invalid path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.as_posix() == name
            and all(part not in ('', '.', '..') for part in path.parts), 'Unsafe path: ' + name)
    return path


def located(root, name):
    path = root.resolve()
    for part in relative_name(name).parts:
        path = path / part
        require(not path.is_symlink(), 'Symlink path: ' + name)
    require(path.resolve().is_relative_to(root.resolve()), 'Path outside package: ' + name)
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def load(body):
    def invalid_constant(value):
        raise ValueError('Nonfinite JSON number: ' + value)
    return json.loads(body, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def hashes(value, label):
    require(type(value) is dict and bool(value), 'Empty or invalid ' + label)
    for name, expected in value.items():
        relative_name(name)
        require(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected) is not None,
                'Invalid hash: ' + label + '/' + name)


def text(value):
    return type(value) is str and bool(value.strip())


def timestamp(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def metadata(record, label):
    require(type(record) is dict, 'Invalid execution record: ' + label)
    for field in ('generated_by', 'generator_sha256', 'cwd', 'runtime', 'source_head', 'source_tree'):
        require(text(record.get(field)), 'Missing execution metadata: ' + label + '/' + field)
    require(Path(record['cwd']).is_absolute(), 'Invalid cwd: ' + label)
    require(re.fullmatch('[0-9a-f]{40}', record['source_head']) is not None
            and re.fullmatch('[0-9a-f]{40}', record['source_tree']) is not None,
            'Invalid source identity: ' + label)
    require(type(record.get('command')) is list and bool(record['command'])
            and all(text(part) for part in record['command']), 'Invalid command: ' + label)
    require(type(record.get('environment')) is dict and bool(record['environment'])
            and all(text(key) and type(value) is str for key, value in record['environment'].items()),
            'Missing execution environment: ' + label)
    require(timestamp(record.get('started_at')) and timestamp(record.get('ended_at'))
            and record['ended_at'] >= record['started_at'], 'Invalid execution timestamps: ' + label)
    require(type(record.get('child_exit')) is int and record['child_exit'] == 0
            and type(record.get('verification_exit')) is int and record['verification_exit'] == 0
            and record.get('source_stable') is True, 'Failed or unstable execution: ' + label)
    hashes(record.get('source_before'), 'source_before/' + label)
    hashes(record.get('source_after'), 'source_after/' + label)
    require(record['source_before'] == record['source_after'], 'Source drift: ' + label)


def retained_sources(packet, manifest, old, source_root):
    require(manifest['source_sha256'] == old['source_sha256'] and len(manifest['source_sha256']) == 1160,
            'Historical source inventory mismatch')
    retained = manifest.get('retained_source')
    require(type(retained) is dict and retained.get('archive') == 'retained-source-86aa4c3.zip'
            and retained.get('commit') == FROZEN and retained.get('tree') == TREE
            and type(retained.get('source_files')) is int and retained['source_files'] == 1160
            and type(retained.get('executed_source_files')) is int and retained['executed_source_files'] == 1158
            and type(retained.get('publication_only_sources')) is list
            and len(retained['publication_only_sources']) == 2
            and set(retained['publication_only_sources']) == PUBLICATION_ONLY,
            'Invalid retained source identity')
    archive_path = located(packet, retained['archive'])
    require(sha(archive_path) == retained.get('sha256'), 'Retained source archive hash mismatch')
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        for member in members:
            relative_name(member.filename)
            require(not member.is_dir() and member.create_system == 3
                    and stat.S_ISREG(member.external_attr >> 16), 'Nonregular archive member: ' + member.filename)
            require(not member.flag_bits & 1 and member.file_size <= 50_000_000,
                    'Invalid archive member: ' + member.filename)
        require(len(names) == len(set(names)), 'Duplicate archive member')
        require(len(names) == 1160 and set(names) == set(manifest['source_sha256']),
                'Retained archive census mismatch')
        require(sum(member.file_size for member in members) <= 100_000_000, 'Oversized source archive')
        for member in members:
            require(digest(archive.read(member)) == manifest['source_sha256'][member.filename],
                    'Retained source mismatch: ' + member.filename)
    if source_root is not None:
        # Explicit extracted historical fixture; never implicitly use ROOT.
        require(source_root.is_dir() and not source_root.is_symlink(), 'Invalid retained source fixture root')
        actual = set()
        for path in source_root.rglob('*'):
            require(not path.is_symlink(), 'Symlink retained source fixture')
            if path.is_file():
                actual.add(str(path.relative_to(source_root)))
        require(actual == set(manifest['source_sha256']), 'Extracted source census mismatch')
        for name, expected in manifest['source_sha256'].items():
            require(sha(located(source_root, name)) == expected, 'Extracted source mismatch: ' + name)


def junit_counts(path, receipt, expected):
    root = ET.parse(path).getroot()
    suites = list(root.iter('testsuite'))
    require(bool(suites), 'Empty JUnit suite')
    keys = ('tests', 'failures', 'errors', 'skipped')
    for suite in suites:
        require(all(re.fullmatch('[0-9]+', suite.attrib.get(key, '')) is not None for key in keys),
                'Invalid JUnit counts')
    counts = {key: sum(int(suite.attrib[key]) for suite in suites) for key in keys}
    cases = list(root.iter('testcase'))
    identities = [(case.attrib.get('classname'), case.attrib.get('name')) for case in cases]
    require(all(text(cls) and text(name) and cls == cls.strip() and name == name.strip()
                for cls, name in identities), 'Blank JUnit testcase identity')
    require(len(identities) == len(set(identities)), 'Duplicate JUnit testcase identity')
    require(type(receipt.get('counts')) is dict and set(receipt['counts']) == set(keys)
            and all(type(value) is int for value in receipt['counts'].values()), 'Invalid portable JUnit counts')
    require(counts == receipt['counts'] and counts['tests'] == expected == len(cases)
            and all(case.find(tag) is None for case in cases for tag in ('failure', 'error', 'skipped'))
            and all(counts[key] == 0 for key in ('failures', 'errors', 'skipped')), 'Empty or failed actual cohort')


def verify(root, source_root=None):
    packet = located(root, str(PACKET))
    manifest = load((packet / 'manifest.json').read_bytes())
    require(type(manifest) is dict and type(manifest.get('schema')) is int and manifest['schema'] == 2,
            'Unknown package schema')
    require(manifest.get('classification') == 'HISTORICAL_EXECUTION_PACKET'
            and manifest.get('current_checkout_acceptance') is False, 'Invalid packet acceptance classification')
    require(manifest.get('generated_by') == PUBLISHER
            and manifest.get('generator_sha256') == sha(located(packet, PUBLISHER))
            and timestamp(manifest.get('generated_at')), 'Publication generator mismatch')
    require(manifest.get('original_publication') == PREVIOUS_MANIFEST
            and manifest.get('previous_publication_sha256') == PREVIOUS_SHA256
            and sha(located(packet, PREVIOUS_MANIFEST)) == PREVIOUS_SHA256, 'Historical publication mismatch')
    old = load(located(packet, PREVIOUS_MANIFEST).read_bytes())
    hashes(manifest.get('source_sha256'), 'historical source inventory')
    hashes(manifest.get('assets_sha256'), 'asset inventory')
    retained_sources(packet, manifest, old, source_root)
    checks = manifest.get('checks')
    require(type(checks) is list and len(checks) == len(REQUIRED_RECEIPTS)
            and all(type(check) is dict and set(check) == {'receipt', 'expected_exit'} for check in checks)
            and {check['receipt'] for check in checks} == set(REQUIRED_RECEIPTS)
            == {str(path.relative_to(packet)) for path in (packet / 'receipts').glob('*.json')}, 'Receipt inventory mismatch')
    for check in checks:
        name = check['receipt']
        stem = Path(name).stem
        receipt = load(located(packet, name).read_bytes())
        metadata(receipt, name)
        require(type(check['expected_exit']) is int and check['expected_exit'] == receipt['child_exit'] == 0,
                'Invalid expected exit: ' + name)
        require(receipt.get('original_receipt') == 'history/' + stem + '.json.gz', 'Original receipt path mismatch')
        original = load(gzip.decompress(located(packet, receipt['original_receipt']).read_bytes()))
        metadata(original, receipt['original_receipt'])
        require(receipt.get('generator') == receipt['generated_by'] == RECORDER
                and Path(original['generated_by']).name == Path(RECORDER).name
                and receipt['generator_sha256'] == original['generator_sha256'] == sha(located(packet, RECORDER)),
                'Recorder identity mismatch')
        require(receipt.get('publication_generator') == 'build_package.py'
                and receipt.get('publication_generator_sha256') == sha(located(packet, 'build_package.py')),
                'Portable publication generator mismatch')
        for field in ('command', 'cwd', 'runtime', 'environment', 'started_at', 'ended_at',
                      'source_head', 'source_tree', 'child_exit', 'verification_exit', 'source_stable'):
            require(receipt[field] == original[field], 'Original execution metadata mismatch: ' + field)
        measured = set(manifest['source_sha256']) - PUBLICATION_ONLY
        require(set(receipt['source_before']) == measured and len(measured) == 1158,
                'Executed source census mismatch')
        for source, expected in receipt['source_before'].items():
            require(manifest['source_sha256'][source] == original['source_before'].get(source) == expected,
                    'Executed source mismatch: ' + source)
        require(receipt.get('log') == 'runs/' + stem + '.log.gz'
                and receipt.get('log_sha256') == sha(located(packet, receipt['log'])), 'Raw log mismatch')
        raw_log = gzip.decompress(located(packet, receipt['log']).read_bytes())
        require(digest(raw_log) == receipt.get('raw_log_sha256') == original['log_sha256'], 'Decompressed log mismatch')
        require(receipt.get('junit') == 'runs/' + stem + '-junit.xml'
                and receipt.get('junit_sha256') == sha(located(packet, receipt['junit'])), 'JUnit hash mismatch')
        junit_counts(located(packet, receipt['junit']), receipt, REQUIRED_RECEIPTS[name])
    replacements = {'README.md': 'history/coordinator-610/previous-README.md',
                    'verify_package.py': 'history/coordinator-610/previous-verify_package.py'}
    require(manifest.get('historical_asset_replacements') == replacements, 'Historical replacement index mismatch')
    for name, expected in old['assets_sha256'].items():
        require(sha(located(packet, replacements.get(name, name))) == expected, 'Historical asset changed: ' + name)
    # The caller's inherited verdict is never consumed, created or replaced.
    actual_assets = set()
    for path in packet.rglob('*'):
        require(not path.is_symlink(), 'Symlink package asset')
        if path.is_file() and path not in (packet / 'manifest.json', packet / 'inherited-verdict.json'):
            actual_assets.add(str(path.relative_to(packet)))
    require(actual_assets == set(manifest['assets_sha256']), 'Asset census mismatch')
    for name, expected in manifest['assets_sha256'].items():
        require(sha(located(packet, name)) == expected, 'Asset mismatch: ' + name)
    require(manifest.get('publication_history') == 'history/coordinator-610/publication-v2.json',
            'Publication history path mismatch')
    publication = load(located(packet, manifest['publication_history']).read_bytes())
    require(publication.get('generated_by') == PUBLISHER
            and publication.get('generator_sha256') == manifest['generator_sha256']
            and publication.get('previous_manifest_sha256') == PREVIOUS_SHA256
            and publication.get('original_execution_status') == 'HISTORICAL_EXECUTION_PACKET'
            and publication.get('current_checkout_acceptance') is False, 'Publication history mismatch')
    require(manifest.get('intermediate_publication') == 'history/coordinator-610/schema2-initial-manifest.json'
            and manifest.get('intermediate_publication_status') == 'HISTORICAL_SUPERSEDED_VALIDATOR'
            and manifest.get('intermediate_publication_sha256') == publication.get('intermediate_manifest_sha256')
            == sha(located(packet, manifest['intermediate_publication'])), 'Intermediate publication mismatch')
    return {'verdict': 'PASSED', 'classification': 'HISTORICAL_EXECUTION_PACKET',
            'current_checkout_acceptance': False, 'checks': len(checks),
            'source_files': 1160, 'executed_source_files': 1158, 'publication_only_source_files': 2}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--retained-source-root', type=Path,
                        help='Optional extracted historical fixture, never the live checkout')
    args = parser.parse_args()
    print(json.dumps(verify(args.root, args.retained_source_root)))
