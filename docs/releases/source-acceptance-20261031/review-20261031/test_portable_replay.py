"""Independent stdlib CLI tests. docker is intercepted; no container is created."""
import json,os,pathlib,shutil,subprocess,sys,tempfile,unittest
HERE=pathlib.Path(__file__).resolve().parent
CANDIDATE=pathlib.Path(os.environ.get('PORTABLE_CANDIDATE',str(HERE.parent)))
class PortableReplay(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='portable-cli-');self.addCleanup(self.tmp.cleanup);self.base=pathlib.Path(self.tmp.name).resolve();self.clone=self.base/'checkout';self.bundle=self.clone/'docs/releases/source-acceptance-20261031';self.bundle.mkdir(parents=True);self.source(self.clone)
  for name in ('run-root-tests.py.bytes','run-final-selection.py.bytes','selection.txt'):shutil.copyfile(CANDIDATE/name,self.bundle/name)
  self.out=self.base/'fresh receipts';self.out.mkdir();self.override=self.base/'override checkout';self.source(self.override);self.bin=self.base/'bin';self.bin.mkdir();self.log=self.base/'docker-calls.jsonl';fake=self.bin/'docker'
  fake.write_text('#!/usr/bin/env python3\nimport os,sys,json,pathlib\np=pathlib.Path(os.environ["FAKE_DOCKER_LOG"]);p.open("a").write(json.dumps({"args":sys.argv[1:],"cwd":os.getcwd()})+"\\n")\nprint("offline fake child stdout")\nprint("offline fake child stderr",file=sys.stderr)\nraise SystemExit(int(os.getenv("FAKE_DOCKER_EXIT","0")))\n');fake.chmod(0o700)
  self.env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],FAKE_DOCKER_LOG=str(self.log));self.env.pop('SOURCE802_SOURCE_ROOT',None);self.env.pop('SOURCE802_EVIDENCE_ROOT',None)
 def source(self,path):
  (path/'frontend').mkdir(parents=True,exist_ok=True);(path/'backend').mkdir(parents=True,exist_ok=True);(path/'backend/alembic.ini').write_text('[alembic]\n')
 def calls(self):
  calls=[json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []
  for call in calls:
   for arg in call['args']:
    if arg.endswith(':/evidence'):
     folder=pathlib.Path(arg[:-len(':/evidence')])
     if folder.name.startswith('source802-replay-'):self.addCleanup(shutil.rmtree,folder,True)
  return calls
 def invoke(self,args,*,companion=False,env=None,cwd=None):
  e=dict(self.env);e.update(env or {});script='run-final-selection.py.bytes' if companion else 'run-root-tests.py.bytes';cmd=[sys.executable]+(['-O'] if sys.flags.optimize else [])+[str(self.bundle/script),*args]
  return subprocess.run(cmd,env=e,cwd=cwd or self.base,capture_output=True,text=True,timeout=10)
 def test_default_checkout_root_is_inferred_from_script_not_author_machine(self):
  r=self.invoke(['portable-default','normal','tests/probe.py']);self.assertEqual(r.returncode,0,r.stderr);calls=self.calls();self.assertEqual(len(calls),1);self.assertIn(str(self.clone)+':/workspace:ro',calls[0]['args']);self.assertEqual(pathlib.Path(calls[0]['cwd']),self.clone)
 def test_explicit_source_and_receipt_roots_are_used(self):
  r=self.invoke(['portable-override','optimized','tests/probe.py'],env={'SOURCE802_SOURCE_ROOT':str(self.override),'SOURCE802_EVIDENCE_ROOT':str(self.out)});self.assertEqual(r.returncode,0,r.stderr);calls=self.calls();self.assertEqual(len(calls),1);self.assertIn(str(self.override)+':/workspace:ro',calls[0]['args']);self.assertIn(str(self.out)+':/evidence',calls[0]['args']);self.assertIn('-O',calls[0]['args']);self.assertTrue((self.out/'portable-override.command.json').is_file())
 def test_companion_runs_only_committed_names_and_selection(self):
  r=self.invoke(['normal'],companion=True,env={'SOURCE802_EVIDENCE_ROOT':str(self.out)});self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(len(self.calls()),1);selection=(self.bundle/'selection.txt').read_text().splitlines();self.assertTrue(all(s in self.calls()[0]['args'] for s in selection if s))
 def test_unknown_mode_refuses_before_docker(self):
  r=self.invoke(['portable-invalid','surprise','tests/probe.py'],env={'SOURCE802_EVIDENCE_ROOT':str(self.out)});self.assertNotEqual(r.returncode,0);self.assertEqual(self.calls(),[])
 def test_existing_receipts_are_never_clobbered(self):
  for folder in [self.bundle,self.out]:
   for suffix in ['.txt','.command.json','.xml']:(folder/('portable-collision'+suffix)).write_text('ORIGINAL RECEIPT')
  r=self.invoke(['portable-collision','normal','tests/probe.py'],env={'SOURCE802_EVIDENCE_ROOT':str(self.out)});self.assertNotEqual(r.returncode,0);self.assertEqual(self.calls(),[])
  for folder in [self.bundle,self.out]:
   for suffix in ['.txt','.command.json','.xml']:self.assertEqual((folder/('portable-collision'+suffix)).read_text(),'ORIGINAL RECEIPT')
 def test_failed_child_exit_is_propagated(self):
  r=self.invoke(['portable-child-fail','normal','tests/probe.py'],env={'SOURCE802_EVIDENCE_ROOT':str(self.out),'FAKE_DOCKER_EXIT':'23'});self.assertEqual(r.returncode,23,r.stdout+r.stderr);self.assertEqual(len(self.calls()),1);self.assertIn('offline fake child',r.stdout+r.stderr)
 def refused(self,env,args=None):
  r=self.invoke(args or ['portable-refuse','normal','tests/probe.py'],env=env);self.assertNotEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(self.calls(),[])
 def test_source_override_missing_directory_refuses(self):
  self.refused({'SOURCE802_SOURCE_ROOT':str(self.base/'absent'),'SOURCE802_EVIDENCE_ROOT':str(self.out)})
 def test_source_override_file_refuses(self):
  bad=self.base/'source-file';bad.write_text('not a directory');self.refused({'SOURCE802_SOURCE_ROOT':str(bad),'SOURCE802_EVIDENCE_ROOT':str(self.out)})
 def test_source_override_incomplete_marker_refuses(self):
  (self.override/'backend/alembic.ini').unlink();self.refused({'SOURCE802_SOURCE_ROOT':str(self.override),'SOURCE802_EVIDENCE_ROOT':str(self.out)})
 def test_empty_explicit_source_override_never_falls_back_to_cwd(self):
  r=self.invoke(['portable-empty','normal','tests/probe.py'],env={'SOURCE802_SOURCE_ROOT':'','SOURCE802_EVIDENCE_ROOT':str(self.out)},cwd=self.override);self.assertNotEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(self.calls(),[])
 def test_detached_helper_cannot_select_valid_checkout_from_cwd(self):
  detached=self.base/'detached';shutil.copytree(self.bundle,detached);self.bundle=detached;r=self.invoke(['portable-detached','normal','tests/probe.py'],env={'SOURCE802_EVIDENCE_ROOT':str(self.out)},cwd=self.override);self.assertNotEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(self.calls(),[])
 def test_evidence_file_refuses(self):
  bad=self.base/'receipt-file';bad.write_text('untouched');self.refused({'SOURCE802_EVIDENCE_ROOT':str(bad)});self.assertEqual(bad.read_text(),'untouched')
 def test_missing_evidence_directory_is_created(self):
  out=self.base/'new'/'nested receipts';r=self.invoke(['portable-create','normal','tests/probe.py'],env={'SOURCE802_EVIDENCE_ROOT':str(out)});self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertTrue((out/'portable-create.command.json').is_file())
 def test_invalid_receipt_names_refuse(self):
  for name in ['../escape','nested/file','.','..','two words','bad;name']:
   with self.subTest(name=name):self.refused({'SOURCE802_EVIDENCE_ROOT':str(self.out)},[name,'normal','tests/probe.py'])
 def test_any_single_existing_receipt_prevents_child(self):
  for i,suffix in enumerate(['.txt','.command.json','.xml']):
   with self.subTest(suffix=suffix):
    name='single-collision-'+str(i);p=self.out/(name+suffix);p.write_text('ORIGINAL');self.refused({'SOURCE802_EVIDENCE_ROOT':str(self.out)},[name,'normal','tests/probe.py']);self.assertEqual(p.read_text(),'ORIGINAL')
 def test_dangling_receipt_symlink_refuses_without_creating_target(self):
  target=self.base/'must-not-be-written';(self.out/'portable-symlink.command.json').symlink_to(target);self.refused({'SOURCE802_EVIDENCE_ROOT':str(self.out)},['portable-symlink','normal','tests/probe.py']);self.assertFalse(target.exists())
 def test_default_receipt_directory_is_fresh_on_repeat(self):
  for i in range(2):
   r=self.invoke(['portable-repeat','normal','tests/probe.py']);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  calls=self.calls();mounts=[next(v for v in c['args'] if v.endswith(':/evidence')) for c in calls];self.assertEqual(len(mounts),2);self.assertNotEqual(mounts[0],mounts[1]);self.assertFalse((self.bundle/'portable-repeat.command.json').exists())
 def test_failed_child_receipt_preserves_exact_nonzero_status(self):
  r=self.invoke(['portable-failure-receipt','normal','tests/probe.py'],env={'SOURCE802_EVIDENCE_ROOT':str(self.out),'FAKE_DOCKER_EXIT':'37'});self.assertEqual(r.returncode,37);receipt=json.loads((self.out/'portable-failure-receipt.command.json').read_text());self.assertEqual(receipt['exit_code'],37);self.assertIn('offline fake child stderr',(self.out/'portable-failure-receipt.txt').read_text())
 def test_companion_uses_fresh_names_on_repeat(self):
  for i in range(2):
   r=self.invoke(['normal'],companion=True,env={'SOURCE802_EVIDENCE_ROOT':str(self.out)});self.assertEqual(r.returncode,0,r.stdout+r.stderr)
  calls=self.calls();names=[next(v for v in c['args'] if v.startswith('--junitxml=')) for c in calls];self.assertEqual(len(names),2);self.assertNotEqual(names[0],names[1])
 def test_empty_explicit_evidence_override_refuses(self):
  r=self.invoke(['portable-empty-evidence','normal','tests/probe.py'],env={'SOURCE802_EVIDENCE_ROOT':''},cwd=self.clone);self.assertNotEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(self.calls(),[])
 def test_companion_accepts_documented_extracted_py_root_helper(self):
  (self.bundle/'run-root-tests.py.bytes').rename(self.bundle/'run-root-tests.py');r=self.invoke(['optimized'],companion=True,env={'SOURCE802_EVIDENCE_ROOT':str(self.out)});self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(len(self.calls()),1);self.assertIn('-O',self.calls()[0]['args'])
 def test_companion_missing_or_empty_inputs_refuse(self):
  path=self.bundle/'selection.txt';saved=path.read_bytes()
  for state in ['empty','missing','missing-helper']:
   with self.subTest(state=state):
    if state=='empty':path.write_text('  \n')
    elif state=='missing':path.unlink()
    else:path.write_bytes(saved);(self.bundle/'run-root-tests.py.bytes').unlink()
    r=self.invoke(['normal'],companion=True,env={'SOURCE802_EVIDENCE_ROOT':str(self.out)});self.assertNotEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(self.calls(),[])
if __name__=='__main__':unittest.main(verbosity=2)
