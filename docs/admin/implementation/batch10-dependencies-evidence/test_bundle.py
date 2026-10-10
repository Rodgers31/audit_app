"""Run controls against the published archive, including forged success records."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from verify_bundle import verify, validate_builder

ARCHIVE, MANIFEST = map(Path, sys.argv[1:3])
del sys.argv[1:3]


class BundleControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='batch10-dependencies-bundle-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = json.loads(MANIFEST.read_bytes())

    def with_manifest(self, manifest, archive=ARCHIVE):
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(manifest))
        return verify(archive, path)

    def forge_record(self, changes):
        name = 'raw/baseline-install.json'
        with zipfile.ZipFile(ARCHIVE) as original:
            record = json.loads(original.read(name))
            record.update(changes)
            content = json.dumps(record).encode()
        archive, manifest = self.forge_members({name: content})
        manifest['records']['baseline-install'].update(changes)
        return archive, manifest

    def forge_members(self, replacements):
        manifest = copy.deepcopy(self.manifest)
        archive = self.root / ('forged-' + str(len(list(self.root.glob('*.zip')))) + '.zip')
        with zipfile.ZipFile(ARCHIVE) as original, zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as output:
            for member in original.namelist():
                output.writestr(member, replacements.get(member, original.read(member)))
        for name, content in replacements.items():
            manifest['files'][name] = hashlib.sha256(content).hexdigest()
        manifest['archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
        return archive, manifest

    def test_published_bytes(self):
        self.assertGreater(verify(ARCHIVE, MANIFEST)['verified_records'], 50)

    def test_missing_archive(self):
        with self.assertRaises(OSError):
            verify(self.root / 'absent.zip', MANIFEST)

    def test_empty_inventory(self):
        self.manifest['records'] = {}
        with self.assertRaisesRegex(ValueError, 'empty record'):
            self.with_manifest(self.manifest)

    def test_missing_required_record(self):
        del self.manifest['records']['linux-native']
        with self.assertRaisesRegex(ValueError, 'missing required'):
            self.with_manifest(self.manifest)

    def test_changed_archive_identity(self):
        self.manifest['archive_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'archive hash'):
            self.with_manifest(self.manifest)

    def test_changed_member_identity(self):
        self.manifest['files']['outputs/baseline.css'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'member hash'):
            self.with_manifest(self.manifest)

    def test_failed_child_cannot_be_green(self):
        archive, manifest = self.forge_record({'exit': 1})
        with self.assertRaisesRegex(ValueError, 'false command verdict'):
            self.with_manifest(manifest, archive)

    def test_boolean_exit_rejected(self):
        archive, manifest = self.forge_record({'exit': False})
        with self.assertRaisesRegex(ValueError, 'exit type'):
            self.with_manifest(manifest, archive)

    def test_strict_manifest_version_and_expected_exit(self):
        for version in (True, 1.0):
            manifest = copy.deepcopy(self.manifest)
            manifest['schema'] = version
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'manifest schema'):
                self.with_manifest(manifest)
        self.manifest['records']['baseline-install']['exit'] = False
        with self.assertRaisesRegex(ValueError, 'expected exit type'):
            self.with_manifest(self.manifest)

    def test_signal_command_and_source_provenance(self):
        for changes, diagnostic in [({'signal': 9}, 'exit/signal'), ({'command': []}, 'command provenance'),
                                    ({'command': None}, 'command provenance')]:
            archive, manifest = self.forge_record(changes)
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, diagnostic):
                self.with_manifest(manifest, archive)
        with zipfile.ZipFile(ARCHIVE) as original:
            source = json.loads(original.read('raw/baseline-install.json'))['source_before']
        source['files'] = {}
        archive, manifest = self.forge_record({'source_before': source, 'source_after': source})
        with self.assertRaisesRegex(ValueError, 'source inventory'):
            self.with_manifest(manifest, archive)

    def test_jest_verdict_inventory_and_counters(self):
        with zipfile.ZipFile(ARCHIVE) as original:
            results = json.loads(original.read('outputs/mac-jest.json'))
        for changes in ({'success': {'success': False}}, {'testResults': []}, {'numFailedTests': False},
                        {'numPassedTests': 2077.0}, {'numTotalTests': -1}):
            value = dict(results, **changes)
            archive, manifest = self.forge_members({'outputs/mac-jest.json': json.dumps(value).encode()})
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'Jest'):
                self.with_manifest(manifest, archive)

    def test_boolean_audit_count(self):
        name = 'baseline-audit-production'
        with zipfile.ZipFile(ARCHIVE) as original:
            audit = json.loads(original.read('raw/' + name + '.stdout'))
            receipt = json.loads(original.read('raw/' + name + '.json'))
        audit['metadata']['vulnerabilities']['total'] = False
        content = json.dumps(audit).encode()
        receipt['stdout_sha256'] = hashlib.sha256(content).hexdigest()
        archive, manifest = self.forge_members({'raw/' + name + '.stdout': content,
                                               'raw/' + name + '.json': json.dumps(receipt).encode()})
        with self.assertRaisesRegex(ValueError, 'audit count type'):
            self.with_manifest(manifest, archive)

    def test_unknown_generator_rejected(self):
        archive, manifest = self.forge_record({'generator_sha256': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'unknown generator'):
            self.with_manifest(manifest, archive)

    def test_builder_empty_malformed_and_boolean(self):
        with zipfile.ZipFile(ARCHIVE) as packet:
            index = packet.read('outputs/mac-builder-index.json')
            vectors = packet.read('outputs/mac-builder.bin')
            reference = packet.read('source/embeddings-index.json')
        for invalid in (b'{}', b'[]', b'null', b'', b'{broken'):
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, TypeError)):
                validate_builder(invalid, vectors, reference)
        value = json.loads(index)
        value['count'] = True
        with self.assertRaisesRegex(ValueError, 'builder count'):
            validate_builder(json.dumps(value).encode(), vectors, reference)
        with self.assertRaisesRegex(ValueError, 'byte length'):
            validate_builder(index, b'', reference)
        import struct
        for number in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(number=number), self.assertRaisesRegex(ValueError, 'non-finite'):
                validate_builder(index, struct.pack('<f', number) + vectors[4:], reference)


if __name__ == '__main__':
    unittest.main(verbosity=2)
