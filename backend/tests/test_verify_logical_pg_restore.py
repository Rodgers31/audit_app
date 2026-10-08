"""Explicit logical comparison: focused boundaries and an owned PG17.6 restore."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_logical_pg_restore as logical

spec = importlib.util.spec_from_file_location('backup_test_fixtures', Path(__file__).with_name('test_bounded_pg_backup.py'))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
spec = importlib.util.spec_from_file_location('acquisition_test_fixtures', Path(__file__).with_name('test_reviewed_pg_acquisition.py'))
configuration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configuration)


class LogicalBoundaryTests(unittest.TestCase):
    @staticmethod
    def inventory():
        records = fixtures.BoundaryTests.catalog_inventory()
        catalog = records[0]
        catalog['columns'].append(['public', 'fixture', 'payload', 3, 'text', False, '', '', "'x'::text", None])
        catalog['roles'].extend([['reader_a', False, True, False, False, True, False, False, -1, None, None],
                                 ['reader_b', False, True, False, False, True, False, False, -1, None, None]])
        catalog['relations'][0][4] = ['postgres=arwdDxtm/postgres', 'reader_a=r*/postgres', 'reader_b=r/postgres']
        catalog['constraints'] = [['public', 'fixture', 'fixture_pkey', True, 'PRIMARY KEY (id)']]
        return records

    def test_physical_gaps_and_acl_array_order_are_the_only_general_equivalences(self):
        source = self.inventory()
        target = copy.deepcopy(source)
        target[0]['columns'][1][3] = 2
        target[0]['relations'][0][4].reverse()
        originals = copy.deepcopy((source, target))
        with self.assertRaises(logical.Refusal):
            logical.backup.compare_inventory(source, target)
        self.assertEqual(logical.compare_logical_inventory(source, target)['tables'], 1)
        self.assertEqual((source, target), originals)

    def test_changed_meaningful_state_never_passes(self):
        source = self.inventory()
        mutations = {
            'logical_column_order': lambda r: r[0]['columns'].reverse(),
            'column_name': lambda r: r[0]['columns'][1].__setitem__(2, 'different'),
            'type': lambda r: r[0]['columns'][1].__setitem__(4, 'integer'),
            'default': lambda r: r[0]['columns'][1].__setitem__(8, "'y'::text"),
            'generated': lambda r: r[0]['columns'][1].__setitem__(7, 's'),
            'notnull': lambda r: r[0]['columns'][1].__setitem__(5, True),
            'missing_grant': lambda r: r[0]['relations'][0][4].pop(),
            'grantee': lambda r: r[0]['relations'][0][4].__setitem__(1, 'reader_b=r*/postgres'),
            'grantor': lambda r: r[0]['relations'][0][4].__setitem__(1, 'reader_a=r*/reader_b'),
            'grant_option': lambda r: r[0]['relations'][0][4].__setitem__(1, 'reader_a=r/postgres'),
            'privilege': lambda r: r[0]['relations'][0][4].__setitem__(1, 'reader_a=w*/postgres'),
            'missing_table': lambda r: r.pop(),
            'changed_row': lambda r: r[1].__setitem__('sha256', 'a' * 64),
            'count_bool': lambda r: r[1].__setitem__('count', False),
            'rls': lambda r: r[0]['relations'][0].__setitem__(5, True),
            'constraint': lambda r: r[0]['constraints'][0].__setitem__(4, 'PRIMARY KEY (payload)'),
            'numeric_bool_difference': lambda r: r[0]['columns'][1].__setitem__(5, 0),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                target = copy.deepcopy(source)
                mutate(target)
                with self.assertRaises((logical.Refusal, ValueError)):
                    logical.compare_logical_inventory(source, target)

    def test_active_column_reorder_with_valid_ascending_physical_numbers_fails(self):
        source = self.inventory()
        target = copy.deepcopy(source)
        target[0]['columns'].reverse()
        for ordinal, row in enumerate(target[0]['columns'], 1):
            row[3] = ordinal
        with self.assertRaises(logical.Refusal):
            logical.compare_logical_inventory(source, target)

    def test_bad_physical_numbers_fail_even_on_identical_inputs(self):
        for number in (None, True, False, 0, -1, 1.0, float('nan'), float('inf'), '1', 32768):
            records = self.inventory()
            records[0]['columns'][0][3] = number
            with self.subTest(number=number), self.assertRaises((logical.Refusal, ValueError)):
                logical.compare_logical_inventory(records, records)
        records = self.inventory()
        records[0]['columns'][1][3] = 1
        with self.assertRaises(logical.Refusal):
            logical.compare_logical_inventory(records, records)

    def test_acl_invalid_and_duplicate_items_fail_even_on_identical_inputs(self):
        for acl in ([None], ['garbage'], ['reader_a=r**/postgres'], ['reader_a=rr/postgres'],
                    ['reader_a=r/postgres', 'reader_a=w/postgres'], ['reader_a=r/postgres'] * 2):
            records = self.inventory()
            records[0]['relations'][0][4] = acl
            with self.subTest(acl=acl), self.assertRaises(logical.Refusal):
                logical.compare_logical_inventory(records, records)

    def test_invalid_column_relation_and_unknown_acl_role_fail_identically(self):
        changes = [('columns', 4, None), ('columns', 5, 0), ('columns', 6, None),
                   ('columns', 7, 'unknown'), ('columns', 8, False),
                   ('relations', 2, 'unknown'), ('relations', 3, 'missing_owner'),
                   ('relations', 5, 0), ('relations', 6, None),
                   ('relations', 7, [None]), ('relations', 4, ['missing_role=r/postgres'])]
        for key, index, value in changes:
            records = self.inventory()
            records[0][key][0][index] = value
            with self.subTest(key=key,index=index), self.assertRaises(logical.Refusal):
                logical.compare_logical_inventory(records,records)

    def test_identical_malformed_catalog_regressions_fail_after_healthy_baseline(self):
        changes = {
            'role_flag_integer': lambda r:r[0]['roles'][0].__setitem__(1,1),
            'role_flag_null': lambda r:r[0]['roles'][0].__setitem__(1,None),
            'role_limit_boolean': lambda r:r[0]['roles'][0].__setitem__(8,False),
            'role_invalid_settings': lambda r:r[0]['roles'][0].__setitem__(10,['missing_equals']),
            'constraint_boolean_integer': lambda r:r[0]['constraints'][0].__setitem__(3,1),
            'constraint_definition_missing': lambda r:r[0]['constraints'][0].__setitem__(4,None),
            'schema_owner_missing': lambda r:r[0]['schemas'][0].__setitem__(1,None),
            'extension_owner_missing': lambda r:r[0]['extensions'][0].__setitem__(3,None),
            'extension_version_missing': lambda r:r[0]['extensions'][0].__setitem__(1,None),
            'extension_flag_integer': lambda r:r[0]['extensions'][0].__setitem__(4,0),
            'routine_definition_missing': lambda r:r[0].__setitem__('routines',[['public','bad','','postgres',None,None,None]]),
            'policy_behavior_missing': lambda r:r[0].__setitem__('policies',[['public','fixture','bad',None,None,None,None,None]]),
            'empty_quoted_acl_grantee': lambda r:r[0]['relations'][0].__setitem__(4,['""=r/postgres']),
            'sequence_orphan_boolean': lambda r:r[0].__setitem__('sequence_definitions',[['public','missing','bigint',True,True,True,True,True,False]]),
        }
        for name,change in changes.items():
            source = self.inventory()
            self.assertEqual(logical.compare_logical_inventory(source,copy.deepcopy(source))['status'],'logical_inventory_equal')
            change(source)
            with self.subTest(case=name), self.assertRaises(logical.Refusal):
                logical.compare_logical_inventory(source,copy.deepcopy(source))

    def test_acl_item_strings_preserve_grant_options_and_quoted_identifiers(self):
        value = ['"role/with=delimiter"=r*/"grant""or"', '=X/postgres']
        self.assertEqual(logical.canonical_acl(value), sorted(value))

    @staticmethod
    def default_inventory():
        records = LogicalBoundaryTests.inventory()
        c = records[0]
        c['schemas'].append(['realtime', 'supabase_admin', None])
        c['roles'].append(['supabase_admin', False, True, False, False, True, False, False, -1, None, None])
        c['relations'].append(['realtime', 'schema_migrations', 'r', 'supabase_admin', logical.DEFAULT_ACL.copy(), False, False, None])
        c['columns'].append(['realtime', 'schema_migrations', 'version', 1, 'integer', False, '', '', None, None])
        c['types'].append(['realtime', 'schema_migrations', 'c', 'supabase_admin', None, None, False, None, 'realtime.schema_migrations', None])
        records.append(dict(kind='table', schema='realtime', name='schema_migrations', count=0, sha256='0' * 64))
        proof = {'kind':'reviewed_relation_default_acl', 'schema':'realtime', 'name':'schema_migrations',
                 'owner':'supabase_admin', 'relkind':'r', 'actual_acl':None, 'default_acl':logical.DEFAULT_ACL.copy()}
        return records, proof

    def test_sole_default_exception_requires_exact_target_readback(self):
        source, proof = self.default_inventory()
        target = copy.deepcopy(source)
        target[0]['relations'][-1][4] = None
        self.assertTrue(logical.compare_logical_inventory(source, target, proof)['reviewed_default_acl_equivalence_used'])
        for key in proof:
            bad = copy.deepcopy(proof)
            bad[key] = None if proof[key] is not None else []
            with self.subTest(field=key), self.assertRaises(logical.Refusal):
                logical.compare_logical_inventory(source, target, bad)
        with self.assertRaises(logical.Refusal):
            logical.compare_logical_inventory(source, target)

    def test_default_exception_cannot_hide_grant_owner_kind_or_scope_changes(self):
        source, proof = self.default_inventory()
        for index, value in ((0, 'public'), (1, 'other'), (2, 'S'), (3, 'postgres'),
                             (4, ['reader_a=r/supabase_admin'])):
            target = copy.deepcopy(source)
            target[0]['relations'][-1][4] = None
            source_changed = copy.deepcopy(source)
            source_changed[0]['relations'][-1][index] = value
            with self.subTest(field=index), self.assertRaises(logical.Refusal):
                logical.compare_logical_inventory(source_changed, target, proof)
        other = self.inventory()
        target = copy.deepcopy(other)
        target[0]['relations'][0][4] = None
        with self.assertRaises(logical.Refusal):
            logical.compare_logical_inventory(other, target, proof)

    def test_sequence_and_definition_changes_fail(self):
        source = self.inventory()
        source[0]['relations'].append(['public', 'seq', 'S', 'postgres', None, False, False, None])
        source[0]['sequence_definitions'] = [['public','seq','bigint',1,1,9223372036854775807,1,1,False]]
        source.append(dict(kind='sequence',schema='public',name='seq',last_value=42,is_called=True))
        for key, value in (('last_value', 43), ('is_called', False), ('last_value', True)):
            target = copy.deepcopy(source)
            target[-1][key] = value
            with self.subTest(key=key), self.assertRaises(logical.Refusal):
                logical.compare_logical_inventory(source, target)
        target = copy.deepcopy(source)
        target[0]['sequence_definitions'][0][4] = 2
        with self.assertRaises(logical.Refusal):
            logical.compare_logical_inventory(source, target)

    def test_missing_graphql_acl_is_never_an_equivalence(self):
        source = self.inventory()
        source[0]['schemas'].append(['graphql', 'postgres', ['postgres=UC/postgres', 'reader_a=U/postgres']])
        target = copy.deepcopy(source)
        target[0]['schemas'][-1][2] = None
        with self.assertRaises(logical.Refusal):
            logical.compare_logical_inventory(source, target)

    def test_empty_or_malformed_inputs_cannot_pass(self):
        for value in (None, {}, [], [{'kind':'catalog'}]):
            with self.subTest(value=value), self.assertRaises(logical.Refusal):
                logical.compare_logical_inventory(value, value)


class OwnedPostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = 'round20_s1_actual_restore_' + uuid.uuid4().hex[:12]
        cls.created = False
        cls.directory = tempfile.TemporaryDirectory(prefix='round20_logical_fixture_')
        try:
            script = ('mkdir -p /var/lib/postgresql/data; chown postgres:postgres /var/lib/postgresql/data; '
                      'su postgres -c "initdb -D /var/lib/postgresql/data -U postgres -A trust --no-locale" >/tmp/initdb.log; '
                      'exec su postgres -c "postgres -D /var/lib/postgresql/data -c listen_addresses= -c shared_preload_libraries="')
            logical.backup.run(['docker','run','--pull','never','-d','--name',cls.name,'--network','none',
                                '--tmpfs','/var/lib/postgresql/data:rw,uid=100,gid=101','--entrypoint','sh',
                                logical.backup.SUPABASE_IMAGE,'-ec',script])
            cls.created = True
            deadline = time.monotonic() + 30
            while True:
                probe = subprocess.run(['docker','exec',cls.name,'pg_isready','-U','postgres'],
                                       env=logical.backup.ENV,capture_output=True,timeout=3)
                if probe.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('owned PG fixture unavailable')
                time.sleep(.1)
            cls.sql('''CREATE ROLE supabase_admin LOGIN; CREATE ROLE reader_a; CREATE ROLE reader_b;
CREATE SCHEMA realtime AUTHORIZATION supabase_admin;
CREATE TABLE realtime.schema_migrations(version integer PRIMARY KEY);
ALTER TABLE realtime.schema_migrations OWNER TO supabase_admin;
GRANT ALL ON realtime.schema_migrations TO supabase_admin;
CREATE TABLE public.fixture(id integer PRIMARY KEY, dropped text, payload text DEFAULT 'x');
ALTER TABLE public.fixture DROP COLUMN dropped;
INSERT INTO public.fixture(id)VALUES(1);
ALTER TABLE public.fixture ENABLE ROW LEVEL SECURITY;
CREATE POLICY fixture_policy ON public.fixture USING(true);
GRANT SELECT ON public.fixture TO reader_a WITH GRANT OPTION;
GRANT SELECT ON public.fixture TO reader_b;
CREATE SEQUENCE public.seq START 42; SELECT nextval('public.seq');''')
            cls.before = cls.inventory()
            logical.backup.run(['docker','exec',cls.name,'pg_dump','-U','postgres','-Fc','--file=/tmp/fixture.dump','postgres'])
            cls.sql('CREATE DATABASE restored WITH TEMPLATE template0;')
            logical.backup.run(['docker','exec',cls.name,'pg_restore','--exit-on-error','--single-transaction',
                                '-U','postgres','-d','restored','/tmp/fixture.dump'])
            # Force a real ACL ordering difference without changing any item.
            cls.sql('''REVOKE ALL ON public.fixture FROM reader_a,reader_b;
GRANT SELECT ON public.fixture TO reader_b;
GRANT SELECT ON public.fixture TO reader_a WITH GRANT OPTION;''', 'restored')
            cls.after = cls.inventory('restored')
            cls.proof = json.loads(cls.sql(logical.DEFAULT_READBACK_SQL, 'restored'))
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.created:
            logical.backup.run(['docker','rm','-fv',cls.name])
            cls.created = False
        cls.directory.cleanup()

    @classmethod
    def sql(cls, query, database='postgres'):
        return logical.backup.run(['docker','exec','-i',cls.name,'psql','-XqAt','-v','ON_ERROR_STOP=1',
                                   '-U','postgres','-d',database], input=query.encode(),timeout=60)

    @classmethod
    def inventory(cls, database='postgres'):
        raw = cls.sql("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL timezone='UTC'; SET LOCAL datestyle='ISO,YMD'; SET LOCAL extra_float_digits=3;\n" + logical.backup.INVENTORY_SQL + '\nROLLBACK;', database)
        return [json.loads(line)for line in raw.decode().splitlines()]

    def test_real_owned_target_binds_publisher_image_before_readonly_inventory(self):
        records, props, proof, context = logical.collect_local(self.name)
        self.assertEqual(records, self.before)
        self.assertEqual(context['server_version'], '17.6')
        self.assertIs(context['local_socket'], True)
        self.assertEqual(proof['actual_acl'], logical.DEFAULT_ACL)
        self.assertEqual(proof['default_acl'], logical.DEFAULT_ACL)
        self.assertEqual(props['kind'], 'recovery_prerequisites')

    def test_real_logical_dump_red_strict_green_logical(self):
        self.assertEqual(self.sql("SELECT current_setting('server_version');").decode().strip(), '17.6')
        columns = lambda value: [r[3]for r in value[0]['columns']if r[:2]==['public','fixture']]
        self.assertEqual(columns(self.before), [1, 3])
        self.assertEqual(columns(self.after), [1, 2])
        relation = lambda value: next(r for r in value[0]['relations']if r[:2]==['public','fixture'])
        self.assertNotEqual(relation(self.before)[4], relation(self.after)[4])
        self.assertEqual(sorted(relation(self.before)[4]), sorted(relation(self.after)[4]))
        self.assertEqual(self.proof['actual_acl'], None)
        self.assertEqual(self.proof['default_acl'], logical.DEFAULT_ACL)
        with self.assertRaises(logical.Refusal):
            logical.backup.compare_inventory(self.before,self.after)
        verdict = logical.compare_logical_inventory(self.before,self.after,self.proof)
        self.assertTrue(verdict['reviewed_default_acl_equivalence_used'])

    def test_real_database_negative_controls_rollback_after_each(self):
        changes = {
            'row': "UPDATE public.fixture SET payload='changed' WHERE id=1;",
            'sequence': "ALTER SEQUENCE public.seq RESTART WITH 70;",
            'type': "ALTER TABLE public.fixture ALTER COLUMN payload TYPE varchar;",
            'default': "ALTER TABLE public.fixture ALTER COLUMN payload SET DEFAULT 'y';",
            'grant': "REVOKE SELECT ON public.fixture FROM reader_b;",
            'grant_option': "REVOKE GRANT OPTION FOR SELECT ON public.fixture FROM reader_a;",
            'grantee': "REVOKE SELECT ON public.fixture FROM reader_b; GRANT SELECT ON public.fixture TO supabase_admin;",
            'grantor': "REVOKE SELECT ON public.fixture FROM reader_b; SET ROLE reader_a; GRANT SELECT ON public.fixture TO reader_b; RESET ROLE;",
            'logical_column_order': "ALTER TABLE public.fixture DROP COLUMN id; ALTER TABLE public.fixture ADD COLUMN id integer; UPDATE public.fixture SET id=1; ALTER TABLE public.fixture ADD PRIMARY KEY(id);",
            'rls': "ALTER TABLE public.fixture DISABLE ROW LEVEL SECURITY;",
            'constraint': "ALTER TABLE public.fixture DROP CONSTRAINT fixture_pkey;",
            'missing_table': "DROP TABLE public.fixture;",
        }
        for name, change in changes.items():
            raw = self.sql("BEGIN; SET LOCAL timezone='UTC'; SET LOCAL datestyle='ISO,YMD'; SET LOCAL extra_float_digits=3;\n" + change + '\n' + logical.backup.INVENTORY_SQL + '\nROLLBACK;', 'restored')
            changed = [json.loads(line)for line in raw.decode().splitlines()]
            with self.subTest(name=name), self.assertRaises(logical.Refusal):
                logical.compare_logical_inventory(self.before,changed,self.proof)
        self.assertEqual(self.inventory('restored'), self.after)


class ReceiptBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='round20_logical_receipt_test_')
        self.directory = Path(self.temp.name)
        self.target = 'round20_s1_actual_restore_012345abcdef'
        self.bundle = self.directory / 'bundle'
        self.bundle.mkdir(mode=0o700)
        self.records = LogicalBoundaryTests.inventory()
        self.props = configuration.prerequisites()
        for name, data in [('database.dump', b'synthetic archive binding test'), ('roles.sql', b'-- synthetic'),
                           ('inventory.json', json.dumps(self.records).encode()),
                           ('recovery_prerequisites.json', json.dumps(self.props).encode())]:
            path = self.bundle / name
            path.write_bytes(data)
            path.chmod(0o600)
        captured = {'status':'acquired_inputs_restore_and_completeness_pending',
                    'inventory_generator_sha256':logical.sha(Path(logical.backup.__file__)),
                    'generator_sha256':logical.sha(Path(logical.acquisition.__file__)),
                    'artifacts':{p.name:{'sha256':logical.sha(p),'bytes':p.stat().st_size}for p in self.bundle.iterdir()}}
        self.write(self.bundle / 'receipt.json', captured)
        self.failed = self.directory / 'failed.json'
        self.write(self.failed, {'status':'FAILED_OFFLINE_RESTORE','backup_verified':False,
                                'phase':'strict_source_restored_comparison','container':self.target,
                                'bundle_receipt_sha256':logical.sha(self.bundle / 'receipt.json'),
                                'archive_sha256':logical.sha(self.bundle / 'database.dump')})
        self.request = self.directory / 'request.json'
        self.disposition = {'comparison_mode':logical.COMPARISON_MODE,
                            'verifier_sha256':logical.sha(Path(logical.__file__)), 'local_target':self.target,
                            'bundle_receipt_sha256':logical.sha(self.bundle / 'receipt.json'),
                            'archive_sha256':logical.sha(self.bundle / 'database.dump'),
                            'original_failed_receipt_sha256':logical.sha(self.failed),
                            'allowed_equivalences':logical.EQUIVALENCES}
        self.write(self.request, self.disposition)
        self.output = self.directory / 'result.json'

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    def verify(self, digest=None):
        return logical.verify_bundle(self.bundle, self.target, self.failed, self.output,
                                     self.request, logical.sha(self.request)if digest is None else digest)

    def test_receipt_provenance_readback_and_exclusive_publication(self):
        failure_before = self.failed.read_bytes()
        target = copy.deepcopy(self.records)
        target[0]['columns'][1][3] = 2
        with patch.object(logical, 'collect_local', return_value=(target,self.props,None,{'executor':'postgres'})):
            result = self.verify()
            with self.assertRaises(FileExistsError):
                self.verify()
        readback = json.loads(self.output.read_text())
        self.assertEqual(result,readback)
        self.assertEqual(readback['generator_sha256'],logical.sha(Path(logical.__file__)))
        self.assertEqual(readback['reviewed_request_sha256'],logical.sha(self.request))
        self.assertEqual(readback['comparison_mode'],logical.COMPARISON_MODE)
        self.assertFalse(readback['strict_physical_inventory_equal'])
        self.assertEqual(readback['allowed_equivalences'],logical.EQUIVALENCES)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.failed.read_bytes(),failure_before)

    def test_disposition_changes_refuse_before_any_target_connection(self):
        for field in self.disposition:
            changed = copy.deepcopy(self.disposition)
            changed[field] = 'unreviewed'
            self.write(self.request, changed)
            with self.subTest(field=field), patch.object(logical,'collect_local')as collect:
                with self.assertRaises(logical.Refusal):
                    self.verify()
                collect.assert_not_called()
                self.assertFalse(self.output.exists())
        self.write(self.request,self.disposition)
        with patch.object(logical,'collect_local')as collect, self.assertRaises(logical.Refusal):
            self.verify('0'*64)
        collect.assert_not_called()

    def test_artifact_tamper_and_nonprivate_requests_refuse_before_connection(self):
        with patch.object(logical,'collect_local')as collect:
            self.request.chmod(0o644)
            with self.assertRaises(logical.Refusal):self.verify()
            self.request.chmod(0o600)
            (self.bundle / 'database.dump').write_bytes(b'drift')
            with self.assertRaises(logical.Refusal):self.verify()
            collect.assert_not_called()

    def test_changed_configuration_cannot_publish_success(self):
        changed = copy.deepcopy(self.props)
        changed['database_properties']['locale'] = 'fr-FR'
        with patch.object(logical,'collect_local',return_value=(self.records,changed,None,{})):
            with self.assertRaises(logical.Refusal):self.verify()
        self.assertFalse(self.output.exists())

    def test_unowned_or_remote_target_refuses_before_docker(self):
        for name in ('production','localhost','round20_s1_actual_restore_bad',None):
            with self.subTest(name=name), patch.object(logical.backup,'run')as run:
                with self.assertRaises(logical.Refusal):logical.collect_local(name)
                run.assert_not_called()

    def test_classic_docker_config_id_binds_exact_publisher_pin(self):
        image_id = "sha256:" + "a" * 64
        state = {"Name": "/" + self.target, "HostConfig": {"NetworkMode": "none", "PortBindings": {}},
                 "State": {"Running": True}, "Image": image_id}
        image = {"Id": image_id, "RepoDigests": [logical.backup.SUPABASE_IMAGE]}
        context = {"kind": "local_execution_context", "executor": "postgres", "server_version": "17.6",
                   "local_socket": True, "search_path": "public", "database": "postgres"}
        payload = "\n".join(json.dumps(r) for r in [context, *self.records, self.props]).encode()
        with patch.object(logical.backup, "run", side_effect=[json.dumps([state]).encode(), json.dumps([image]).encode(), payload]) as run:
            self.assertEqual(logical.collect_local(self.target)[0], self.records)
            self.assertEqual(run.call_args_list[1].args[0], ["docker", "image", "inspect", logical.backup.SUPABASE_IMAGE])

    def test_image_identity_refusals_stop_before_database_execution(self):
        digest = logical.backup.SUPABASE_IMAGE.split('@')[1]
        state = {'Name': '/' + self.target, 'HostConfig': {'NetworkMode': 'none', 'PortBindings': {}},
                 'State': {'Running': True}, 'Image': digest}
        healthy = {'Id': digest, 'RepoDigests': [logical.backup.SUPABASE_IMAGE]}
        wrong_images = [[], [healthy, healthy], [None],
                        [{**healthy, 'Id': 'mutable'}], [{**healthy, 'Id': None}],
                        [{**healthy, 'Id': 'sha256:' + 'b' * 64}],
                        [{**healthy, 'RepoDigests': []}], [{**healthy, 'RepoDigests': None}],
                        [{**healthy, 'RepoDigests': logical.backup.SUPABASE_IMAGE}],
                        [{**healthy, 'RepoDigests': ['supabase/postgres@' + digest]}]]
        for images in wrong_images:
            with self.subTest(images=images), patch.object(logical.backup, 'run', side_effect=[json.dumps([state]).encode(), json.dumps(images).encode()]) as run:
                with self.assertRaises(logical.Refusal):
                    logical.collect_local(self.target)
                self.assertEqual(run.call_count, 2)

    def test_malformed_inspection_and_execution_context_cannot_certify(self):
        state = {'Name':'/'+self.target,'HostConfig':{'NetworkMode':'none','PortBindings':{}},
                 'State':{'Running':True},'Image':logical.backup.SUPABASE_IMAGE.split('@')[1]}
        image = {'Id': state['Image'], 'RepoDigests': [logical.backup.SUPABASE_IMAGE]}
        context = {'kind':'local_execution_context','executor':'postgres','server_version':'17.6',
                   'local_socket':True,'search_path':'public','database':'postgres'}
        healthy_payload = '\n'.join(json.dumps(r)for r in [context,*self.records,self.props]).encode()
        with patch.object(logical.backup,'run',side_effect=[json.dumps([state]).encode(),json.dumps([image]).encode(),healthy_payload]):
            self.assertEqual(logical.collect_local(self.target)[0],self.records)
        for running,ports in [('false',{}),({'success':False},{}),(1,{}),(True,False),(True,[])]:
            changed = copy.deepcopy(state)
            changed['State']['Running'] = running
            changed['HostConfig']['PortBindings'] = ports
            with self.subTest(running=running,ports=ports), patch.object(logical.backup,'run',side_effect=[json.dumps([changed]).encode(),healthy_payload])as run:
                with self.assertRaises(logical.Refusal):logical.collect_local(self.target)
                self.assertEqual(run.call_count,1)
        missing_path = context.copy()
        missing_path.pop('search_path')
        for ctx in (missing_path,{**context,'search_path':None},{**context,'search_path':''}):
            payload = '\n'.join(json.dumps(r)for r in [ctx,*self.records,self.props]).encode()
            with patch.object(logical.backup,'run',side_effect=[json.dumps([state]).encode(),json.dumps([image]).encode(),payload]):
                with self.assertRaises(logical.Refusal):logical.collect_local(self.target)


if __name__ == '__main__':
    unittest.main()
