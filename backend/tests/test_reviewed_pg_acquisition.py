"""Standalone operator boundary controls; no application/conftest imports."""
import datetime as dt
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('reviewed', ROOT / 'tools/reviewed_pg_acquisition.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)


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


class ReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=tool.PREFIX)
        self.directory = Path(self.temp.name)
        self.directory.chmod(0o700)
        self.request = dict(version=1, project=tool.PROJECT,
            expires_at=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)).isoformat(),
            generator_sha256=tool.backup.sha256(tool.__file__),
            inventory_generator_sha256=tool.backup.sha256(tool.backup.__file__),
            service_sha256='a'*64, pgpass_sha256='b'*64, ca_sha256='c'*64,
            identity=dict(database_name_sha256='d'*64, server_address_sha256='e'*64,
                          role='postgres', server_port=5432, version='17.6'),
            wall_seconds=300, transport_abort_bytes=128*1024*1024,
            transport_acknowledgement=tool.ACK, writer_freeze_receipt_sha256='f'*64)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, value):
        p = self.directory / 'request.json'
        p.write_text(json.dumps(value)); p.chmod(0o600)
        return p, tool.backup.sha256(p)

    def test_default_cli_refuses_without_connection(self):
        p = subprocess.run([os.sys.executable, '-I', '-B', str(ROOT/'tools/reviewed_pg_acquisition.py')],
                           env=tool.ENV, capture_output=True)
        self.assertEqual(p.returncode, 2)

    def test_review_requires_exact_current_bytes(self):
        p, h = self.write(self.request)
        self.assertEqual(tool.read_request(p, h)['project'], tool.PROJECT)
        with self.assertRaises(tool.Refusal):
            tool.read_request(p, '0'*64)

    def test_request_shapes_and_expiry_refuse_directly(self):
        for value in [None, {}, [], 'oops', {**self.request, 'version': True},
                      {**self.request, 'wall_seconds': float('nan')},
                      {**self.request, 'transport_abort_bytes': True},
                      {**self.request, 'transport_acknowledgement': 'hard_ceiling'},
                      {**self.request, 'expires_at': '2020-01-01T00:00:00+00:00'},
                      {**self.request, 'expires_at': '2999-01-01T00:00:00+00:00'},
                      {**self.request, 'generator_sha256': '0'*64},
                      {**self.request, 'inventory_generator_sha256': '0'*64},
                      {**self.request, 'identity': {}},
                      {**self.request, 'project': 'other'}]:
            with self.subTest(value=value), self.assertRaises((tool.Refusal, ValueError)):
                tool.read_request(*self.write(value))

    def credentials(self, **changes):
        fields = dict(host='db.'+tool.PROJECT+'.supabase.co', port='5432', user='postgres',
            dbname='postgres', connect_timeout='8', sslmode='verify-full',
            sslrootcert='/backup/root.crt', passfile='/backup/pgpass', gssencmode='disable')
        fields.update(changes)
        service = self.directory / 'service'
        service.write_text('['+tool.SERVICE+']\n'+'\n'.join(k+'='+v for k,v in fields.items())+'\n')
        pgpass = self.directory / 'password'; pgpass.write_text('synthetic-private-password')
        ca = self.directory / 'ca'; ca.write_text('synthetic-test-ca')
        for key, p in [('service_sha256', service), ('pgpass_sha256', pgpass), ('ca_sha256', ca)]:
            p.chmod(0o600); self.request[key] = tool.backup.sha256(p)
        target = self.directory / 'stage'; target.mkdir(exist_ok=True, mode=0o700)
        return target, service, pgpass, ca

    def test_tls_target_and_service_override_refuse_before_docker(self):
        for change in [dict(sslmode='require'), dict(sslmode='disable'), dict(host='evil.example'),
                       dict(port='6543'), dict(hostaddr='127.0.0.1'), dict(password='value'),
                       dict(options='-c transaction_read_only=off'), dict(user='root'),
                       dict(passfile='/tmp/password'), dict(sslrootcert='system')]:
            args = self.credentials(**change)
            with self.subTest(change=change), patch.object(tool.backup, 'run') as run, self.assertRaises(tool.Refusal):
                tool.stage_credentials(*args, self.request)
            run.assert_not_called()

    def test_private_inputs_hashes_and_readback(self):
        args = self.credentials()
        tool.stage_credentials(*args, self.request)
        self.assertEqual(tool.backup.sha256(args[0]/'pg_service.conf'), self.request['service_sha256'])
        self.assertEqual((args[0]/'pgpass').stat().st_mode & 0o777, 0o600)
        args[2].write_text('changed')
        with self.assertRaises(tool.Refusal): tool.stage_credentials(*args, self.request)

    def test_public_and_symlink_request_refuse(self):
        p,h = self.write(self.request); p.chmod(0o644)
        with self.assertRaises(tool.Refusal): tool.read_request(p,h)
        p.chmod(0o600); link = self.directory/'link'; link.symlink_to(p)
        with self.assertRaises(tool.Refusal): tool.read_request(link,h)

    def test_failed_review_never_calls_docker_or_publishes(self):
        args = self.credentials()
        p,h = self.write({**self.request, 'transport_acknowledgement': None})
        output = self.directory/'bundle'
        with patch.object(tool.backup, 'run') as run, self.assertRaises(tool.Refusal):
            tool.acquire_reviewed(p,h,*args[1:],output)
        run.assert_not_called(); self.assertFalse(output.exists())

    def test_partial_exporter_line_obeys_deadline(self):
        proc = subprocess.Popen([os.sys.executable, '-I', '-c',
            "import os,time;os.write(1,b'{');time.sleep(1)"], stdout=subprocess.PIPE, env=tool.ENV)
        began = time.monotonic()
        try:
            with self.assertRaises(tool.Refusal): tool.bounded_line(proc.stdout, began + .15)
            self.assertLess(time.monotonic() - began, .5)
        finally:
            proc.kill(); proc.wait(timeout=2); proc.stdout.close()

    def test_direct_capture_bounds_before_connections(self):
        for wall,limit in [(301,1024),(1,True),(1,float('nan')),(1,-1)]:
            with self.subTest(wall=wall,limit=limit), patch.object(tool, 'exporter') as exporter, self.assertRaises(tool.Refusal):
                tool.capture('round19_s1_test',self.directory,self.request['identity'],wall,limit)
            exporter.assert_not_called()

    def test_direct_capture_rejects_identical_malformed_identities(self):
        for key,value in [('server_port',True),('server_port',float('inf')),
                          ('database_name_sha256',''),('server_address_sha256',None),
                          ('role',None),('version',True)]:
            identity={**self.request['identity'],key:value}
            @contextlib.contextmanager
            def exporter(*args): yield {**identity,'snapshot':'0001-0001-1'}
            with self.subTest(key=key,value=value), patch.object(tool,'exporter',exporter), self.assertRaises(tool.Refusal):
                tool.capture('round19_s1_test',self.directory,identity,1,1024)

    def test_late_counter_abort_never_returns_acquired_inputs(self):
        @contextlib.contextmanager
        def exporter(*args): yield {**self.request['identity'],'snapshot':'0001-0001-1'}
        def child(argv, **kwargs):
            if 'pg_dumpall' in argv: return b'synthetic roles'
            if 'pg_dump' in argv: return b''
            if 'sh' in argv:
                (self.directory/'abort').write_text('transport_exceeded')
                return b'0\n0\n'
            return b'{}\n' + json.dumps(prerequisites()).encode() + b'\n'
        with patch.object(tool,'exporter',exporter), patch.object(tool.backup,'run',child), \
             patch.object(tool.backup,'validate_inventory'), self.assertRaises(tool.Refusal):
            tool.capture('round19_s1_test',self.directory,self.request['identity'],1,1024)

    def test_cleanup_abort_never_publishes(self):
        args = self.credentials(); p,h = self.write(self.request); output=self.directory/'bundle'
        acquired_directory = None
        def capture(client,directory,*args):
            nonlocal acquired_directory
            acquired_directory=directory
            return {'snapshot_shared':True}
        def remove(client): (acquired_directory/'abort').write_text('transport_exceeded')
        with patch.object(tool.backup,'run',return_value=b''), patch.object(tool,'capture',capture), \
             patch.object(tool,'remove',remove), patch.object(tool.backup,'inspect_archive') as inspect:
            result=tool.acquire_reviewed(p,h,*args[1:],output)
        self.assertEqual(result['status'],'failed'); self.assertFalse(output.exists());inspect.assert_not_called()

    def test_empty_or_whitespace_roles_never_publish_pending_inputs(self):
        args = self.credentials(); p, h = self.write(self.request)
        catalog = {key: None for key in tool.backup.CATALOG_ARRAYS}
        catalog.update(kind='catalog', database_acl=None,
            schemas=[['public', 'postgres', None]],
            relations=[['public', 'fixture', 'r', 'postgres', None, False, False, None]],
            columns=[['public', 'fixture', 'id', 1, 'integer', True, '', '', None, None]],
            types=[['public', 'fixture', 'c', 'postgres', None, None, False, None, 'fixture', None]],
            roles=[['postgres', True, True, True, True, True, True, True, -1, None, None]],
            extensions=[['plpgsql', '1.0', 'pg_catalog', 'postgres', False, None, None]],
            tablespaces=[['pg_default', 'postgres', None, None]])
        raw = '\n'.join(json.dumps(r) for r in [catalog, dict(kind='table', schema='public',
            name='fixture', count=0, sha256='a'*64), prerequisites()]).encode()
        @contextlib.contextmanager
        def exporter(*args): yield {**self.request['identity'], 'snapshot': '0001-0001-1'}
        for index, roles in enumerate((b'', b' \t\r\n', b'-- reviewed role dump header\n')):
            captured = None
            def child(argv, **kwargs):
                nonlocal captured
                if argv[:2] == ['docker', 'run']:
                    captured = Path(argv[argv.index('--mount')+1].split('src=')[1].split(',dst=')[0])
                if 'psql' in argv: return raw
                if 'pg_dumpall' in argv: return roles
                if 'pg_dump' in argv:
                    dump = captured/'database.dump'; dump.write_bytes(b'PGDMPfixture'); dump.chmod(0o600)
                if 'sh' in argv and argv[1] == 'exec': return b'0 0'
                return b''
            output = self.directory/('roles_bundle_'+str(index))
            with self.subTest(roles=roles), patch.object(tool, 'exporter', exporter), \
                 patch.object(tool.backup, 'run', child), patch.object(tool, 'remove'), \
                 patch.object(tool.backup, 'inspect_archive'):
                result = tool.acquire_reviewed(p, h, *args[1:], output)
                if roles.strip():
                    self.assertEqual(result['status'], 'acquired_inputs_restore_and_completeness_pending')
                    self.assertFalse(result['backup_verified'])
                    self.assertIn('recovery_prerequisites.json', result['artifacts'])
                    self.assertEqual(json.loads((output/'recovery_prerequisites.json').read_text()), prerequisites())
                else:
                    self.assertEqual(result['status'], 'failed')
                    self.assertFalse(output.exists())

    def test_recovery_configuration_changes_reject_restore(self):
        import copy
        before = prerequisites()
        for key, value in [('locale', 'fr-FR'), ('encoding', 'SQL_ASCII'), ('owner', 'other'),
                           ('collation_version', 'wrong'), ('acl', ['other=C/postgres'])]:
            after = copy.deepcopy(before); after['database_properties'][key] = value
            with self.subTest(key=key), self.assertRaises(tool.Refusal):
                tool.compare_recovery_prerequisites(before, after)
        after = copy.deepcopy(before); after['database_role_settings'] = [[None, 'postgres', ['statement_timeout=1s']]]
        with self.assertRaises(tool.Refusal): tool.compare_recovery_prerequisites(before, after)

    def test_recovery_missing_and_malformed_configuration_refused(self):
        import copy
        before = prerequisites()
        for key in before:
            value = copy.deepcopy(before); del value[key]
            with self.subTest(missing=key), self.assertRaises(tool.Refusal): tool.validate_recovery_prerequisites(value)
        for value in (None, {}, [], True):
            with self.subTest(value=value), self.assertRaises(tool.Refusal): tool.validate_recovery_prerequisites(value)
        for count in (True, -1, float('nan'), float('inf')):
            value = copy.deepcopy(before); value['activity_counts']['clients'] = count
            with self.subTest(count=count), self.assertRaises(tool.Refusal): tool.validate_recovery_prerequisites(value)
        for rows in (None, [], [['pg_catalog', 'supabase_admin', None]]):
            value = copy.deepcopy(before); value['system_schema_acls'] = rows
            with self.subTest(schemas=rows), self.assertRaises(tool.Refusal): tool.validate_recovery_prerequisites(value)

    def test_activity_changes_do_not_mask_configuration_comparison(self):
        after = prerequisites(); after['activity_counts']['background_workers'] = 8
        tool.compare_recovery_prerequisites(prerequisites(), after)

    def test_optional_system_acl_objects_compare_and_duplicates_refuse(self):
        import copy
        before = prerequisites()
        before['system_routine_acls'] = [['pg_catalog', 'fixture', '', 'supabase_admin', ['postgres=X/supabase_admin']]]
        tool.validate_recovery_prerequisites(before)
        after = copy.deepcopy(before); after['system_routine_acls'][0][-1] = []
        with self.assertRaises(tool.Refusal): tool.compare_recovery_prerequisites(before, after)
        after = copy.deepcopy(before); after['system_routine_acls'] *= 2
        with self.assertRaises(tool.Refusal): tool.validate_recovery_prerequisites(after)

    def test_independently_found_invalid_durable_fields_refuse_even_identical_compare(self):
        import copy
        cases = []
        for key in ('icu_rules', 'collation_version'):
            value = prerequisites(); value['database_properties'][key] = 'invalid\x00text'; cases.append(value)
        for key, row in (
            ('system_relation_acls', ['pg_catalog', 'fixture', 'r', 'supabase_admin', None]),
            ('system_column_acls', ['pg_catalog', 'fixture', 'id', None]),
            ('system_routine_acls', ['pg_catalog', 'fixture', '', 'supabase_admin', None])):
            value = prerequisites(); value[key] = [row]; cases.append(value)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(tool.Refusal): tool.validate_recovery_prerequisites(value)
            with self.subTest(compare=value), self.assertRaises(tool.Refusal): tool.compare_recovery_prerequisites(value, copy.deepcopy(value))


if __name__ == '__main__':
    unittest.main(verbosity=2)
