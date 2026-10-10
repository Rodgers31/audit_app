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
        manifest = copy.deepcopy(self.manifest)
        name = 'raw/baseline-install.json'
        with zipfile.ZipFile(ARCHIVE) as original:
            record = json.loads(original.read(name))
            record.update(changes)
            content = json.dumps(record).encode()
            archive = self.root / 'forged.zip'
            with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as output:
                for member in original.namelist():
                    output.writestr(member, content if member == name else original.read(member))
        manifest['files'][name] = hashlib.sha256(content).hexdigest()
        manifest['archive_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
        manifest['records']['baseline-install'].update(changes)
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
        with self.assertRaisesRegex(ValueError, 'record exit type'):
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
