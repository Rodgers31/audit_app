"""Validate the retained evidence bytes; this is not a remediation gate."""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import struct
import sys
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_builder(index_bytes, vector_bytes, reference_bytes):
    index = json.loads(index_bytes)
    reference = json.loads(reference_bytes)
    require(isinstance(index, dict), 'builder index must be an object')
    require(type(index.get('count')) is int and index['count'] == 264, 'builder count')
    require(type(index.get('dim')) is int and index['dim'] == 384, 'builder dimensions')
    require(index.get('model') == 'Xenova/all-MiniLM-L6-v2', 'builder model')
    require(index.get('articles') == reference['articles'], 'builder article identity/order')
    require(len(index['articles']) == index['count'], 'builder index length')
    require(len(vector_bytes) == 264 * 384 * 4, 'builder vector byte length')
    values = struct.unpack('<' + 'f' * (264 * 384), vector_bytes)
    require(all(math.isfinite(v) for v in values), 'non-finite builder value')
    drift = max(abs(math.sqrt(sum(v * v for v in values[i:i + 384])) - 1) for i in range(0, len(values), 384))
    require(drift < 0.0001, 'builder normalization')
    return {'count': 264, 'dim': 384, 'max_norm_error': drift}


def verify(archive, manifest_path):
    manifest = json.loads(Path(manifest_path).read_bytes())
    require(isinstance(manifest, dict) and type(manifest.get('schema')) is int and manifest['schema'] == 1, 'unknown manifest schema')
    require(manifest.get('base') == 'f6c31e271297eece52f34102dc40a1e2ed7069a8', 'wrong base')
    require(manifest.get('base_tree') == '69ddfad6deb814dd08fdaee2db2d512d73e14c78', 'wrong base tree')
    files = manifest.get('files')
    records = manifest.get('records')
    require(isinstance(files, dict) and bool(files), 'empty file inventory')
    require(isinstance(records, dict) and bool(records), 'empty record inventory')
    required_records = {'baseline-install', 'baseline-audit-full', 'baseline-audit-production', 'baseline-tree',
        'baseline-callers-corrected', 'baseline-native', 'baseline-boundaries', 'baseline-build-corrected',
        'mac-full-jest-parity', 'mac-preview-browser', 'mac-native-controls', 'mac-builder', 'mac-lint', 'mac-types',
        'linux-install', 'linux-audit-full', 'linux-audit-production', 'linux-tree', 'linux-native', 'linux-native-controls',
        'linux-boundaries', 'linux-build', 'linux-jest-parity', 'linux-preview-browser', 'linux-builder', 'linux-lint', 'linux-types',
        'candidate-config-only-css', 'candidate-official-css', 'candidate-official-audit', 'candidate-official-fresh-tree',
        'candidate-supported-tree', 'candidate-supported-audit', 'css-render-positive', 'css-render-negative',
        'advisory-braces', 'advisory-sprintf', 'registry-braces', 'registry-sprintf', 'issue-census'}
    require(required_records <= set(records), 'missing required evidence record')
    require(digest(Path(archive).read_bytes()) == manifest.get('archive_sha256'), 'archive hash mismatch')
    with zipfile.ZipFile(archive) as packet:
        names = packet.namelist()
        require(len(names) == len(set(names)), 'duplicate archive member')
        require(set(names) == set(files), 'archive inventory mismatch')
        for name in names:
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in name, 'unsafe archive path')
            require(digest(packet.read(name)) == files[name], 'member hash mismatch: ' + name)
        generators = {digest(packet.read(n)) for n in names if n.startswith('generators/') and n.endswith('.py')}
        require(bool(generators), 'missing generators')
        raw_names = {n.removeprefix('raw/').removesuffix('.json') for n in names if n.startswith('raw/') and n.endswith('.json')}
        require(raw_names == set(records), 'record inventory mismatch')
        for name, expected in records.items():
            require(isinstance(expected, dict), 'expected record must be an object')
            require(type(expected.get('exit')) is int and type(expected.get('verification_exit')) is int, 'expected exit type')
            require(type(expected.get('source_stable')) is bool, 'expected stability type')
            record = json.loads(packet.read('raw/' + name + '.json'))
            require(isinstance(record, dict), 'record must be an object')
            require(type(record.get('exit')) is int and type(record.get('verification_exit')) is int, 'record exit type')
            require(type(record.get('source_stable')) is bool, 'record stability type')
            require(record.get('generator_sha256') in generators, 'unknown generator: ' + name)
            command = record.get('command')
            require(isinstance(command, list) and bool(command) and all(isinstance(v, str) and bool(v) for v in command), 'missing command provenance')
            require(isinstance(record.get('cwd'), str) and Path(record['cwd']).is_absolute(), 'missing cwd provenance')
            signal = record.get('signal')
            require((record['exit'] >= 0 and signal is None) or
                    (record['exit'] < 0 and type(signal) is int and signal == -record['exit']), 'exit/signal contradiction')
            for axis in ('source_before', 'source_after'):
                source = record.get(axis)
                require(isinstance(source, dict) and isinstance(source.get('files'), dict) and bool(source['files']), 'missing source inventory')
                require(source.get('head') == manifest['base'] and source.get('tree') == manifest['base_tree'], 'source identity mismatch')
                for path in ('frontend/package.json', 'frontend/package-lock.json'):
                    require(source['files'].get(path) == files['source/' + path], 'source manifest identity mismatch')
            require(record['source_before']['files'].get(record.get('generated_by')) == record['generator_sha256'], 'starting generator identity mismatch')
            for stream in ('stdout', 'stderr'):
                require(digest(packet.read('raw/' + name + '.' + stream)) == record.get(stream + '_sha256'), 'stream hash: ' + name)
            for key in ('exit', 'verification_exit', 'source_stable', 'generator_sha256'):
                require(record.get(key) == expected.get(key), 'record contract mismatch: ' + name + '/' + key)
            require(record['source_before']['head'] == manifest['base'], 'historical record head: ' + name)
            require(record['source_before']['tree'] == manifest['base_tree'], 'historical record tree: ' + name)
            stable = record['source_before'] == record['source_after'] and record.get('input_before') == record.get('input_after')
            require(stable == record['source_stable'], 'stability verdict mismatch: ' + name)
            verdict = 0 if record['exit'] == 0 and stable and record.get('error') is None else 1
            require(record['verification_exit'] == verdict, 'false command verdict: ' + name)
        builders = {}
        for platform in ('mac', 'linux'):
            builders[platform] = validate_builder(packet.read('outputs/' + platform + '-builder-index.json'),
                packet.read('outputs/' + platform + '-builder.bin'), packet.read('source/embeddings-index.json'))
        for platform in ('mac', 'linux'):
            results = json.loads(packet.read('outputs/' + platform + '-jest.json'))
            require(isinstance(results, dict) and results.get('success') is True and results.get('wasInterrupted') is False, 'Jest failed/interrupted verdict')
            counts = {'numPassedTestSuites': 147, 'numFailedTestSuites': 0, 'numPendingTestSuites': 0,
                'numRuntimeErrorTestSuites': 0, 'numTotalTestSuites': 147, 'numTotalTests': 2078,
                'numPassedTests': 2077, 'numFailedTests': 0, 'numPendingTests': 1, 'numTodoTests': 0}
            require(all(type(results.get(k)) is int and results[k] == v for k, v in counts.items()), 'Jest counter type/value')
            suites = results.get('testResults')
            require(isinstance(suites, list) and len(suites) == 147, 'Jest suite inventory')
            # Jest labels the existing BudgetTab suite with its conditional
            # prerequisite skip as "focused"; assertion counts below still
            # require every executed case to pass and exactly one pending case.
            require(all(isinstance(s, dict) and s.get('status') in ('passed', 'focused') and isinstance(s.get('assertionResults'), list) for s in suites), 'Jest suite status')
            assertions = [a for s in suites for a in s['assertionResults']]
            require(len(assertions) == 2078 and all(isinstance(a, dict) for a in assertions), 'Jest assertion inventory')
            require(sum(a.get('status') == 'passed' for a in assertions) == 2077 and sum(a.get('status') == 'pending' for a in assertions) == 1, 'Jest assertion status')
            require(results.get('numPassedTestSuites') == 147 and results.get('numFailedTestSuites') == 0, 'Jest suites: ' + platform)
            require(results.get('numPassedTests') == 2077 and results.get('numFailedTests') == 0 and results.get('numPendingTests') == 1, 'Jest cases: ' + platform)
        for name, total in (('baseline-audit-full', 26), ('linux-audit-full', 27), ('baseline-audit-production', 0), ('linux-audit-production', 0)):
            audit = json.loads(packet.read('raw/' + name + '.stdout'))
            counts = audit['metadata']['vulnerabilities']
            require(all(type(counts.get(k)) is int and counts[k] >= 0 for k in ('info', 'low', 'moderate', 'high', 'critical', 'total')), 'audit count type/value')
            require(counts['total'] == sum(counts[k] for k in ('info', 'low', 'moderate', 'high', 'critical')), 'audit total mismatch')
            require(audit['metadata']['vulnerabilities']['total'] == total, 'audit count: ' + name)
        return {'verified_records': len(records), 'verified_files': len(files), 'builders': builders,
                'meaning': 'retained evidence integrity; issue acceptance remains unmet'}


if __name__ == '__main__':
    try:
        print(json.dumps(verify(*sys.argv[1:]), indent=2))
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
