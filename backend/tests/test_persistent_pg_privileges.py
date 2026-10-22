"""Retained capture evidence and actual owned PG17.6 permission readbacks.

Source evidence is a synthetic local capture, never a production assertion.
The source-producer fixture is explicitly approved by each local request.
"""
import copy
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import verify_logical_pg_restore as logical
import verify_persistent_pg_privileges as permissions
from backend.tests import test_logical_restore_check_proof as fixtures


class PersistentProfileTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RealCheckProofTests.setUpClass.__func__)
    tearDownClass = classmethod(fixtures.RealCheckProofTests.tearDownClass.__func__)
    sql = classmethod(fixtures.RealCheckProofTests.sql.__func__)
    write = staticmethod(fixtures.RealCheckProofTests.write)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='persistent-profile-')
        self.root=Path(self.tmp.name)
        self.before,self.props,self.default,_=logical.collect_local(self.name)
        self.contract,self.contract_path=permissions.load_contract()
        self.matrix=permissions.query_profile(self.name)[2]
        self.original=copy.deepcopy(self.matrix)
        # A retained unfiltered capture has a different digest when source temp
        # schema rows existed. That original observation is kept, not overwritten.
        self.original['rows'][0][4]='a'*64
        self.bundle=self.root/'bundle';self.bundle.mkdir(mode=0o700)
        (self.bundle/'database.dump').write_bytes(self.archive)
        (self.bundle/'roles.sql').write_text('-- inert acquired roles fixture')
        self.write(self.bundle/'inventory.json',self.before)
        self.write(self.bundle/'recovery_prerequisites.json',self.props)
        for p in self.bundle.iterdir():p.chmod(0o600)
        self.write(self.bundle/'receipt.json',{'status':'acquired_inputs_restore_and_completeness_pending',
            'generator_sha256':logical.sha(logical.acquisition.__file__),
            'inventory_generator_sha256':logical.sha(logical.backup.__file__),
            'artifacts':{p.name:{'sha256':logical.sha(p),'bytes':p.stat().st_size} for p in self.bundle.iterdir()}})
        self.failed=self.root/'failed.json'
        self.write(self.failed,{'status':'FAILED_OFFLINE_RESTORE','backup_verified':False,
            'phase':'strict_source_restored_comparison','container':self.name,
            'bundle_receipt_sha256':logical.sha(self.bundle/'receipt.json'),'archive_sha256':logical.sha(self.bundle/'database.dump')})
        self.logical_request=self.root/'logical_request.json'
        self.write(self.logical_request,{'comparison_mode':logical.COMPARISON_MODE,'verifier_sha256':logical.sha(logical.__file__),
            'local_target':self.name,'bundle_receipt_sha256':logical.sha(self.bundle/'receipt.json'),
            'archive_sha256':logical.sha(self.bundle/'database.dump'),'original_failed_receipt_sha256':logical.sha(self.failed),
            'allowed_equivalences':logical.EQUIVALENCES})
        self.parent=self.root/'logical.json'
        logical.verify_bundle(self.bundle,self.name,self.failed,self.parent,self.logical_request,logical.sha(self.logical_request))
        self.producer=self.root/'source_producer.py';self.producer.write_text('# explicitly approved synthetic source generator\n');self.producer.chmod(0o600)
        self.proof_path=self.root/'source_proof.json';self.original_path=self.root/'original.json'
        self.write(self.original_path,self.original)
        self.proof={'schema':1,'status':'VERIFIED_CAPTURE_BOUND_PERSISTENT_PRIVILEGES_SOURCE','profile':self.contract.PROFILE,
            'commit':'1'*40,'generator_sha256':logical.sha(self.producer),
            'catalog_sha256':self.contract.digest(self.contract.catalog_projection(self.before[0],logical)),
            'durable_prerequisites_sha256':self.contract.digest(self.contract.durable_projection(self.props,logical.acquisition)),
            'original_privileges_sha256':self.contract.digest(self.original),
            'persistent_privileges_sha256':self.contract.digest(self.matrix),'profile_contract_sha256':permissions.CONTRACT_SHA,
            'original_sql_sha256':permissions.ORIGINAL_SQL_SHA,'persistent_sql_sha256':permissions.SQL_SHA,
            'role_count':len(self.matrix['rows']),'excluded_temp_namespace_count':2,'read_only':True,'tls_verified':True,
            'publishing_disabled':True,'off_switch_count':12,'production_mutations':False,'connection_disposed':True,
            'temporary_material_removed':True,'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'elapsed_seconds':1.0}
        self.write(self.proof_path,self.proof)
        self.request=self.root/'request.json';self.output=self.root/'result.json'
        self.approve()

    def tearDown(self):self.tmp.cleanup()

    def approve(self):
        paths={'logical_receipt':self.parent,'source_proof':self.proof_path,'source_generator':self.producer,'original_privileges':self.original_path}
        parent=json.loads(self.parent.read_text())
        paths.update({name:Path(parent[name]) for name in ('reviewed_request','original_failed_receipt','restored_inventory','restored_prerequisites')})
        paths.update({'bundle/'+name:self.bundle/name for name in ('receipt.json','database.dump','roles.sql','inventory.json','recovery_prerequisites.json')})
        sources={'verifier':permissions.__file__,'logical':logical.__file__,'acquisition':logical.acquisition.__file__,
            'inventory':logical.backup.__file__,'contract':self.contract_path,
            'check_helper':Path(logical.__file__).with_name('logical_restore_check_proof.py'),
            'check_grammar':Path(logical.__file__).with_name('logical_restore_check_grammar.py'),'sql':Path(permissions.__file__).with_name('persistent_pg_privileges.sql')}
        self.write(self.request,{'version':1,'local_target':self.name,'verifier_sha256':logical.sha(permissions.__file__),
            'source_hashes':{k:logical.sha(v) for k,v in sources.items()},'input_hashes':{k:logical.sha(v) for k,v in paths.items()}})

    def verify(self):
        return permissions.verify(self.bundle,self.name,self.parent,self.proof_path,self.producer,self.original_path,
                                  self.request,logical.sha(self.request),self.output)

    def test_actual_readback_and_cli_preserve_original_unfiltered_evidence(self):
        old=self.original_path.read_bytes()
        result=self.verify()
        self.assertTrue(result['persistent_privileges_verified'])
        self.assertFalse(result['source_observation_is_current_production_read'])
        self.assertFalse(result['mutations'])
        self.assertEqual(self.original_path.read_bytes(),old)
        self.assertEqual(logical.collect_local(self.name)[0],self.before)
        self.output=self.root/'cli.json'
        result=subprocess.run([sys.executable,permissions.__file__,'--bundle',str(self.bundle),'--target',self.name,
            '--logical-receipt',str(self.parent),'--source-proof',str(self.proof_path),'--source-generator',str(self.producer),
            '--original-privileges',str(self.original_path),'--request',str(self.request),'--approved-request-sha256',logical.sha(self.request),
            '--out',str(self.output)],capture_output=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertTrue(json.loads(result.stdout)['persistent_privileges_verified'])

    def test_source_proof_requires_complete_types_capture_and_scope(self):
        for field,value in [('schema',True),('role_count',True),('role_count',0),('off_switch_count',True),
            ('excluded_temp_namespace_count',-1),('excluded_temp_namespace_count',True),('elapsed_seconds',float('nan')),
            ('elapsed_seconds',float('inf')),('elapsed_seconds',True),('read_only',1),('tls_verified',False),
            ('production_mutations',True),('connection_disposed',False),('temporary_material_removed',False),
            ('catalog_sha256','b'*64),('durable_prerequisites_sha256','b'*64),('original_privileges_sha256','b'*64),
            ('generator_sha256','b'*64),('persistent_sql_sha256','b'*64),('commit','bad'),('generated_at','bad'),
            ('generated_at',(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat())]:
            with self.subTest(field=field,value=value):
                changed=copy.deepcopy(self.proof);changed[field]=value
                with self.assertRaises((logical.Refusal,ValueError)):
                    permissions.validate_source(changed,self.before,self.props,self.original,logical.sha(self.producer),self.contract)
        for matrix in ({},dict(self.original,rows=[]),dict(self.original,rows=self.original['rows'][:-1]),
                       dict(self.original,rows=[self.original['rows'][0]]*len(self.original['rows']))):
            with self.subTest(matrix=matrix),self.assertRaises((logical.Refusal,ValueError)):
                permissions.validate_source(self.proof,self.before,self.props,matrix,logical.sha(self.producer),self.contract)

    def test_changed_expected_matrix_and_parent_receipt_refuse(self):
        self.proof['persistent_privileges_sha256']='b'*64;self.write(self.proof_path,self.proof);self.approve()
        with self.assertRaises(logical.Refusal):self.verify()
        self.assertFalse(self.output.exists())
        self.proof['persistent_privileges_sha256']=self.contract.digest(self.matrix);self.write(self.proof_path,self.proof)
        parent=json.loads(self.parent.read_text());parent['archive_sha256']='b'*64;self.write(self.parent,parent);self.approve()
        with self.assertRaises(logical.Refusal):self.verify()
        self.assertFalse(self.output.exists())

    def test_missing_or_changed_inputs_never_publish(self):
        self.producer.write_text('# changed generator\n')
        with self.assertRaises(logical.Refusal):self.verify()
        self.assertFalse(self.output.exists())
        self.producer.unlink()
        with self.assertRaises((logical.Refusal,OSError)):self.verify()
        self.assertFalse(self.output.exists())

    def test_source_or_input_drift_during_publication_refuses(self):
        actual=logical.backup.write_new
        def changed(path,value):
            actual(path,value)
            if '.pending-' in str(path):self.producer.write_text('# changed during publication\n')
        with patch.object(logical.backup,'write_new',side_effect=changed),self.assertRaises(logical.Refusal):self.verify()
        self.assertFalse(self.output.exists())

    def test_exact_temp_schema_scope_and_real_persistent_permission_changes(self):
        baseline=permissions.query_profile(self.name)[2]
        self.sql('ALTER EVENT TRIGGER reject_witness_ddl DISABLE;')
        try:
            self.sql('CREATE TEMP TABLE inert_runtime_namespace(x integer);')
            self.assertEqual(permissions.query_profile(self.name)[2],baseline)
            # Persistent system schemas remain covered, unlike a broad pg_ filter.
            for statement,restore in [('REVOKE USAGE ON SCHEMA information_schema FROM PUBLIC','GRANT USAGE ON SCHEMA information_schema TO PUBLIC'),
                                      ('REVOKE USAGE ON SCHEMA pg_catalog FROM PUBLIC','GRANT USAGE ON SCHEMA pg_catalog TO PUBLIC')]:
                try:
                    self.sql(statement)
                    self.assertNotEqual(permissions.query_profile(self.name)[2],baseline)
                finally:self.sql(restore)
            self.assertEqual(permissions.query_profile(self.name)[2],baseline)
        finally:self.sql('ALTER EVENT TRIGGER reject_witness_ddl ENABLE;')

    def test_pg_toast_schema_grant_reproduces_logical_only_gap_and_supplement_refuses(self):
        self.sql('ALTER EVENT TRIGGER reject_witness_ddl DISABLE; GRANT USAGE ON SCHEMA pg_toast TO PUBLIC; ALTER EVENT TRIGGER reject_witness_ddl ENABLE;')
        try:
            # RED baseline: the original inventory excludes every pg_ schema;
            # durable prerequisites cover only pg_catalog/information_schema.
            baseline=self.root/'logical_without_persistent_supplement.json'
            result=logical.verify_bundle(self.bundle,self.name,self.failed,baseline,self.logical_request,logical.sha(self.logical_request))
            self.assertTrue(result['backup_verified'])
            # GREEN: the approved source persistent profile includes pg_toast.
            with self.assertRaisesRegex(logical.Refusal,'permission_persistent_profile_changed'):
                self.verify()
            self.assertFalse(self.output.exists())
        finally:
            self.sql('ALTER EVENT TRIGGER reject_witness_ddl DISABLE; REVOKE USAGE ON SCHEMA pg_toast FROM PUBLIC; ALTER EVENT TRIGGER reject_witness_ddl ENABLE;')
        self.assertEqual(permissions.query_profile(self.name)[2],self.matrix)

    def test_duplicate_request_fields_and_changed_producer_path_refuse(self):
        raw=self.request.read_text()
        self.request.write_text(raw.replace('"version": 1','"version": 1, "version": 1'))
        with self.assertRaises(logical.Refusal):self.verify()
        self.assertFalse(self.output.exists())
        self.approve()
        original=logical.backup.__file__
        copied=self.root/'copied_inventory.py';copied.write_bytes(Path(original).read_bytes())
        actual=permissions.query_profile
        def changed(target):
            result=actual(target)
            logical.backup.__file__=str(copied)
            return result
        try:
            with patch.object(permissions,'query_profile',side_effect=changed),self.assertRaises(logical.Refusal):self.verify()
            self.assertFalse(self.output.exists())
        finally:logical.backup.__file__=original
