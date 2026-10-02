"""Run directly with unittest and an allowlisted environment; no app/bootstrap.

Real PostgreSQL 17/Docker controls use only round18_s1 resources and port 5591.
"""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('bounded_pg_backup', ROOT / 'tools/bounded_pg_backup.py')
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BoundaryTests(unittest.TestCase):
    def test_hostile_numeric_bounds_refuse_direct_calls(self):
        for value in (None, True, False, 0, -1, float('nan'), float('inf'), '300', 301):
            with self.subTest(value=repr(value)), self.assertRaises(backup.Refusal):
                backup.bounds(value, 1024)
        for value in (None, True, 0, -1, 1.0, float('nan'), '1', backup.MAX_BYTES + 1):
            with self.subTest(value=repr(value)), self.assertRaises(backup.Refusal):
                backup.bounds(1, value)
        backup.bounds(300, backup.MAX_BYTES)

    def test_default_cli_cannot_connect(self):
        result = subprocess.run([os.sys.executable, '-I', '-B', str(ROOT / 'tools/bounded_pg_backup.py')],
                                env=backup.ENV, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(b'postgresql://', result.stdout + result.stderr)

    def test_absent_empty_corrupt_and_public_archive_refused(self):
        with tempfile.TemporaryDirectory(prefix=backup.PREFIX) as directory:
            path = Path(directory) / 'archive'
            with self.assertRaises(backup.Refusal):
                backup.inspect_archive(path)
            for content in (b'', b'not an archive', b'PGDMPcorrupt'):
                path.write_bytes(content)
                path.chmod(0o600)
                with self.subTest(content=content), self.assertRaises(backup.Refusal):
                    backup.inspect_archive(path)
            path.chmod(0o644)
            with self.assertRaises(backup.Refusal):
                backup.inspect_archive(path)

    def test_receipt_is_exclusive_private_and_read_back(self):
        with tempfile.TemporaryDirectory(prefix=backup.PREFIX) as directory:
            path = Path(directory) / 'receipt'
            receipt = {**backup.provenance(), 'status': 'synthetic_only'}
            backup.write_new(path, receipt)
            self.assertEqual(json.loads(path.read_text()), receipt)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                backup.write_new(path, receipt)

    def test_empty_inventory_cannot_certify_restore(self):
        for value in (None, {}, [], [{'kind': 'catalog'}]):
            with self.subTest(value=value), self.assertRaises(backup.Refusal):
                backup.compare_inventory(value, value)

    def test_missing_catalog_or_table_identity_cannot_certify_restore(self):
        bad = [{'kind':'catalog'}, {'kind':'table','count':0,'sha256':'0'*64}]
        with self.assertRaises(backup.Refusal):
            backup.compare_inventory(bad, bad)

    def test_serialization_failure_leaves_no_receipt(self):
        with tempfile.TemporaryDirectory(prefix=backup.PREFIX) as directory:
            path = Path(directory) / 'receipt'
            with self.assertRaises(ValueError):
                backup.write_new(path, {'status':'complete','value':float('nan')})
            self.assertFalse(path.exists())


class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix=backup.PREFIX)
        cls.private = Path(cls.directory.name)
        cls.network = backup.PREFIX + 'net_' + uuid.uuid4().hex[:10]
        cls.source = backup.PREFIX + 'source_' + uuid.uuid4().hex[:10]
        cls.exporter = None
        cls.net_created = cls.source_created = False
        try:
            backup.run(['docker', 'network', 'create', '--internal', cls.network])
            cls.net_created = True
            backup.run(['docker', 'run', '-d', '--name', cls.source, '--network', cls.network,
                        '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', backup.IMAGE])
            cls.source_created = True
            deadline = time.monotonic() + 30
            while True:
                state = subprocess.run(['docker', 'exec', cls.source, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'],
                                       env=backup.ENV, capture_output=True, timeout=5)
                if state.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('local source not ready')
                time.sleep(0.1)
            cls.roles = cls.private / 'roles.sql'
            cls.roles.write_text('CREATE ROLE round18_s1_owner;\nCREATE ROLE round18_s1_reader;\n')
            cls.roles.chmod(0o600)
            schema = cls.roles.read_text() + '''
CREATE EXTENSION pgcrypto;
CREATE SCHEMA auth AUTHORIZATION round18_s1_owner;
CREATE SCHEMA storage AUTHORIZATION round18_s1_owner;
CREATE TABLE auth.users(id integer PRIMARY KEY, private_text text);
ALTER TABLE auth.users OWNER TO round18_s1_owner;
CREATE TABLE storage.objects(id integer PRIMARY KEY, bucket text);
ALTER TABLE storage.objects OWNER TO round18_s1_owner;
CREATE TABLE public.samples(id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
 amount numeric CHECK(amount >= 0), metadata jsonb, user_id integer REFERENCES auth.users(id));
ALTER TABLE public.samples OWNER TO round18_s1_owner;
ALTER TABLE public.samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.samples FORCE ROW LEVEL SECURITY;
GRANT USAGE ON SCHEMA public TO round18_s1_reader;
GRANT SELECT ON public.samples TO round18_s1_reader;
CREATE POLICY visible ON public.samples TO round18_s1_reader USING(amount=0);
INSERT INTO auth.users VALUES(1,'synthetic private');
INSERT INTO storage.objects VALUES(7,'metadata only; no object bytes');
INSERT INTO public.samples(id,amount,metadata,user_id) VALUES
 (19,NULL,'{"null":null,"zero":0,"flag":false}',1),
 (20,0,'{"project":"synthetic"}',1);
SELECT setval('public.samples_id_seq',900,true);
SELECT lo_from_bytea(76543,decode('00ff0012','hex'));
ALTER LARGE OBJECT 76543 OWNER TO round18_s1_owner;
GRANT SELECT ON LARGE OBJECT 76543 TO round18_s1_reader;
CREATE TABLE public.transport_fixture(id integer PRIMARY KEY, payload text);
INSERT INTO public.transport_fixture SELECT i,repeat(md5(i::text),128) FROM generate_series(1,1000) i;
'''
            backup.run(['docker', 'exec', '-i', cls.source, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1',
                        '-U', 'postgres', '-d', 'postgres'], input=schema.encode())
            cls.exporter, cls.resolved = cls.export_snapshot()
            cls.snapshot = cls.resolved.pop('snapshot')
            assert cls.resolved['readonly'] == 'on' and cls.resolved['isolation'] == 'repeatable read'
            cls.inventory = backup.inventory_local(cls.source, cls.snapshot)
            cls.archive = cls.private / 'full.dump'
            cls.acquisition = backup.acquire_local(cls.source, cls.network, cls.snapshot, cls.archive)
            assert cls.acquisition['status'] == 'acquired_unverified', cls.acquisition
            cls.measurements = {'resolved': cls.resolved, 'acquisition': cls.acquisition}
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.exporter:
            cls.exporter.communicate(b"ROLLBACK;\n\\q\n", timeout=5)
            cls.exporter = None
        if cls.source_created:
            backup.remove_container(cls.source)
            cls.source_created = False
        if cls.net_created:
            backup.run(['docker', 'network', 'rm', cls.network])
            cls.net_created = False
        if hasattr(cls, 'measurements'):
            print('LOCAL_REHEARSAL_MEASUREMENTS=' + json.dumps(cls.measurements, sort_keys=True))
        cls.directory.cleanup()

    @classmethod
    def export_snapshot(cls):
        exporter = subprocess.Popen(['docker', 'exec', '-i', cls.source, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'postgres'], env=backup.ENV, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        exporter.stdin.write(b"BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SELECT json_build_object('snapshot',pg_export_snapshot(),'database',current_database(),'version',current_setting('server_version'),'readonly',current_setting('transaction_read_only'),'isolation',current_setting('transaction_isolation'));\n")
        exporter.stdin.flush()
        try:
            resolved = json.loads(exporter.stdout.readline())
        except BaseException:
            exporter.communicate(timeout=5)
            raise
        resolved.update(endpoint='owned Docker Unix socket', app_imported=False)
        return exporter, resolved

    def new_path(self):
        return self.private / (uuid.uuid4().hex + '.dump')

    def acquire(self, **kwargs):
        destination = self.new_path()
        result = backup.acquire_local(self.source, self.network, self.snapshot, destination, **kwargs)
        return destination, result

    def test_full_archive_restore_inventory_permissions_constraints_allocation(self):
        with contextlib.contextmanager(backup.restore_local)(self.archive, backup.sha256(self.archive), self.roles, backup.sha256(self.roles)) as restored:
            target = restored['target']
            after = backup.inventory_local(target)
            comparison = backup.compare_inventory(self.inventory, after)
            self.assertEqual(comparison['tables'], 4)
            # RLS really restricts the read role; null differs from zero.
            count = backup.run(['docker', 'exec', target, 'psql', '-XqAt', '-U', 'postgres', '-d', 'postgres',
                                '-c', 'SET ROLE round18_s1_reader; SELECT count(*) FROM public.samples;'])
            self.assertEqual(count.strip(), b'1')
            for invalid in ("INSERT INTO public.samples(amount,user_id) VALUES(-1,1)",
                            "INSERT INTO public.samples(amount,user_id) VALUES(1,999)"):
                with self.assertRaises(backup.Refusal):
                    backup.run(['docker', 'exec', target, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1',
                                '-U', 'postgres', '-d', 'postgres', '-c', invalid])
            allocation = backup.run(['docker', 'exec', target, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1',
                                     '-U', 'postgres', '-d', 'postgres', '-c',
                                     "BEGIN; SELECT nextval('public.samples_id_seq'); ROLLBACK; SELECT last_value FROM public.samples_id_seq;"])
            # Failed INSERT constraints consumed 901 and 902; rollback does not
            # undo nextval. This target is destroyed, never reset/reused.
            self.assertEqual(allocation.decode().splitlines(), ['903', '903'])
            self.measurements['restore'] = {**restored, 'inventory_equal': True,
                                           'constraints_refused': 2, 'rls_visible_rows': 1,
                                           'rollback_sequence_persists': True}
        state = subprocess.run(['docker', 'inspect', restored['target'], '--format', '{{.Name}}'], env=backup.ENV, capture_output=True)
        self.assertNotEqual(state.returncode, 0)

    def test_operator_cli_inspection_and_restore_remain_explicitly_unverified(self):
        inventory_file=self.private/'inventory.json'
        backup.write_new(inventory_file,self.inventory)
        base=[os.sys.executable,'-I','-B',str(ROOT/'tools/bounded_pg_backup.py')]
        for operation in (
            ['inspect','--archive',str(self.archive),'--expected-sha256',backup.sha256(self.archive)],
            ['restore-local','--archive',str(self.archive),'--expected-sha256',backup.sha256(self.archive),
             '--roles-file',str(self.roles),'--roles-sha256',backup.sha256(self.roles),
             '--inventory',str(inventory_file),'--inventory-sha256',backup.sha256(inventory_file)]):
            result=subprocess.run(base+operation,env=backup.ENV,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout)
            outcome=json.loads(result.stdout)
            self.assertFalse(outcome['backup_verified'])
            if operation[0]=='restore-local':
                self.assertTrue(outcome['inventory_equal'])
                self.assertEqual(outcome['status'],'local_inventory_equal_production_unverified')
                self.assertNotEqual(subprocess.run(['docker','inspect',outcome['target'],'--format','{{.Name}}'],env=backup.ENV,capture_output=True).returncode,0)

    def test_inspector_failure_removes_daemon_owned_child(self):
        from unittest.mock import patch
        original_run=backup.run
        started=[]
        def failed_list(argv,**kwargs):
            if argv[:3]==['docker','run','--rm'] and 'pg_restore' in argv:
                name=argv[argv.index('--name')+1]
                original_run(['docker','run','-d','--name',name,'--network','none','--entrypoint','sleep',backup.IMAGE,'infinity'])
                started.append(name)
                raise backup.Refusal('child_unavailable_or_timed_out')
            return original_run(argv,**kwargs)
        try:
            with patch.object(backup,'run',side_effect=failed_list),self.assertRaises(backup.Refusal):
                backup.inspect_archive(self.archive)
            self.assertEqual(len(started),1)
            self.assertNotEqual(subprocess.run(['docker','inspect',started[0],'--format','{{.Name}}'],env=backup.ENV,capture_output=True).returncode,0)
        finally:
            for name in started: backup.remove_container(name)

    def test_stall_is_killed_and_no_archive_is_published(self):
        path, result = self.acquire(wall_seconds=0.25, command=['sleep', '60'])
        self.assertEqual(result['status'], 'failed')
        self.assertIn(result['reason'], ('wall_expired', 'outer_wall_expired'))
        self.assertFalse(path.exists())
        self.assertLess(result['elapsed_seconds'], 5)
        self.measurements['stall'] = result

    def test_transport_breach_refuses_compressed_archive(self):
        path, result = self.acquire(transport_bytes=128 * 1024)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['reason'], 'transport_exceeded')
        self.assertGreater(result['transport_bytes'], 128 * 1024)
        self.assertFalse(path.exists())
        self.assertFalse(result['hard_transport_ceiling'])
        self.measurements['byte_breach'] = result

    def test_original_plan_has_no_wall_or_transport_enforcement(self):
        original = backup.PREFIX + 'original_' + uuid.uuid4().hex[:10]
        private = self.private / uuid.uuid4().hex
        private.mkdir(mode=0o700)
        process = lock = None
        try:
            backup.run(['docker','run','-d','--name',original,'--network',self.network,
                        '--mount',f'type=bind,src={private},dst=/backup',
                        '-e','PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=300000',
                        '--entrypoint','sleep',backup.IMAGE,'infinity'])
            lock = subprocess.Popen(['docker','exec','-i',self.source,'psql','-XqAt','-v','ON_ERROR_STOP=1','-U','postgres','-d','postgres'],env=backup.ENV,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            lock.stdin.write(b"BEGIN; LOCK TABLE public.transport_fixture IN ACCESS EXCLUSIVE MODE; SELECT 'locked';\n")
            lock.stdin.flush()
            self.assertEqual(lock.stdout.readline().strip(),b'locked')
            # Original Round17 acquisition command, adapted ONLY to owned local
            # credentials/source/paths. Statement timeout and lock timeout remain.
            started=time.monotonic()
            process=subprocess.Popen(['docker','exec',original,'sh','-c','umask 077; exec "$@"','original','pg_dump',
                '-h',self.source,'-U','postgres','-d','postgres','-Fc','--snapshot='+self.snapshot,'--lock-wait-timeout=5s',
                '--file=/backup/original.dump'],env=backup.ENV,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            time.sleep(0.35)
            original_still_running=process.poll() is None
            self.assertTrue(original_still_running)
            path,fixed=self.acquire(wall_seconds=0.25)
            self.assertEqual(fixed['status'],'failed')
            self.assertEqual(fixed['reason'],'wall_expired')
            self.assertFalse(path.exists())
            lock.communicate(b"ROLLBACK;\n\\q\n",timeout=5)
            lock=None
            stdout,stderr=process.communicate(timeout=10)
            self.assertEqual(process.returncode,0)
            self.assertEqual(stderr,b'')
            duration=time.monotonic()-started
            transferred=backup.network_bytes(original)
            size=(private/'original.dump').stat().st_size
            self.assertGreater(transferred,128*1024)
            self.assertLess(size,128*1024)
            self.measurements['original_plan_baseline']={'source_commit':'4acd7c0270a78a035557575125d77743ac2dbd5d',
                'wall_limit_assertion':'RED: dump still alive after0.35s at0.25s proposed bound',
                'byte_limit_assertion':'RED: successful original dump transport exceeds128KiB while compressed bytes below128KiB',
                'duration_seconds':duration,'transport_bytes':transferred,'archive_bytes':size,
                'fixed_locked_dump':fixed}
        finally:
            if lock:
                lock.communicate(b"ROLLBACK;\n\\q\n",timeout=5)
            backup.remove_container(original)
            if process and process.poll() is None:
                process.communicate(timeout=5)

    def test_truncated_data_archive_refuses_restore_even_if_toc_is_readable(self):
        path=self.new_path()
        data=self.archive.read_bytes()
        path.write_bytes(data[:len(data)//2])
        path.chmod(0o600)
        inspection=backup.inspect_archive(path)
        self.assertFalse(inspection['backup_verified'])
        with self.assertRaises(backup.Refusal):
            with contextlib.contextmanager(backup.restore_local)(path,backup.sha256(path),self.roles,backup.sha256(self.roles)):
                self.fail('truncated archive restored')

    def test_inventory_shape_sequence_and_coverage_mutants_refuse(self):
        import copy
        cases=[]
        for mutate in ('missing_table','duplicate_table','missing_identity','bad_count','bad_sequence','missing_catalog','bad_catalog'):
            mutant=copy.deepcopy(self.inventory)
            table=next(row for row in mutant if row['kind']=='table')
            sequence=next(row for row in mutant if row['kind']=='sequence')
            if mutate=='missing_table': mutant.remove(table)
            elif mutate=='duplicate_table': mutant.append(table)
            elif mutate=='missing_identity': del table['schema']
            elif mutate=='bad_count': table['count']=True
            elif mutate=='bad_sequence': sequence['last_value']=True
            elif mutate=='missing_catalog': del mutant[0]['roles']
            elif mutate=='bad_catalog': mutant[0]['relations']='wrong'
            cases.append((mutate,mutant))
        for name,mutant in cases:
            with self.subTest(name=name),self.assertRaises(backup.Refusal):
                backup.compare_inventory(mutant,mutant)

    def test_child_failure_credentials_are_not_in_public_result(self):
        path, result = self.acquire(command=['sh', '-c', 'printf "postgresql://user:synthetic_secret@host/db" >&2; exit 7'])
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(path.exists())
        self.assertNotIn('synthetic_secret', json.dumps(result))
        self.assertNotIn('postgresql://', json.dumps(result))

    def test_expired_snapshot_refuses_without_archive(self):
        exporter, resolved = self.export_snapshot()
        snapshot = resolved['snapshot']
        exporter.communicate(b"ROLLBACK;\n\\q\n", timeout=5)
        path = self.new_path()
        result = backup.acquire_local(self.source, self.network, snapshot, path)
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(path.exists())

    def test_unavailable_snapshot_and_noninternal_network_refuse(self):
        path = self.new_path()
        result = backup.acquire_local(self.source, self.network, 'FFFFFFFF-FFFFFFFF-9', path)
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(path.exists())
        with self.assertRaises(backup.Refusal):
            backup.acquire_local(self.source, 'bridge', self.snapshot, self.new_path())

    def test_partial_archive_is_not_a_backup_or_equal_restore(self):
        path, result = self.acquire(command=['pg_dump', '-Fc', '-t', 'public.samples', '--dbname=service=rehearsal', '--snapshot=' + self.snapshot])
        self.assertEqual(result['status'], 'acquired_unverified')
        self.assertFalse(result['backup_verified'])
        # Missing auth FK relation means the transaction fails, no bypass.
        with self.assertRaises(backup.Refusal):
            with contextlib.contextmanager(backup.restore_local)(path, backup.sha256(path), self.roles, backup.sha256(self.roles)):
                self.fail('partial archive certified')

    def test_missing_roles_and_corrupt_digests_refuse(self):
        for digest in ('0' * 64, '', None):
            with self.subTest(digest=digest), self.assertRaises((backup.Refusal, TypeError)):
                with contextlib.contextmanager(backup.restore_local)(self.archive, digest, self.roles, backup.sha256(self.roles)):
                    self.fail('bad archive digest accepted')
        empty_roles = self.private / 'empty_roles.sql'
        empty_roles.write_text('-- missing owners\n')
        empty_roles.chmod(0o600)
        with self.assertRaises(backup.Refusal):
            with contextlib.contextmanager(backup.restore_local)(self.archive, backup.sha256(self.archive), empty_roles, backup.sha256(empty_roles)):
                self.fail('missing owners accepted')

    def test_same_snapshot_excludes_later_rows_and_drift_refuses(self):
        backup.run(['docker', 'exec', self.source, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres',
                    '-d', 'postgres', '-c', "INSERT INTO storage.objects VALUES(9,'after exported snapshot');"])
        self.assertEqual(backup.inventory_local(self.source, self.snapshot), self.inventory)
        with self.assertRaises(backup.Refusal):
            backup.compare_inventory(self.inventory, backup.inventory_local(self.source))
        backup.run(['docker', 'exec', self.source, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres',
                    '-d', 'postgres', '-c', 'DELETE FROM storage.objects WHERE id=9;'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
