"""Independent OFF-state operation-accounting regressions. No sockets or DB."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
assess=runpy.run_path(str(ROOT/'tools/worker_rehearsal/capacity_v2.py'))['assess']
fixture=runpy.run_path(str(ROOT/'backend/tests/social/test_worker_rehearsal_guards.py'))['evidence']

class UnaccountedOperations(unittest.TestCase):
    def test_complete_offline_control_remains_unauthenticated(self):
        result=assess(*fixture())
        self.assertEqual(result['provider_mutations'],6)
        self.assertIs(result['production_accepted'],False)
        self.assertIs(result['evidence_authenticated'],False)

    def test_unexpected_method_cannot_be_silently_discarded(self):
        value=fixture()
        value[5].append(dict(request_id='unapproved-delete',method='DELETE',path='/foreign-target',
            started=4,completed=5,run_id='owned-run',case='capacity'))
        with self.assertRaises(ValueError):
            assess(*value)

    def test_actual_endpoint_error_start_cannot_be_silently_discarded(self):
        spec=importlib.util.spec_from_file_location('owned_endpoint_replay',ROOT/'tools/worker_rehearsal/endpoints.py')
        endpoint=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(endpoint)
        errors=[]
        request=types.SimpleNamespace(headers={'Content-Length':'0','Host':'graph.facebook.com'},
            command='GET',path='/foreign-target',rfile=io.BytesIO(b''),send_error=errors.append)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'endpoint-case').write_text('capacity')
            (root/'endpoint-delay').write_text('0')
            stdout=io.StringIO()
            with patch.object(endpoint,'ROOT',root),patch.dict(os.environ,{'B15_ENDPOINT_RUN_ID':'owned-run'},clear=True), \
                    patch.object(endpoint.time,'monotonic',return_value=4),contextlib.redirect_stdout(stdout):
                with self.assertRaisesRegex(RuntimeError,'Unexpected inert Graph request'):
                    endpoint.Endpoint.respond(request)
        self.assertEqual(errors,[400])
        emitted=[json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(len(emitted),1)
        self.assertEqual(emitted[0]['path'],'/foreign-target')
        value=fixture()
        value[5].extend(emitted)
        with self.assertRaises(ValueError):
            assess(*value)

    def test_unfinished_provider_read_cannot_be_silently_discarded(self):
        value=fixture()
        value[2]['cohort']['provider_paths']=['/v26.0/901/feed']
        for row in value[5]:
            if row['method']=='POST':row['path']='/v26.0/901/feed'
        value[2]['social_post_targets'][0]['checkpoint']={'photo_id':'401'}
        value[5].append(dict(request_id='unfinished-read',method='GET',path='/v26.0/401',
            started=4,run_id='owned-run',case='capacity'))
        with self.assertRaisesRegex(ValueError,'Incomplete operation observations'):
            assess(*value)

    def test_complete_fixture_reads_and_metadata_are_accounted(self):
        value=fixture()
        value[2]['cohort']['provider_paths']=['/v26.0/901/feed']
        value[2]['social_post_targets'][0].update(primary_remote_id='901_778',
            checkpoint={'photo_id':'401'},remote_refs={'post_id':'901_778'})
        for row in value[5]:
            if row['method']=='POST':row['path']='/v26.0/901/feed'
        for index,(method,path) in enumerate((('GET','/v26.0/401'),
                ('GET','/v26.0/901_778'),('GET','/rest/v1/profiles'),
                ('HEAD','/media-test/owned'))):
            common=dict(request_id='read-'+str(index),method=method,path=path,
                        run_id='owned-run',case='capacity')
            value[5].extend((dict(common,started=4,input_bytes=0),
                             dict(common,completed=5,output_bytes=0)))
        self.assertEqual(assess(*value)['observed_operations'],11)

    def test_foreign_read_or_metadata_routes_refuse(self):
        for method,path in (('GET','/foreign-target'),('HEAD','/foreign-target'),
                ('GET','/v26.0/902_778'),('HEAD','/v26.0/401')):
            value=fixture()
            common=dict(request_id='foreign',method=method,path=path,
                        run_id='owned-run',case='capacity')
            value[5].extend((dict(common,started=4),dict(common,completed=5)))
            with self.subTest(method=method,path=path),self.assertRaises(ValueError):
                assess(*value)

    def test_all_read_phases_share_method_identity_and_window(self):
        diagnostics={'duplicate':'Duplicate operation start identity',
            'identity':'Unmatched/duplicate operation completion',
            'method':'Operation method changed between phases',
            'outside':'Operation path/order outside measured API window',
            'both':'Operation event must contain exactly one phase',
            'neither':'Operation event must contain exactly one phase',
            'bytes':'Invalid measured integer'}
        for mutation in ('duplicate','identity','method','outside','both','neither','bytes'):
            value=fixture()
            common=dict(request_id='extra-read',method='GET',path='/media-test/owned',
                        run_id='owned-run',case='capacity')
            start,end=dict(common,started=4),dict(common,completed=5)
            if mutation=='duplicate':value[5].append(dict(start))
            elif mutation=='identity':end['request_id']='different'
            elif mutation=='method':start['path']=end['path']='/media-test/owned';end['method']='HEAD'
            elif mutation=='outside':end['completed']=182
            elif mutation=='both':start['completed']=5
            elif mutation=='neither':del start['started']
            else:end['output_bytes']=True
            value[5].extend((start,end))
            with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,diagnostics[mutation]):
                assess(*value)

if __name__=='__main__': unittest.main(verbosity=2)
