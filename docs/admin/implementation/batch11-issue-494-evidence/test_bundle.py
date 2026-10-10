import copy,hashlib,importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('validator',Path(__file__).with_name('verify_bundle.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
class Controls(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import sys
  cls.archive=Path(PACKET_ARGS[0]);cls.manifest=Path(PACKET_ARGS[1]);cls.data=json.loads(cls.manifest.read_bytes());cls.members={n:zipfile.ZipFile(cls.archive).read(n) for n in cls.data['members']};cls.receipt_name=next(iter(cls.data['receipts']))
 def mutation(self,change):
  with tempfile.TemporaryDirectory() as scratch:
   root=Path(scratch);members=dict(self.members);manifest=copy.deepcopy(self.data);record=json.loads(members[self.receipt_name]);change(record,manifest,members)
   members[self.receipt_name]=(json.dumps(record)+'\n').encode()
   archive=root/'mutant.zip'
   with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for n,b in members.items():z.writestr(n,b)
   manifest['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest();manifest['members']={n:hashlib.sha256(b).hexdigest() for n,b in members.items()};p=root/'manifest.json';p.write_text(json.dumps(manifest))
   with self.assertRaises((ValueError,KeyError,TypeError,json.JSONDecodeError)):v.verify(archive,p)
 def test_actual_packet(self):self.assertIs(v.verify(self.archive,self.manifest)['current_checkout_acceptance'],False)
 def test_boolean_exit(self):self.mutation(lambda r,m,b:r.update(exit=True))
 def test_float_exit(self):self.mutation(lambda r,m,b:r.update(exit=0.0))
 def test_string_stability(self):self.mutation(lambda r,m,b:r.update(source_stable='true'))
 def test_missing_source(self):self.mutation(lambda r,m,b:r.pop('source_before'))
 def test_empty_inventory(self):self.mutation(lambda r,m,b:r['source_before'].update(files={}))
 def test_wrong_producer(self):self.mutation(lambda r,m,b:r.update(generator_sha256='0'*64))
 def test_missing_packet_producer(self):self.mutation(lambda r,m,b:m.pop('producer_sha256'))
 def test_unbound_packet_producer(self):self.mutation(lambda r,m,b:m.update(schema=2,producer_sha256='0'*64))
 def test_wrong_stream(self):self.mutation(lambda r,m,b:r.update(stdout_sha256='0'*64))
 def test_missing_command(self):self.mutation(lambda r,m,b:r.pop('command'))
 def test_missing_error(self):self.mutation(lambda r,m,b:r.pop('error'))
 def test_missing_error_both(self):self.mutation(lambda r,m,b:(r.pop('error'),m['receipts'][self.receipt_name].pop('error')))
 def test_empty_environment(self):self.mutation(lambda r,m,b:r.update(resolved_environment={}))
 def test_missing_environment_field(self):self.mutation(lambda r,m,b:r['resolved_environment'].pop('HOME'))
 def test_relative_environment(self):self.mutation(lambda r,m,b:r['resolved_environment'].update(HOME='relative'))
 def test_wrong_environment_policy(self):self.mutation(lambda r,m,b:r['resolved_environment'].update(ONNXRUNTIME_NODE_INSTALL='cuda12'))
 def test_unexpected_environment(self):self.mutation(lambda r,m,b:r['resolved_environment'].update(PROVIDER_TOKEN='unexpected'))
 def test_wrong_executable_path(self):self.mutation(lambda r,m,b:r['resolved_environment'].update(PATH='/wrong:'+r['resolved_environment']['PATH']))
 def test_real_home(self):self.mutation(lambda r,m,b:r['resolved_environment'].update(HOME='/Users/roger'))
 def test_real_npm_config(self):self.mutation(lambda r,m,b:r['resolved_environment'].update(npm_config_userconfig='/Users/roger/.npmrc'))
 def test_extra_path(self):self.mutation(lambda r,m,b:r['resolved_environment'].update(PATH=r['resolved_environment']['PATH']+':/Users/roger/.local/bin'))
 def test_bad_source_names_both(self):self.mutation(lambda r,m,b:[r[key].update(files={'../escape':'0'*64}) for key in ('source_before','source_after')])
 def test_current_scope(self):self.mutation(lambda r,m,b:r.update(current_checkout_acceptance=True))
 def test_incomplete_receipts(self):self.mutation(lambda r,m,b:m['receipts'].pop(self.receipt_name))
 def test_duplicate_json(self):
  with self.assertRaises(ValueError):v.object_json('{"exit":0,"exit":1}')
 def test_nonfinite_json(self):
  with self.assertRaises(ValueError):v.object_json('{"exit":NaN}')
 def test_source_internal_output(self):
  with tempfile.TemporaryDirectory() as scratch:
   root=Path(scratch).resolve();inside=root/'.git/ignored';inside.mkdir(parents=True)
   with self.assertRaises(ValueError):v.external_output(inside,root)
 def test_output_symlink(self):
  with tempfile.TemporaryDirectory() as scratch:
   root=Path(scratch).resolve();target=root/'outside';target.mkdir();link=root/'link';link.symlink_to(target,target_is_directory=True)
   with self.assertRaises(ValueError):v.external_output(link,root/'checkout')
 def test_external_positive(self):
  with tempfile.TemporaryDirectory() as scratch:
   root=Path(scratch).resolve();output=root/'outside';output.mkdir();self.assertEqual(v.external_output(output,root/'checkout'),output)
if __name__=='__main__':
 import sys
 if len(sys.argv)!=3:raise SystemExit('ARCHIVE MANIFEST required')
 PACKET_ARGS=sys.argv[1:]
 unittest.main(argv=[sys.argv[0]],verbosity=2)
