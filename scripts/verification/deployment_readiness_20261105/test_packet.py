"""Exercise the offline inventory boundary with owned, inert files only."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name('packet.py')
spec = importlib.util.spec_from_file_location('readiness_packet', MODULE)
packet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packet)


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        self.file = self.root / 'source.txt'
        self.file.write_text('inert source\n')

    def test_nonempty_source_inventory_binds_final_bytes(self):
        records = packet.inventory(self.root, ['source.txt'])
        packet.check_inventory(self.root, records)
        self.file.write_text('changed\n')
        with self.assertRaises(packet.Refusal):
            packet.check_inventory(self.root, records)

    def test_inventory_rejects_empty_duplicate_and_path_aliases(self):
        for names in ([], ['source.txt', 'source.txt'], ['../outside'], ['/absolute'], ['./source.txt']):
            with self.subTest(names=names), self.assertRaises(packet.Refusal):
                packet.inventory(self.root, names)

    def test_missing_empty_and_boolean_size_refuse(self):
        record = packet.inventory(self.root, ['source.txt'])
        for bad in ([], [{**record[0], 'bytes': True}], [{**record[0], 'bytes': 0}], [{**record[0], 'sha256': '0' * 64}]):
            with self.subTest(bad=bad), self.assertRaises(packet.Refusal):
                packet.check_inventory(self.root, bad)
        self.file.unlink()
        with self.assertRaises(packet.Refusal):
            packet.check_inventory(self.root, record)

    def test_parent_and_leaf_links_refuse_before_read(self):
        real = self.base / 'real'
        real.mkdir()
        (real / 'data.json').write_text('{"safe":true}')
        link = self.base / 'alias'
        link.symlink_to(real, target_is_directory=True)
        leaf = self.base / 'leaf'
        leaf.symlink_to(real / 'data.json')
        for path in (link / 'data.json', leaf):
            with self.subTest(path=path), self.assertRaises(packet.Refusal):
                packet.read_regular(path)

    def test_hardlinks_fifo_and_oversize_refuse(self):
        alias = self.base / 'hard'
        os.link(self.file, alias)
        with self.assertRaises(packet.Refusal):
            packet.read_regular(alias)
        alias.unlink()
        fifo = self.base / 'fifo'
        os.mkfifo(fifo)
        with self.assertRaises(packet.Refusal):
            packet.read_regular(fifo)
        with self.assertRaises(packet.Refusal):
            packet.read_regular(self.file, limit=2)

    def test_json_duplicate_nonfinite_and_empty_refuse(self):
        for raw in (b'', b'{}', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            p = self.base / 'input.json'
            p.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(packet.Refusal):
                packet.load_object(p)

    def test_output_fresh_external_private_and_read_back(self):
        output = self.base / 'receipt.json'
        value = {'verdict': 'INVENTORY_ONLY', 'accepted': False}
        packet.publish(output, value, self.root)
        self.assertEqual(json.loads(output.read_text()), value)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(packet.Refusal):
            packet.publish(output, {'accepted': True}, self.root)
        self.assertEqual(json.loads(output.read_text()), value)
        with self.assertRaises(packet.Refusal):
            packet.publish(self.root / 'new.json', value, self.root)
        self.assertFalse((self.root / 'new.json').exists())

    def test_output_refuses_symlinked_parent(self):
        real = self.base / 'real'
        real.mkdir()
        alias = self.base / 'alias'
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaises(packet.Refusal):
            packet.publish(alias / 'receipt.json', {'a': 1}, self.root)
        self.assertFalse((real / 'receipt.json').exists())

    def test_capacity_does_not_add_different_units_or_unknowns(self):
        rows = [{'unit': 'pooler_clients', 'route_ref': 'a' * 64, 'limit': 200,
                 'measured_peak': None, 'other_population': None, 'accepted_reserve': None},
                {'unit': 'physical_pg', 'route_ref': 'b' * 64, 'limit': 60,
                 'measured_peak': 8, 'other_population': 8, 'accepted_reserve': 3}]
        result = packet.capacity(rows)
        self.assertEqual(result['state'], 'PENDING')
        self.assertEqual(len(result['partitions']), 2)
        self.assertIsNone(result['partitions'][0]['remaining'])
        self.assertEqual(result['partitions'][1]['remaining'], 41)
        self.assertFalse(result['production_capacity_accepted'])

    def test_capacity_hostile_scalar_types_and_zero_reserve_refuse(self):
        row = {'unit': 'physical_pg', 'route_ref': 'a' * 64, 'limit': 60,
               'measured_peak': 8, 'other_population': 8, 'accepted_reserve': 3}
        for field, bad in [('limit', True), ('limit', 0), ('measured_peak', -1),
                           ('measured_peak', float('nan')), ('accepted_reserve', 0),
                           ('other_population', '0'), ('unit', 'all_connections')]:
            with self.subTest(field=field, bad=bad), self.assertRaises(packet.Refusal):
                packet.capacity([{**row, field: bad}])
        with self.assertRaises(packet.Refusal):
            packet.capacity([])
        with self.assertRaises(packet.Refusal):
            packet.capacity([row, row])

    def test_metadata_inventory_never_opens_payload_or_follows_link(self):
        private = self.base / 'private'
        private.mkdir()
        (private / 'export.dump').write_bytes(b'inert test payload')
        (private / 'link').symlink_to(self.file)
        result = packet.metadata([private], max_entries=20, max_depth=2)
        self.assertEqual(result['scope'], 'METADATA_ONLY_NOT_EXPORT_CLASSIFICATION')
        self.assertEqual(result['regular_files'], 1)
        self.assertFalse(result['retention_compliant'])
        self.assertEqual({x['kind'] for x in result['entries']}, {'directory', 'regular', 'symlink'})
        self.assertNotIn('inert test payload', json.dumps(result))
        self.assertNotIn(str(private), json.dumps(result))
        with self.assertRaises(packet.Refusal):
            packet.metadata([private], max_entries=1, max_depth=2)

    def test_matrix_refuses_omitted_gate_and_success_or_truthy_controls(self):
        matrix = {'schema': 'deployment-readiness-matrix-v1',
                  'scope': 'PREPARATION_ONLY', 'release_authorized': False,
                  'controls': {k: False for k in packet.OFF_CONTROLS},
                  'gates': [{'id': name, 'state': 'pending_engineering',
                             'evidence': [], 'next': 'exact missing observation',
                             'authority': 'engineering'} for name in packet.GATE_IDS]}
        self.assertEqual(packet.check_matrix(matrix)['release'], 'HELD')
        for mutate in ('missing', 'empty', 'state', 'control', 'authority'):
            bad = copy.deepcopy(matrix)
            if mutate == 'missing': bad['gates'].pop()
            if mutate == 'empty': bad['gates'] = []
            if mutate == 'state': bad['gates'][0]['state'] = 'accepted'
            if mutate == 'control': bad['controls']['publishing'] = 0
            if mutate == 'authority': bad['release_authorized'] = 'false'
            with self.subTest(mutate=mutate), self.assertRaises(packet.Refusal):
                packet.check_matrix(bad)


if __name__ == '__main__':
    unittest.main()
