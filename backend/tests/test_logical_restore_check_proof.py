"""Known legacy spellings, real PG17 reparse/rollback, and full verifier wiring.

The before-image models legacy deparse text; a fresh PG17 server cannot recreate
the older stored parse tree. The witness, archive extraction, collector and DDL
rollback below really execute. This fixture is not a production capture.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import verify_logical_pg_restore as logical
import logical_restore_check_proof as proof
import logical_restore_check_grammar as grammar

DOMAIN = "CHECK (((domain)::text = ANY ((ARRAY['audits'::character varying, 'fiscal_summary'::character varying, 'counties_budget'::character varying, 'population'::character varying, 'cra'::character varying, 'opendata'::character varying])::text[])))"
SUBJECT = "CHECK (((((length((app_id)::text) >= 1) AND (length((app_id)::text) <= 64)) AND (length((subject_digest)::text) = 64)) AND ((length((digest_version)::text) >= 1) AND (length((digest_version)::text) <= 32))))"


class GrammarTests(unittest.TestCase):
    def test_exact_source_predicates_and_hostile_variants(self):
        for identity, source in [(('public', 'etl_dispatch_domains', 'ck_etl_dispatch_domain'), DOMAIN),
                                 (('public', 'social_privacy_ownership', 'ck_social_privacy_subject'), SUBJECT)]:
            self.assertTrue(grammar.validate(identity, source))
            for changed in (None, '', source + '; SELECT 1', source.replace('::text', '::evil'),
                            source.replace('length(', 'evil(') if 'length(' in source else source.replace('audits', 'evil'),
                            source.replace('64', '65') if '64' in source else source.replace('cra', 'other')):
                with self.subTest(identity=identity, changed=changed), self.assertRaises(grammar.Refusal):
                    grammar.validate(identity, changed)

    def test_metadata_json_uses_strict_lf_framing(self):
        self.assertEqual(proof.one('{"x":"a\u2028b"}\n'.encode()), {'x': 'a\u2028b'})
        for raw in (b'', b'\xff', b'{}\n\n', b'{}\n{}\n', b'{'):
            with self.subTest(raw=raw), self.assertRaises((logical.Refusal, ValueError)):
                proof.one(raw)


class RealCheckProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = 'round20_s1_actual_restore_' + uuid.uuid4().hex[:12]
        cls.created = False
        try:
            script = ('mkdir -p /var/lib/postgresql/data; chown postgres:postgres /var/lib/postgresql/data; '
                      'su postgres -c "initdb -D /var/lib/postgresql/data -U postgres -A trust --no-locale" >/tmp/initdb.log; '
                      'exec su postgres -c "postgres -D /var/lib/postgresql/data -c listen_addresses= -c shared_preload_libraries="')
            logical.backup.run(['docker', 'run', '--pull', 'never', '-d', '--name', cls.name,
                                '--network', 'none', '--memory', '512m', '--cpus', '2',
                                '--label', 'auditgava.owned=logical_check_test',
                                '--tmpfs', '/var/lib/postgresql/data:rw,uid=100,gid=101,size=256m',
                                '--entrypoint', 'sh', logical.backup.SUPABASE_IMAGE, '-ec', script])
            cls.created = True
            deadline = time.monotonic() + 30
            while subprocess.run(['docker', 'exec', cls.name, 'pg_isready', '-U', 'postgres'],
                                 capture_output=True, timeout=3).returncode:
                if time.monotonic() > deadline:
                    raise RuntimeError('owned PG unavailable')
                time.sleep(.1)
            cls.sql("ALTER ROLE postgres SET search_path=pg_catalog,public; CREATE ROLE supabase_admin SUPERUSER LOGIN;")
            cls.sql("CREATE TABLE public.etl_dispatch_domains(domain varchar NOT NULL, CONSTRAINT ck_etl_dispatch_domain " + DOMAIN + ");"
                    "CREATE TABLE public.social_privacy_ownership(app_id varchar,subject_digest varchar,digest_version varchar,"
                    "CONSTRAINT ck_social_privacy_subject " + SUBJECT + ");"
                    "INSERT INTO public.etl_dispatch_domains VALUES ('cra');")
            cls.sql("CREATE FUNCTION public.reject_witness_ddl() RETURNS event_trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'hook must not run'; END $$;"
                    "CREATE EVENT TRIGGER reject_witness_ddl ON ddl_command_start EXECUTE FUNCTION public.reject_witness_ddl();")
            cls.archive = logical.backup.run(['docker', 'exec', cls.name, 'pg_dump', '-U', 'postgres', '-d', 'postgres', '-Fc'])
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.created:
            logical.backup.run(['docker', 'rm', '-fv', cls.name])
            cls.created = False
            if logical.backup.run(['docker', 'ps', '-aq', '--filter', 'name=^/' + cls.name + '$']).strip():
                raise RuntimeError('owned PG survived cleanup')

    @classmethod
    def sql(cls, text, role='postgres'):
        return logical.backup.run(['docker', 'exec', '-i', cls.name, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1',
                                   '-U', role, '-d', 'postgres'], input=text.encode(), timeout=120)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='logical-check-')
        self.root = Path(self.tmp.name)
        self.after, self.props, self.default, _ = logical.collect_local(self.name)
        self.before = copy.deepcopy(self.after)
        spellings = {'ck_etl_dispatch_domain': DOMAIN, 'ck_social_privacy_subject': SUBJECT}
        for row in self.before[0]['constraints']:
            if row[2] in spellings:
                row[4] = spellings[row[2]]
        self.plan = {'version': 1, 'constraints': []}
        for identity in sorted(proof.SCOPES):
            source = next(r for r in self.before[0]['constraints'] if tuple(r[:3]) == identity)
            target = next(r for r in self.after[0]['constraints'] if tuple(r[:3]) == identity)
            self.assertNotEqual(source[4], target[4])
            self.plan['constraints'].append(dict(zip(('schema', 'table', 'name'), identity),
                source_definition_sha256=proof.text_sha(source[4]), target_definition_sha256=proof.text_sha(target[4]),
                column_context_sha256=proof.text_sha(proof.canonical(proof.column_context(self.before, *identity[:2])))))
        self.plan_path = self.root / 'plan.json'
        self.write(self.plan_path, self.plan)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value))
        path.chmod(0o600)

    def archive_sql(self):
        return logical.backup.run(['docker', 'exec', '-i', self.name, 'pg_restore', '--schema-only',
                                  '--section=pre-data', '--schema=public', '--table=etl_dispatch_domains',
                                  '--table=social_privacy_ownership', '--file=-'], input=self.archive)

    def collect(self):
        inventory, props, _, _ = logical.collect_local(self.name)
        return inventory, props

    def prove(self, directory='proof', collect=None):
        work = self.root / directory
        work.mkdir(mode=0o700)
        return proof.prove(self.before, self.after, self.props, self.plan_path, logical.sha(self.plan_path),
                           work, self.sql, collect or self.collect, self.archive_sql,
                           logical.backup.write_new, logical, self.default)

    def test_real_witnesses_disable_hooks_and_rollback_all_state(self):
        with self.assertRaises(logical.Refusal):
            logical.compare_logical_inventory(self.before, self.after, self.default)
        derived, receipt = self.prove()
        self.assertEqual(logical.compare_logical_inventory(derived, self.after)['status'], 'logical_inventory_equal')
        self.assertTrue(receipt['full_post_rollback_state_unchanged'])
        self.assertEqual(receipt['scope_count'], 2)
        self.assertFalse(receipt['original_constraints_changed'])
        self.assertEqual(self.collect()[0], self.after)
        self.assertIn(b'"O"', self.sql(proof.HOOK_SQL))

    def test_changed_column_scope_validation_predicate_and_plan_refuse_before_ddl(self):
        for change in ('column', 'validation', 'predicate', 'missing', 'duplicate'):
            before = copy.deepcopy(self.before)
            plan = copy.deepcopy(self.plan)
            if change == 'column':
                before[0]['columns'][0][2] = 'different'
            elif change == 'validation':
                before[0]['constraints'][0][3] = False
            elif change == 'predicate':
                r = next(r for r in before[0]['constraints'] if r[2] == 'ck_social_privacy_subject')
                r[4] = r[4].replace('64', '65')
            elif change == 'missing':
                plan['constraints'].pop()
            else:
                plan['constraints'][1] = plan['constraints'][0]
            self.write(self.plan_path, plan)
            with self.subTest(change=change), self.assertRaises(logical.Refusal):
                proof.load_plan(self.plan_path, logical.sha(self.plan_path), before, self.after)

    def test_changed_post_rollback_inventory_cannot_certify(self):
        changed = copy.deepcopy(self.after)
        next(r for r in changed if r['kind'] == 'table')['sha256'] = 'f' * 64
        with self.assertRaises(logical.Refusal):
            self.prove(collect=lambda: (changed, self.props))
        receipt = json.loads((self.root / 'proof/check_reparse_receipt.json').read_text())
        self.assertEqual(receipt['status'], 'REFUSED_EXACT_CHECK_REPARSE')
        self.assertFalse(receipt['full_post_rollback_state_unchanged'])
        self.assertEqual(self.collect()[0], self.after)

    def test_different_live_predicate_fails_actual_postgresql_proof_and_rolls_back(self):
        # The plan is coherent but the source and target predicates differ in
        # meaning. A spelling/hash match alone must never certify this target.
        changed = DOMAIN.replace("'opendata'::character varying", "'other'::character varying")
        def replace_domain(definition):
            self.sql('ALTER EVENT TRIGGER reject_witness_ddl DISABLE;')
            self.sql('ALTER TABLE public.etl_dispatch_domains DROP CONSTRAINT ck_etl_dispatch_domain;'
                     'ALTER TABLE public.etl_dispatch_domains ADD CONSTRAINT ck_etl_dispatch_domain ' + definition + ';')
            self.sql('ALTER EVENT TRIGGER reject_witness_ddl ENABLE;')
        try:
            replace_domain(changed)
            self.after, self.props, self.default, _ = logical.collect_local(self.name)
            self.before = copy.deepcopy(self.after)
            for row in self.before[0]['constraints']:
                if row[2] == 'ck_etl_dispatch_domain': row[4] = DOMAIN
                if row[2] == 'ck_social_privacy_subject': row[4] = SUBJECT
            for item in self.plan['constraints']:
                row = next(r for r in self.after[0]['constraints'] if tuple(r[:3]) == tuple(item[k] for k in ('schema', 'table', 'name')))
                item['target_definition_sha256'] = proof.text_sha(row[4])
            self.write(self.plan_path, self.plan)
            with self.assertRaises(logical.Refusal):
                self.prove()
            receipt = json.loads((self.root / 'proof/check_reparse_receipt.json').read_text())
            self.assertEqual(receipt['status'], 'REFUSED_EXACT_CHECK_REPARSE')
            self.assertTrue(receipt['full_post_rollback_state_unchanged'])
            self.assertEqual(self.collect()[0], self.after)
        finally:
            replace_domain(DOMAIN)

    def test_archive_collation_anywhere_refuses(self):
        work = self.root / 'archive'
        work.mkdir(mode=0o700)
        raw = self.archive_sql() + b"\n-- COLLATE unreviewed\n"
        with self.assertRaises(logical.Refusal):
            proof.source_archive_column_proof(lambda: raw, work, logical.backup.write_new)

    def test_replayed_witness_packets_cannot_certify_a_new_run(self):
        actual = self.sql
        previous = []
        def capture(sql, role):
            raw = actual(sql, role)
            if 'constraint_reparse_witness' in sql:
                previous.append(raw)
            return raw
        with patch.object(self, 'sql', side_effect=capture):
            self.prove(directory='first')
        self.assertEqual(len(previous), 1)
        def replay(sql, role):
            return previous[0] if 'constraint_reparse_witness' in sql else actual(sql, role)
        with patch.object(self, 'sql', side_effect=replay), self.assertRaises(logical.Refusal):
            self.prove(directory='second')
        self.assertEqual(self.collect()[0], self.after)

    def test_full_verifier_requires_explicit_hash_bound_optin(self):
        bundle = self.root / 'bundle'
        bundle.mkdir(mode=0o700)
        (bundle / 'database.dump').write_bytes(self.archive)
        (bundle / 'roles.sql').write_text('-- fixture role artifact')
        self.write(bundle / 'inventory.json', self.before)
        self.write(bundle / 'recovery_prerequisites.json', self.props)
        for path in bundle.iterdir():
            path.chmod(0o600)
        self.write(bundle / 'receipt.json', {'status': 'acquired_inputs_restore_and_completeness_pending',
            'inventory_generator_sha256': logical.sha(logical.backup.__file__),
            'generator_sha256': logical.sha(logical.acquisition.__file__),
            'artifacts': {p.name: {'sha256': logical.sha(p), 'bytes': p.stat().st_size} for p in bundle.iterdir()}})
        failed = self.root / 'failed.json'
        self.write(failed, {'status': 'FAILED_OFFLINE_RESTORE', 'backup_verified': False,
            'phase': 'strict_source_restored_comparison', 'container': self.name,
            'bundle_receipt_sha256': logical.sha(bundle / 'receipt.json'), 'archive_sha256': logical.sha(bundle / 'database.dump')})
        request = self.root / 'request.json'
        disposition = {'comparison_mode': logical.COMPARISON_MODE, 'verifier_sha256': logical.sha(logical.__file__),
            'local_target': self.name, 'bundle_receipt_sha256': logical.sha(bundle / 'receipt.json'),
            'archive_sha256': logical.sha(bundle / 'database.dump'), 'original_failed_receipt_sha256': logical.sha(failed),
            'allowed_equivalences': logical.EQUIVALENCES}
        output = self.root / 'result.json'
        self.write(request, disposition)
        with self.assertRaises(logical.Refusal):
            logical.verify_bundle(bundle, self.name, failed, output, request, logical.sha(request))
        self.assertFalse(output.exists())
        disposition['isolated_check_reparse'] = {'plan_sha256': logical.sha(self.plan_path),
            'proof_generator_sha256': logical.sha(proof.__file__), 'grammar_sha256': logical.sha(grammar.__file__)}
        self.write(request, disposition)
        result = logical.verify_bundle(bundle, self.name, failed, output, request, logical.sha(request),
                                       self.plan_path, logical.sha(self.plan_path))
        self.assertTrue(result['backup_verified'])
        self.assertTrue(result['mutations'])  # Only the explicit, rolled-back witness DDL.
        self.assertFalse(result['persistent_mutations'])
        self.assertTrue(result['isolated_check_reparse']['full_post_rollback_state_unchanged'])
        self.assertEqual(self.collect()[0], self.after)


if __name__ == '__main__':
    unittest.main()
