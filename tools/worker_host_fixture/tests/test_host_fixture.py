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
    def test_boot_writes_bounded_synthetic_database_profile_before_start(self):
        import io
        sys.path[:0] = [str(HERE), str(HERE.parent / 'worker_rehearsal')]
        try:
            boot = module('boot')
            contents, commands = [], []
            class Config(io.StringIO):
                def close(self):
                    contents.append(self.getvalue())
                    super().close()
            class StopBeforeDatabaseStart(Exception):
                pass
            with tempfile.TemporaryFile() as public:
                public.write(b'public source'); public.seek(0)
                manifest = dict(files={'app/public.py':hashlib.sha256(b'public source').hexdigest()})
                def opened(path, *args, **kwargs):
                    if str(path) == '/manifest.json':
                        return io.BytesIO(json.dumps(manifest).encode())
                    if str(path) == '/state/pg/postgresql.conf':
                        self.assertEqual(args, ('a',))
                        return Config()
                    self.assertEqual(str(path), '/app/public.py')
                    return public
                def called(argv, **kwargs):
                    commands.append(argv)
                    if argv[0].endswith('/pg_ctl'):
                        raise StopBeforeDatabaseStart()
                with patch.object(boot.os,'getpid',return_value=1), \
                        patch.object(boot,'post_exec',return_value={}), \
                        patch.object(boot,'inert_environment'), \
                        patch.object(boot.os,'chdir'), patch.object(boot.os,'umask'), \
                        patch.object(boot.os,'posix_fadvise',create=True), \
                        patch.object(boot.os,'POSIX_FADV_DONTNEED',4,create=True), \
                        patch.object(Path,'read_text',return_value=json.dumps(manifest)), \
                        patch.object(Path,'exists',return_value=False), \
                        patch.object(Path,'open',opened), \
                        patch.dict(sys.modules,{'custody':SimpleNamespace(export=lambda *args:None)}), \
                        patch.object(boot,'call',side_effect=called), \
                        self.assertRaises(StopBeforeDatabaseStart):
                    boot.main()
            self.assertEqual(len(contents),1)
            self.assertIn("shared_buffers='2MB'\n",contents[0])
            self.assertIn("work_mem='1MB'\n",contents[0])
            self.assertIn('max_connections=12\n',contents[0])
            self.assertIn('--wal-segsize=1',commands[0])
            self.assertNotIn('--no-sync',commands[0])
            self.assertEqual(commands[-1][-2:],['-w','start'])
        finally:
            del sys.path[:2]

    def test_resolver_guard_loads_fixed_config_before_helper_search_path(self):
        isolation = module('isolation')
        config = module('host_config')
        library = '/usr/lib/x86_64-linux-gnu/libnss_wrapper.so'
        hosts = config.HOSTS.encode()
        manifest = dict(confinement='landlock-seccomp-v1',
            hosts_sha256=hashlib.sha256(hosts).hexdigest(),
            resolver=dict(path=library, sha256=hashlib.sha256(b'library').hexdigest()))
        def fixed_config(path):
            self.assertEqual(path, '/host/host_config.py')
            return dict(HOSTS=config.HOSTS, resolver_library=lambda: library)
        def resolve(name, *args):
            address = ('127.0.0.2' if name == 'b15-worker-db' else
                       '127.0.0.3' if name == 'b15-worker-wire' else
                       '127.0.0.1' if name == 'b15-worker-api' else '127.0.0.4')
            return [(None, None, None, None, (address, 443))]
        with patch.dict(os.environ, dict(B29_SANDBOX='landlock-seccomp-v1',
                LD_PRELOAD=library, NSS_WRAPPER_HOSTS='/etc/b29-hosts'), clear=True), \
                patch.dict(sys.modules, {'host_config':None}), \
                patch('runpy.run_path', side_effect=fixed_config) as load, \
                patch.object(Path, 'read_text', return_value=json.dumps(manifest)), \
                patch.object(Path, 'stat', return_value=SimpleNamespace(st_mode=0o100444, st_uid=65534)), \
                patch.object(Path, 'read_bytes', side_effect=lambda: None) as read, \
                patch.object(isolation.socket, 'getaddrinfo', side_effect=resolve):
            read.side_effect = [hosts, b'library']
            self.assertTrue(isolation.resolver_boundary())
            load.assert_called_once_with('/host/host_config.py')

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

    def test_syscall_policy_executes_architecture_socket_and_namespace_rules(self):
        policy=module('confinement')
        def evaluate(machine,nr,args=(),architecture=None):
            arch,sock,pair,denied=policy.syscall_numbers(machine)
            words={0:nr,4:arch if architecture is None else architecture}
            words.update({16+i*8:v for i,v in enumerate(args)})
            rows=policy.instructions(machine);pc=0;acc=0
            for _ in range(300):
                op,jt,jf,k=rows[pc]
                if op==0x20:acc=words.get(k,0);pc+=1
                elif op==0x15:pc+=1+(jt if acc==k else jf)
                elif op==0x45:pc+=1+(jt if acc&k else jf)
                elif op==0x54:acc &= k;pc+=1
                elif op==0x06:return k
                else:raise AssertionError('Unknown BPF')
            raise AssertionError('Unterminated filter')
        for machine in ('x86_64','aarch64'):
            arch,sock,pair,denied=policy.syscall_numbers(machine)
            for nr in denied:
                self.assertEqual(evaluate(machine,nr),0x50001)
            for nr in (428,429,430,431,432,433,442):
                self.assertEqual(evaluate(machine,nr),0x50001)
            for family in (0,1,16,17,40):
                self.assertEqual(evaluate(machine,sock,(family,1,0)),0x50001)
            for family in (2,10):
                self.assertEqual(evaluate(machine,sock,(family,1,0)),0x7fff0000)
            for args in ((1,1,0),(1,1|0x80000|0x800,0)):
                self.assertEqual(evaluate(machine,pair,args),0x7fff0000)
            for args in ((1,2,0),(1,3,0),(2,1,0),(1,1,1),(1,1|0x10000,0)):
                self.assertEqual(evaluate(machine,pair,args),0x50001)
            clone=56 if machine=='x86_64' else 220
            self.assertEqual(evaluate(machine,clone,(0x10000,)),0x7fff0000)
            for flag in (0x80,0x20000,0x2000000,0x4000000,0x8000000,0x10000000,0x20000000,0x40000000):
                self.assertEqual(evaluate(machine,clone,(flag,)),0x50001)
            self.assertEqual(evaluate(machine,435),0x50000|38)
            self.assertEqual(evaluate(machine,0,architecture=0),0x80000000)
        self.assertEqual(evaluate('x86_64',0x40000000|41,(1,1,0)),0x50001)
        with self.assertRaises(RuntimeError):policy.instructions('unknown')

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

    def test_only_exact_readonly_public_resolver_descriptor_is_admitted(self):
        import stat
        isolation=module('isolation')
        valid=dict(st_mode=stat.S_IFREG|0o644,st_uid=65534,st_nlink=1,st_dev=7,st_ino=9)
        for change,flags in (({},os.O_RDONLY),({'st_ino':8},os.O_RDONLY),
                             ({'st_uid':10001},os.O_RDONLY),({'st_nlink':2},os.O_RDONLY),
                             ({'st_mode':stat.S_IFLNK|0o777},os.O_RDONLY),
                             ({'st_mode':stat.S_IFREG|0o666},os.O_RDONLY),
                             ({},os.O_RDWR),({},getattr(os,'O_PATH',0x200000))):
            with patch.object(isolation.os,'fstat',return_value=SimpleNamespace(**(valid|change))), \
                    patch.object(isolation.os,'stat',return_value=SimpleNamespace(**valid)), \
                    patch.object(isolation.fcntl,'fcntl',return_value=flags):
                self.assertIs(isolation.resolver_descriptor(3),not change and flags==os.O_RDONLY)
        for fd in (True,None,-1,0,2,512):
            with self.assertRaises(RuntimeError):isolation.resolver_descriptor(fd)

    def test_landlock_fixed_leaves_never_admit_directory_subtrees(self):
        import stat
        policy=module('confinement')
        for malformed in (None,'/etc/passwd','/dev/null'):
            closed=[]
            def observed(path,**kwargs):
                mode=stat.S_IFDIR if path in policy.DIRECTORIES+policy.WRITABLE else stat.S_IFREG
                if path=='/dev/null':mode=stat.S_IFCHR
                if path==malformed:mode=stat.S_IFDIR
                return SimpleNamespace(st_mode=mode,st_rdev=os.makedev(1,3))
            def syscall(n,*args):
                return (4 if args[0] is None else 7) if n==444 else 0
            fake=SimpleNamespace(stat=observed,open=lambda *a:9,close=closed.append,
                O_PATH=0,O_CLOEXEC=0,O_NOFOLLOW=0,makedev=os.makedev)
            with patch.object(policy,'os',fake),patch.object(policy,'LIBC',SimpleNamespace(syscall=syscall)), \
                    patch.object(policy,'platform',SimpleNamespace(machine=lambda:'x86_64')):
                if malformed is None:self.assertEqual(policy.restrict_filesystem(),4)
                else:
                    with self.assertRaisesRegex(RuntimeError,'leaf type'):
                        policy.restrict_filesystem()
            self.assertIn(7,closed)

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
            with patch.dict(os.environ, {'DATABASE_URL':'production-not-admitted', 'SECRET_KEY':'private'}, clear=True), \
                    patch.object(config.platform,'machine',return_value='x86_64'):
                values = config.environment('0'*12)
            inert_environment(values)
            for key in ('B29_SANDBOX','LD_PRELOAD','NSS_WRAPPER_HOSTS'):
                bad=dict(values);bad.pop(key)
                with self.assertRaises(ValueError):inert_environment(bad)
                bad=dict(values);bad[key]='unexpected'
                with self.assertRaises(ValueError):inert_environment(bad)
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

    def test_failed_assessment_exports_unassessed_raw_data_and_still_refuses(self):
        from uuid import UUID
        sys.path[:0] = [str(HERE), str(HERE.parent / 'worker_rehearsal')]
        try:
            driver = module('driver')
            instance = driver.HostRehearsal.__new__(driver.HostRehearsal)
            instance.plan = [dict(target_id=str(UUID(int=i+1)), delay=delay)
                for i, delay in enumerate((0,0,0,25,50,75,100,125,150))]
            instance.provenance = dict(run_id='a'*12)
            instance.duration = 0
            instance.endpoint = 'endpoint'
            baseline = dict(social_post_targets=[dict(id=p['target_id'],state='queued')
                for p in instance.plan], statements=[])
            instance.snapshot = lambda *a, **kw: baseline
            instance.wire = lambda: {}
            instance.api = lambda *a, **kw: dict(latency=.01, started=100., wall_started=time.time())
            instance.metrics = lambda: dict(memory=1)
            instance.sql = lambda _: {}
            instance.logs = lambda _: ''
            with tempfile.TemporaryDirectory() as folder:
                instance.out = Path(folder)
                with patch.object(driver,'validate_scheduled'), patch.object(driver,'export') as export:
                    with self.assertRaisesRegex(ValueError,'Insufficient cgroup samples'):
                        instance.capacity('b15_worker_capacity')
                    raw = (instance.out / 'capacity-observations.json').read_bytes()
                    self.assertEqual(json.loads(raw)['verdict'], 'UNASSESSED')
                    export.assert_called_once_with('capacity_failed', raw)
                    self.assertFalse((instance.out / 'host-capacity.json').exists())
        finally:
            del sys.path[:2]

    def test_resident_api_probe_keeps_real_http_bounds_without_child_process(self):
        import io
        import http.client
        sys.path[:0] = [str(HERE), str(HERE.parent / 'worker_rehearsal')]
        try:
            driver = module('driver')
            instance = driver.HostRehearsal.__new__(driver.HostRehearsal)
            instance.cmd = lambda *a, **kw: self.fail('Per-request process must not run')
            instance.network, instance.image = 'private-loopback', 'inert-fixed'
            class Response(io.BytesIO):
                status = 200
            with patch('urllib.request.urlopen', return_value=Response(b'actual-body')) as request:
                value = instance.api('/api/v1/counties', timings=True)
                request.assert_called_once_with('http://b15-worker-api:33501/api/v1/counties', timeout=3)
                self.assertGreater(value['wall_started'], 0)
                self.assertEqual(value['latency'], value['completed']-value['started'])
            for content, status in ((b'',200),(b'x',503),(b'x'*(2*1024**2+1),200)):
                response = Response(content); response.status = status
                with patch('urllib.request.urlopen',return_value=response), self.assertRaises(RuntimeError):
                    instance.api('/health/ready')
            for route in ('https://foreign.invalid','/unknown','//foreign.invalid',None,True):
                with self.assertRaises(RuntimeError):
                    instance.api(route)
            for error in (TimeoutError(), http.client.BadStatusLine('malformed inert status')):
                with patch('urllib.request.urlopen', side_effect=error), self.assertRaises(RuntimeError) as raised:
                    instance.api('/health/live')
                self.assertIs(raised.exception.__cause__, error)
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

    def test_endpoint_image_buffer_is_not_retained_between_requests(self):
        import gc
        import tracemalloc
        endpoint = module('endpoint')
        with patch.object(Path, 'read_bytes', side_effect=lambda:b'x'*(2*1024**2)):
            tracemalloc.start()
            try:
                value = endpoint.image()
                self.assertEqual(len(value), 2*1024**2)
                del value
                gc.collect()
                self.assertLess(tracemalloc.get_traced_memory()[0], 512*1024)
            finally:
                tracemalloc.stop()

    def test_endpoint_drains_ignored_multipart_with_bounded_reads_and_refuses_eof(self):
        import contextlib
        import io
        endpoint = module('endpoint')
        class Input:
            def __init__(self, size): self.remaining=size
            def read(self, size):
                self_check.assertLessEqual(size, 65536)
                count=min(size,self.remaining)
                self.remaining-=count
                return b'x'*count
        self_check=self
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'endpoint-case').write_text('capacity')
            (root/'endpoint-delay').write_text('0')
            for available in (1024**2,1024**2-1):
                handler=endpoint.Endpoint.__new__(endpoint.Endpoint)
                handler.command,handler.path='POST','/v26.0/901/photos'
                handler.headers={'Content-Length':str(1024**2),'Content-Type':'multipart/form-data','Host':'graph.facebook.com'}
                handler.rfile,handler.wfile=Input(available),io.BytesIO()
                statuses=[]
                handler.send_response=statuses.append
                handler.send_header=lambda *a:None
                handler.end_headers=lambda:None
                output=io.StringIO()
                with patch.object(endpoint,'ROOT',root), patch.dict(os.environ,{'B15_ENDPOINT_RUN_ID':'a'*12}),contextlib.redirect_stdout(output):
                    if available==1024**2:
                        handler.respond()
                        self.assertEqual(statuses,[200])
                        self.assertEqual(json.loads(handler.wfile.getvalue()),{'id':'401'})
                        events=[json.loads(line) for line in output.getvalue().splitlines()]
                        self.assertEqual(events[0]['input_bytes'],1024**2)
                        self.assertEqual(events[0]['request_id'],events[1]['request_id'])
                    else:
                        with self.assertRaises(RuntimeError): handler.respond()
                        self.assertEqual(statuses,[])
                        self.assertEqual(output.getvalue(),'')
                    self.assertEqual(handler.rfile.remaining,0)

    def test_endpoint_requires_bounded_prepared_image(self):
        endpoint = module('endpoint')
        for data in (b'', b'x' * (1024 * 1024 - 1), b'x' * (11 * 1024 * 1024 + 1)):
            with patch.object(Path, 'read_bytes', return_value=data), self.assertRaises(RuntimeError):
                endpoint.image()
        with patch.object(Path, 'read_bytes', return_value=b'x' * (1024 * 1024)) as read:
            self.assertEqual(len(endpoint.image()), 1024 * 1024)
            endpoint.image()
            self.assertEqual(read.call_count, 2)

    def test_storage_response_streams_exact_prepared_bytes_without_whole_image_buffer(self):
        import contextlib
        import io
        endpoint = module('endpoint')
        content=b'x'*(2*1024**2)
        class Sink(io.BytesIO):
            def write(self, data):
                self_check.assertLessEqual(len(data),16384)
                return super().write(data)
        self_check=self
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'endpoint-image.jpg').write_bytes(content)
            (root/'endpoint-case').write_text('capacity')
            (root/'endpoint-delay').write_text('0')
            for head in (False,True):
                handler=endpoint.Endpoint.__new__(endpoint.Endpoint)
                handler.command,handler.path=('HEAD' if head else 'GET'),'/media/fixture.jpg'
                handler.headers={'Content-Length':'0','Host':endpoint.R2}
                handler.rfile,handler.wfile=io.BytesIO(),Sink()
                statuses=[];headers={}
                handler.send_response=statuses.append
                handler.send_header=lambda k,v:headers.update({k:v})
                handler.end_headers=lambda:None
                output=io.StringIO()
                with patch.object(endpoint,'ROOT',root),patch.dict(os.environ,{'B15_ENDPOINT_RUN_ID':'a'*12}), \
                        patch.object(Path,'read_bytes',side_effect=AssertionError('Whole image buffer')),contextlib.redirect_stdout(output):
                    handler.respond(head=head)
                self.assertEqual(statuses,[200])
                self.assertEqual(headers['Content-Length'],str(len(content)))
                self.assertEqual(headers['ETag'],'"'+hashlib.md5(content).hexdigest()+'"')
                self.assertEqual(headers['x-amz-meta-sha256'],hashlib.sha256(content).hexdigest())
                self.assertEqual(handler.wfile.getvalue(),b'' if head else content)
                events=[json.loads(line) for line in output.getvalue().splitlines()]
                self.assertEqual(events[-1]['output_bytes'],0 if head else len(content))
            with patch.object(endpoint,'ROOT',root):
                for invalid in (1,0,None,'yes',[],{}):
                    with self.assertRaises(ValueError): endpoint.serve_image(handler,head=invalid)

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
