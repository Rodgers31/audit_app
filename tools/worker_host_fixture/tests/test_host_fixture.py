"""Behavioral refusal controls for the opt-in, synthetic host qualification."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

HERE = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location('host_fixture_' + name, HERE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class HostFixtureTests(unittest.TestCase):
    def setUp(self):
        self.decode = module('decode').decode
        self.custody = module('custody')
        self.expected = dict(name='capacity', run_id='a' * 12,
            manifest_sha256='b' * 64, generator_sha256='c' * 64)

    def chunks(self, content):
        data = base64.b64encode(zlib.compress(content)).decode()
        pieces = [data[i:i+1536] for i in range(0, len(data), 1536)]
        return [dict(version=1, **self.expected, index=i, count=len(pieces),
                     size=len(content), sha256=hashlib.sha256(content).hexdigest(), data=part)
                for i, part in enumerate(pieces)]

    def test_actual_chunk_roundtrip_and_incomplete_refusal(self):
        content = hashlib.shake_256(b'public fixture').digest(64000)
        rows = self.chunks(content)
        self.assertGreater(len(rows), 1)
        self.assertEqual(self.decode(list(reversed(rows)), **self.expected), content)
        for broken in ([], rows[1:], rows + [rows[0]], [dict(rows[0], count=True)],
                       [dict(row, run_id='d' * 12) for row in rows],
                       [dict(row, generator_sha256='d' * 64) for row in rows]):
            with self.subTest(broken=len(broken)), self.assertRaises(ValueError):
                self.decode(broken, **self.expected)

    def test_payload_tampering_and_compression_bound_refuse(self):
        content = b'public inert artifact'
        rows = self.chunks(content)
        for key, value in [('size', True), ('size', len(content)+1), ('version', True),
                           ('index', False), ('sha256', 'f'*64), ('data', '@@@'),
                           ('data', base64.b64encode(zlib.compress(content)+b'trailing').decode())]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.decode([dict(rows[0], **{key:value})], **self.expected)
        bomb = b'0' * (4 * 1024 ** 2 + 1)
        with self.assertRaises(ValueError):
            self.decode(self.chunks(bomb), **self.expected)

    def test_real_receipt_pipe_required(self):
        read_fd, write_fd = os.pipe()
        try:
            argv = ['python', '-m', 'social.worker', '--supervisor-receipt-fd', str(write_fd)]
            self.assertEqual(self.custody.receipt_descriptor(argv), write_fd)
            for value in ('0', '1', '2', '-1', '512', '999999', True, None, str(read_fd)):
                with self.subTest(value=value), self.assertRaises((ValueError, OSError)):
                    self.custody.receipt_descriptor(argv[:-1] + [value])
            with self.assertRaises(ValueError):
                self.custody.receipt_descriptor(argv + ['--supervisor-receipt-fd', str(write_fd)])
            with open(__file__, 'rb') as source:
                with self.assertRaises(ValueError):
                    self.custody.receipt_descriptor(argv[:-1] + [str(source.fileno())])
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_duplicate_native_receipt_never_reaches_backup(self):
        payload = (b'{"version":1,"owner_id":"11111111-1111-4111-8111-111111111111",'
            b'"generation":1,"providers_closed":false,"providers_closed":true,'
            b'"executor_closed":true,"claims_drained":true}')
        with self.assertRaisesRegex(ValueError, 'Duplicate native receipt key'):
            self.custody.closure_backup(payload)

    def test_private_mount_parser_executes_and_refuses_unknown_propagation(self):
        isolation = module('isolation')
        valid = '1 0 0:1 / / rw - overlay overlay rw\n2 1 0:2 / /proc ro - proc proc ro\n'
        self.assertEqual(isolation.private_mounts(valid), 2)
        for value in ('', None, [], valid.replace(' - overlay', ' shared:5 - overlay'),
                      valid + valid, valid.replace(' / rw ', ' / rw,ro '),
                      valid.replace(' / rw ', ' /other rw '),
                      valid.replace(' - overlay ', ' - bad/type '), 'x'*524289):
            with self.subTest(value=str(value)[:50]), self.assertRaises(RuntimeError):
                isolation.private_mounts(value)

    def test_copied_null_device_refuses_regular_links_and_other_devices(self):
        import stat
        isolation = module('isolation')
        valid = SimpleNamespace(st_mode=stat.S_IFCHR|0o666,st_rdev=os.makedev(1,3))
        with patch.object(isolation.os,'stat',return_value=valid) as observed:
            self.assertIs(isolation.null_device(),True)
            observed.assert_called_once_with('/dev/null',follow_symlinks=False)
        for mode,device in ((stat.S_IFREG|0o666,os.makedev(1,3)),
                            (stat.S_IFLNK|0o777,os.makedev(1,3)),
                            (stat.S_IFCHR|0o666,os.makedev(1,5))):
            with patch.object(isolation.os,'stat',return_value=SimpleNamespace(st_mode=mode,st_rdev=device)), \
                    self.assertRaises(RuntimeError):
                isolation.null_device()

    def test_device_archive_has_one_canonical_safe_device(self):
        import tarfile
        builder = module('build_root')
        self.assertIs(builder.validate_device_archive(HERE/'dev-null.tar'),True)
        with tempfile.TemporaryDirectory() as folder:
            for field,value in (('name','../../etc/passwd'),('type',tarfile.SYMTYPE),
                                ('devmajor',8),('devminor',5),('uid',10001),('mode',0o777),
                                ('linkname','/dev/null'),('mtime',1),('uname','unexpected'),
                                ('gname','unexpected')):
                target = Path(folder)/'bad.tar'
                item=tarfile.TarInfo('dev/null');item.type=tarfile.CHRTYPE
                item.devmajor=1;item.devminor=3;item.mode=0o666
                setattr(item,field,value)
                with tarfile.open(target,'w',format=tarfile.USTAR_FORMAT) as archive:
                    archive.addfile(item)
                with self.subTest(field=field),self.assertRaises(RuntimeError):
                    builder.validate_device_archive(target)
            for form in (tarfile.GNU_FORMAT, tarfile.PAX_FORMAT):
                with tarfile.open(target,'w',format=form) as archive:
                    item=tarfile.TarInfo('dev/null');item.type=tarfile.CHRTYPE
                    item.devmajor=1;item.devminor=3;item.mode=0o666
                    if form == tarfile.PAX_FORMAT:
                        item.pax_headers={'comment':'unexpected'}
                    archive.addfile(item)
                with self.subTest(format=form),self.assertRaises(RuntimeError):
                    builder.validate_device_archive(target)
            altered=bytearray((HERE/'dev-null.tar').read_bytes());altered[2048]=1
            target.write_bytes(altered)
            with self.assertRaises(RuntimeError):
                builder.validate_device_archive(target)

    def test_root_replacement_permissions_refuse_before_capability_checks(self):
        isolation = module('isolation')
        class FakePath:
            def __init__(self, name):
                self.name = name
            def exists(self):
                return False
            def stat(self):
                return SimpleNamespace(st_uid=65534, st_mode=0o777 if self.name == '/' else 0o555)
        with patch.object(isolation, 'Path', FakePath), patch.object(isolation, 'os',
                SimpleNamespace(getuid=lambda:10001,getgid=lambda:10001)), \
                patch.object(isolation, 'LIBC', SimpleNamespace()):
            with self.assertRaisesRegex(RuntimeError, 'replaceable'):
                isolation.post_exec()

    def test_mapped_identity_drift_refuses_before_observer_or_network(self):
        isolation = module('isolation')
        for identity in ('uid', 'gid'):
            state = {'mapped':False}
            class FakePath:
                def __init__(self, name):
                    self.name = name
                def write_text(self, value):
                    if self.name.endswith('gid_map'):
                        state['mapped'] = True
            fake_os = SimpleNamespace(getpid=lambda:1,
                getuid=lambda:0 if state['mapped'] and identity == 'uid' else 10001,
                getgid=lambda:0 if state['mapped'] and identity == 'gid' else 10001,
                readlink=lambda name:name)
            with patch.object(isolation, 'Path', FakePath), patch.object(isolation, 'os', fake_os), \
                    patch.object(isolation, 'LIBC', SimpleNamespace(unshare=lambda flags:0)):
                with self.subTest(identity=identity), self.assertRaisesRegex(RuntimeError, 'Mapped identity changed'):
                    isolation.enter_namespaces()

    def test_directory_stdio_never_crosses_chroot_boundary(self):
        isolation = module('isolation')
        with patch.object(isolation.os, 'fstat', return_value=SimpleNamespace(st_mode=0o040755)):
            with self.assertRaisesRegex(RuntimeError, 'Real null stdin'):
                isolation.stdio_boundary()

    def test_only_exact_private_helper_log_descriptors_are_admitted(self):
        isolation = module('isolation')
        for failure in (None, 'inode', 'owner', 'mode', 'links', 'symlink'):
            info = SimpleNamespace(st_mode=0o100644 if failure == 'mode' else 0o100600,
                st_uid=55 if failure == 'owner' else 10001,
                st_nlink=2 if failure == 'links' else 1, st_dev=5, st_ino=7)
            expected = SimpleNamespace(st_dev=5, st_ino=8 if failure == 'inode' else 7)
            class FakePath:
                def __init__(self, path):
                    self.path = path
                def is_symlink(self):
                    return failure == 'symlink'
                def stat(self):
                    return expected
            fakeos = SimpleNamespace(getuid=lambda:10001, makedev=os.makedev,
                fstat=lambda fd:SimpleNamespace(st_mode=0o020666,st_rdev=os.makedev(1,3)) if fd == 0 else info)
            with patch.object(isolation, 'os', fakeos), patch.object(isolation, 'Path', FakePath):
                if failure is None:
                    isolation.stdio_boundary(log_name='endpoint')
                    with self.assertRaises(RuntimeError):
                        isolation.stdio_boundary()  # The app never admits regular stdio.
                else:
                    with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                        isolation.stdio_boundary(log_name='endpoint')

    def test_private_port_mapping_never_redirects_another_destination(self):
        mapping = module('portmap')
        seen = []
        class Socket:
            def connect(self, address):
                seen.append(address)
                return 11
            def connect_ex(self, address):
                seen.append(address)
                return 12
        with patch.object(mapping, 'socket', SimpleNamespace(socket=Socket)):
            mapping.install()
            current = Socket()
            self.assertEqual(current.connect(('127.0.0.4',443)), 11)
            self.assertEqual(seen[-1], ('127.0.0.4',8443))
            self.assertEqual(current.connect_ex(('192.0.2.1',443)), 12)
            self.assertEqual(seen[-1], ('192.0.2.1',443))
            with self.assertRaises(RuntimeError):
                mapping.install()
        for address in (None, True, ('127.0.0.4',True), ('127.0.0.4',8443),
                        ('graph.facebook.com',443), ['127.0.0.4',443], ('127.0.0.4',443,0,0)):
            self.assertIs(mapping.destination(address), address)
        with patch.object(mapping, 'trim_inert_heap'):
            self.assertEqual(mapping.endpoint_server(('127.0.0.4',443), 'handler',
                lambda address, handler:(address,handler)), (('127.0.0.4',8443),'handler'))
        with self.assertRaises(ValueError):
            mapping.endpoint_server(('0.0.0.0',443), None, lambda *args:True)

    def test_inert_allocator_advice_never_claims_bytes_reclaimed(self):
        mapping = module('portmap')
        for value in (0, 1, True, False, None, 2, -1):
            class Function:
                def __call__(self, argument):
                    self.argument = argument
                    return value
            function = Function()
            with patch('ctypes.CDLL', return_value=SimpleNamespace(malloc_trim=function)):
                if type(value) is int and value in (0, 1):
                    self.assertIsNone(mapping.trim_inert_heap())
                    self.assertEqual(function.argument, 0)
                else:
                    with self.assertRaises(RuntimeError):
                        mapping.trim_inert_heap()

    def test_no_ambient_configuration_and_exact_owned_identity(self):
        config = module('host_config')
        sys.path.insert(0, str(HERE.parent / 'worker_rehearsal'))
        try:
            from bounded_profile import inert_environment
            with patch.dict(os.environ, {'DATABASE_URL':'production-not-admitted', 'SECRET_KEY':'private'}, clear=True):
                values = config.environment('0'*12)
            inert_environment(values)
            self.assertNotIn('production-not-admitted', values.values())
            self.assertEqual(values['SOCIAL_MEDIA_ENABLED'], 'false')
            self.assertEqual(values['SOCIAL_MEDIA_RETAINED_WRITES_ENABLED'], 'false')
            for identity in (None, True, '', 'a'*11, 'a'*13, '../'+'a'*9, 'G'*12):
                with self.assertRaises(ValueError):
                    config.environment(identity)
        finally:
            sys.path.pop(0)

    def test_observer_consumer_rejects_missing_wrong_and_stale_measurements(self):
        sys.path[:0] = [str(HERE), str(HERE.parent / 'worker_rehearsal')]
        try:
            driver = module('driver')
            instance = driver.HostRehearsal.__new__(driver.HostRehearsal)
            instance.run_id = 'a'*12
            instance.observer_sha256 = 'b'*64
            instance.provenance = {'manifest_sha256':'c'*64}
            instance.last_sequence = 0
            sample = dict(run_id=instance.run_id, generator_sha256=instance.observer_sha256,
                manifest_sha256='c'*64, sequence=1, observed_at=time.monotonic(),
                memory=1, peak=2, cpu={'usage_usec':'1'}, oom={'oom_kill':'0'},
                processes=[dict(pid=42, ppid=1, argv=['python'], rss=1, threads=1)])
            with tempfile.TemporaryDirectory() as folder:
                instance.out = Path(folder)
                path = instance.out / 'metrics.json'
                path.write_text(json.dumps(sample))
                self.assertEqual(instance.metrics(), sample)
                with self.assertRaises(RuntimeError):
                    instance.metrics()  # Replayed sequence, even if still recent.
                for fields in ({'generator_sha256':'f'*64}, {'manifest_sha256':'f'*64},
                               {'run_id':'f'*12}, {'memory':True}, {'peak':False},
                               {'cpu':{}}, {'oom':{'oom_kill':False}}, {'processes':[]},
                               {'observed_at':float('nan')}, {'observed_at':time.monotonic()-5}):
                    instance.last_sequence = 0
                    path.write_text(json.dumps(dict(sample, **fields)))
                    with self.subTest(fields=fields), self.assertRaises((RuntimeError, ValueError, KeyError)):
                        instance.metrics()
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    instance.metrics()
        finally:
            del sys.path[:2]

    def test_capacity_consumer_never_accepts_empty_failed_or_foreign_results(self):
        sys.path[:0] = [str(HERE), str(HERE.parent / 'worker_rehearsal')]
        try:
            driver = module('driver')
            expected = dict(run_id='a'*12, manifest_sha256='b'*64,
                observer_sha256='c'*64, driver_sha256='d'*64,
                cohort=dict(run_id='a'*12, case='capacity'))
            upload = dict(upload_available=False, upload_status=503)
            for result in (None, False, {}, {'verdict':'FAIL'},
                           {'samples':[dict(run_id='f'*12,generator_sha256='c'*64,manifest_sha256='b'*64)]}):
                with self.subTest(result=result), self.assertRaises((RuntimeError, ValueError, KeyError)):
                    driver.qualified_capacity(result, upload, **expected)
            for invalid in (None, {}, dict(upload_available=0,upload_status=503),
                            dict(upload_available=False,upload_status=True)):
                with self.assertRaises((RuntimeError, ValueError, KeyError)):
                    driver.qualified_capacity({}, invalid, **expected)
        finally:
            del sys.path[:2]

    def test_prepared_plan_and_actual_schedule_readback_must_match(self):
        from datetime import datetime, timezone, timedelta
        from uuid import UUID
        sys.path[:0] = [str(HERE), str(HERE.parent / 'worker_rehearsal')]
        try:
            driver = module('driver')
            plan = [dict(target_id=str(UUID(int=i+1)),delay=delay)
                for i,delay in enumerate((0,0,0,25,50,75,100,125,150))]
            anchor = datetime(2026,10,20,tzinfo=timezone.utc)
            result = dict(count=9,anchor=anchor.isoformat(),rows=[dict(id=row['target_id'],
                next_action_at=(anchor+timedelta(seconds=row['delay'])).isoformat()) for row in plan])
            driver.validate_plan(plan)
            driver.validate_scheduled(plan,result,anchor.timestamp()-1,anchor.timestamp()+1)
            targets = [dict(id=row['id'],state='published',published_at=row['next_action_at'])
                       for row in result['rows']]
            driver.validate_target_cohort(plan,targets,plan[0]['target_id'],result)
            with self.assertRaises(RuntimeError):
                driver.validate_target_cohort(plan,targets+[targets[0]],plan[0]['target_id'],result)
            early = [dict(row) for row in targets]
            early[-1]['published_at'] = anchor.isoformat()
            with self.assertRaises(RuntimeError):
                driver.validate_target_cohort(plan,early,plan[0]['target_id'],result)
            sql = driver.schedule_sql(plan)
            self.assertIn("t.state='queued'",sql)
            self.assertIn('MATERIALIZED',sql)
            for broken in (None,[],plan[:-1],[dict(row,delay=True) for row in plan],
                           [plan[0]]*9,[dict(row,target_id="x'); DROP DATABASE p;--") for row in plan]):
                with self.assertRaises((RuntimeError,ValueError,TypeError)):
                    driver.schedule_sql(broken)
            for changed in (dict(count=True),dict(rows=result['rows'][:-1]),dict(rows=[result['rows'][0]]*9),
                            dict(anchor='2026-10-20'), dict(anchor=(anchor+timedelta(seconds=5)).isoformat()),
                            dict(rows=[dict(row,next_action_at=anchor.isoformat()) for row in result['rows']])):
                with self.subTest(changed=changed), self.assertRaises((RuntimeError,ValueError,TypeError)):
                    driver.validate_scheduled(plan,dict(result,**changed),anchor.timestamp()-1,anchor.timestamp()+1)
        finally:
            del sys.path[:2]

    def test_outside_driver_boundary_never_signals_pid_one(self):
        sys.path[:0] = [str(HERE), str(HERE.parent / 'worker_rehearsal')]
        try:
            driver = module('driver')
            with patch.object(driver,'post_exec',side_effect=RuntimeError('OUTSIDE')), \
                    patch.object(driver.os,'kill') as kill:
                with self.assertRaisesRegex(RuntimeError,'OUTSIDE'):
                    driver.main()
                kill.assert_not_called()
        finally:
            del sys.path[:2]

    def test_lean_endpoint_preserves_protocol_and_requires_prepared_image(self):
        import ast
        source = HERE.parent / 'worker_rehearsal' / 'endpoints.py'
        original = ast.parse(source.read_text())
        current = ast.parse((HERE / 'endpoint.py').read_text())
        endpoint_class = lambda tree: next(node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == 'Endpoint')
        self.assertEqual(ast.dump(endpoint_class(original)), ast.dump(endpoint_class(current)))
        endpoint = module('endpoint')
        for data in (b'', b'x' * (1024 * 1024 - 1), b'x' * (11 * 1024 * 1024 + 1)):
            endpoint.image.cache_clear()
            with patch.object(Path, 'read_bytes', return_value=data), self.assertRaises(RuntimeError):
                endpoint.image()
        endpoint.image.cache_clear()
        with patch.object(Path, 'read_bytes', return_value=b'x' * (1024 * 1024)) as read:
            self.assertEqual(len(endpoint.image()), 1024 * 1024)
            endpoint.image()
            read.assert_called_once()

    def test_endpoint_preparation_refuses_noncanonical_bind(self):
        from unittest.mock import mock_open
        fake = SimpleNamespace(Endpoint=object(), image=lambda:b'inert')
        with patch.dict(sys.modules, {'endpoints':fake}):
            prep = module('prepare_endpoint')
        for address in (('127.0.0.4',443.0), ['127.0.0.4',443], ('127.0.0.4',True),
                        ('0.0.0.0',443), ('127.0.0.4',8443)):
            with patch.object(Path,'open',mock_open()) as opened, self.assertRaises(RuntimeError):
                prep.prepared(address,fake.Endpoint)
            opened.assert_not_called()

    def test_serial_build_install_requires_exact_complete_lock_and_success(self):
        import subprocess
        installer = module('install_locked')
        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder)/'requirements.lock'
            for text in ('', '# empty\n', 'a>=1', '-r other.txt', 'https://example.test/a.whl',
                         'a==1\na==1', 'Some_Name==1\nsome-name==2', 'a==1; echo bad',
                         'a==1\nbad==1!!2', 'a==1\nbad==1+', 'a==1\nbad==1..2', 'a==1\nbad-==1'):
                lock.write_text(text)
                with patch.object(installer.subprocess,'run') as run, self.assertRaises(ValueError):
                    installer.install(lock)
                run.assert_not_called()
            lock.write_text('a==1\nb==2\n')
            with patch.object(installer.subprocess,'run') as run, \
                    patch.object(installer.importlib.metadata,'version',side_effect=['1','2']):
                installer.install(lock)
                self.assertEqual(run.call_count,3)
                self.assertEqual([c.args[0][-1] for c in run.call_args_list],['a==1','b==2','check'])
                self.assertTrue(all(c.kwargs['check'] is True
                    and c.kwargs['env'] == dict(PATH='/usr/local/bin:/usr/bin:/bin',HOME='/tmp',
                        LC_ALL='C.UTF-8',PIP_CONFIG_FILE='/dev/null') for c in run.call_args_list))
                self.assertIn('--no-deps',run.call_args_list[0].args[0])
            with patch.object(installer.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'pip')) as run, \
                    self.assertRaises(subprocess.CalledProcessError):
                installer.install(lock)
            self.assertEqual(run.call_count,1)
            with patch.object(installer.subprocess,'run') as run, \
                    patch.object(installer.importlib.metadata,'version',return_value='wrong'), \
                    self.assertRaises(RuntimeError):
                installer.install(lock)
            self.assertEqual(run.call_count,1)



if __name__ == '__main__':
    unittest.main()
