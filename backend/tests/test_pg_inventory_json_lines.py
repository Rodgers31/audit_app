"""Standalone regressions for psql JSON records containing Unicode separators."""
import contextlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load('inventory_framing_backup', ROOT / 'tools/bounded_pg_backup.py')
reviewed = load('inventory_framing_reviewed', ROOT / 'tools/reviewed_pg_acquisition.py')


def inventory():
    # A valid small inventory, including the exact character class seen in
    # PostgreSQL's JSON serialization of the migrated routine definitions.
    catalog = {key: None for key in backup.CATALOG_ARRAYS}
    catalog.update(kind='catalog', database_acl=None,
        schemas=[['public', 'postgres', None]],
        relations=[['public', 'fixture', 'r', 'postgres', None, False, False, None]],
        columns=[['public', 'fixture', 'id', 1, 'integer', True, '', '', None, None]],
        types=[['public', 'fixture', 'c', 'postgres', None, None, False, None, 'fixture', None]],
        roles=[['postgres', True, True, True, True, True, True, True, -1, None, None]],
        routines=[['public', 'fixture_function', '', 'postgres', None, None,
                   "CREATE FUNCTION fixture_function() RETURNS text LANGUAGE sql AS $$ SELECT 'Kenya\u0085\u2028\u2029'::text $$;\n"]],
        extensions=[['plpgsql', '1.0', 'pg_catalog', 'postgres', False, None, None]],
        tablespaces=[['pg_default', 'postgres', None, None]])
    return [catalog, {'kind': 'table', 'schema': 'public', 'name': 'fixture',
                      'count': 0, 'sha256': '0' * 64}]


def prerequisites():
    return dict(kind='recovery_prerequisites', readonly='on', isolation='repeatable read',
        activity_counts=dict(clients=0, active_clients=0, client_transactions=0,
            assigned_client_xids=0, background_workers=0, assigned_background_xids=0),
        database_properties=dict(name='postgres', owner='postgres', encoding='UTF8', locale_provider='i',
            collate='en_US.UTF-8', ctype='en_US.UTF-8', locale='en-US', icu_rules=None,
            collation_version='153.121', connection_limit=-1, allow_connections=True,
            tablespace='pg_default', acl=None),
        database_role_settings=None,
        system_schema_acls=[['information_schema', 'supabase_admin', None], ['pg_catalog', 'supabase_admin', None]],
        system_relation_acls=None, system_column_acls=None, system_routine_acls=None, parameter_acls=None)


def wire(records, separator=b'\n', final=b'\n'):
    return separator.join(json.dumps(row, ensure_ascii=False).encode('utf8') for row in records) + final


class InventoryLineFramingTests(unittest.TestCase):
    def local(self, raw):
        with patch.object(backup, 'isolated_container'), patch.object(backup, 'run', return_value=raw):
            result = backup.inventory_local('round19_s1_framing')
        backup.validate_inventory(result)
        return result

    def acquired(self, raw):
        identity = dict(database_name_sha256='a' * 64, server_address_sha256='b' * 64,
                        role='postgres', server_port=5432, version='17.6')
        @contextlib.contextmanager
        def exporter(*args):
            yield {**identity, 'snapshot': '0001-0001-1'}
        calls = []
        def child(argv, **kwargs):
            calls.append(argv)
            if 'psql' in argv:
                return raw
            if 'pg_dumpall' in argv:
                return b'-- synthetic role inventory, no passwords\n'
            if 'pg_dump' in argv:
                return b''
            return b'0\n0\n'
        with tempfile.TemporaryDirectory(prefix=reviewed.PREFIX) as directory:
            target = Path(directory)
            with patch.object(reviewed, 'exporter', exporter), patch.object(reviewed.backup, 'run', child):
                reviewed.capture('round19_s1_framing', target, identity, 3, 1024)
            result = json.loads((target / 'inventory.json').read_text())
            self.assertEqual(json.loads((target / 'recovery_prerequisites.json').read_text()), prerequisites())
        self.assertTrue(any('pg_dump' in argv for argv in calls))
        return result

    def test_local_routine_contents_survive_json_record_transport(self):
        records = inventory()
        for ending in (b'\n', b'\r\n', b''):
            with self.subTest(ending=ending):
                raw = wire(records, separator=b'\r\n' if ending == b'\r\n' else b'\n', final=ending)
                self.assertEqual(self.local(raw), records)

    def test_acquired_routine_contents_survive_json_record_transport(self):
        records = inventory()
        for ending in (b'\n', b'\r\n', b''):
            with self.subTest(ending=ending):
                raw = wire(records + [prerequisites()], separator=b'\r\n' if ending == b'\r\n' else b'\n', final=ending)
                self.assertEqual(self.acquired(raw), records)

    def test_unicode_outside_json_strings_cannot_separate_records(self):
        # Exclude the valid string contents so the former parser's erroneous
        # acceptance of these *structural* separators is independently visible.
        records = inventory()
        records[0]['routines'][0][-1] = 'SELECT 1'
        for separator in ('\u0085', '\u2028', '\u2029'):
            for reader, values in ((self.local, records), (self.acquired, records + [prerequisites()])):
                with self.subTest(separator=repr(separator), reader=reader.__name__):
                    with self.assertRaises(json.JSONDecodeError):
                        reader(wire(values, separator=separator.encode('utf8')))

    def test_malformed_or_blank_records_still_refuse(self):
        records = inventory()
        records[0]['routines'][0][-1] = 'SELECT 1'
        for reader, values in ((self.local, records), (self.acquired, records + [prerequisites()])):
            valid = wire(values)
            for raw in (b'\xff\n' + valid, b'{}{}\n' + valid, b'\n' + valid,
                        valid + b'\n', b'{\n' + valid):
                with self.subTest(reader=reader.__name__, raw=raw[:12]):
                    with self.assertRaises((json.JSONDecodeError, UnicodeDecodeError)):
                        reader(raw)


if __name__ == '__main__':
    unittest.main(verbosity=2)
