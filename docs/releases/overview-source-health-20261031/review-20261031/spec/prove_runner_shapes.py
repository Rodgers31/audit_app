"""Run exact historical argv builders, replacing only project selectors/output with sentinels."""
import json,os,pathlib,runpy,subprocess,sys
P=pathlib.Path(__file__).resolve().parent
original_run=subprocess.run
records=[]
for name in ['run_review.py','run_final_review.py','run_canonical_affected.py']:
 def injected(argv,*,_name=name,**kwargs):
  if argv[:2]!=['docker','run']or argv[argv.index('--network')+1]!='none':raise RuntimeError('Unexpected historical runtime shape')
  i=argv.index('admin-redesign-python-runtime:local')+1
  if argv[i:i+5]!=['python','-O','-m','pytest','-q']:raise RuntimeError('Historical optimized entrypoint changed')
  if any(x.startswith('--assert')for x in argv):raise RuntimeError('Historical runner changes default assertion rewriting')
  xml=P/(_name+'-assertions.xml')
  child=[sys.executable,'-O','-m','pytest','-q','-p','no:cacheprovider',str(P/'test_optimizer_assertions.py'),'--junitxml='+str(xml)]
  records.append({'runner':_name,'constructed_docker_argv':argv,'executed_child':child,'selector_redirect_only':True,'actual_docker_or_gh_calls':0})
  return original_run(child,**kwargs)
 subprocess.run=injected
 saved=sys.argv;sys.argv=[str(P/'historical-runners'/name),'--optimized']
 try:
  try:runpy.run_path(str(P/'historical-runners'/name),run_name='__main__')
  except SystemExit as exc:code=exc.code
  else:raise RuntimeError('Runner did not return child exit')
 finally:sys.argv=saved;subprocess.run=original_run
 if code!=1:raise RuntimeError('False assertions were not surfaced by '+name+': '+repr(code))
 records[-1]['propagated_exit']=code
# Calibrate the detector: disabling rewriting under-O makes the same false asserts disappear.
plain=[sys.executable,'-O','-m','pytest','--assert=plain','-q','-p','no:cacheprovider',str(P/'test_optimizer_assertions.py'),'--junitxml='+str(P/'plain-negative-calibration.xml')]
with (P/'plain-negative-calibration.txt').open('wb')as out:r=original_run(plain,stdout=out,stderr=subprocess.STDOUT)
if r.returncode!=0:raise RuntimeError('Expected false-green calibration when rewriting is deliberately disabled')
(P/'assertion-runner-results.json').write_text(json.dumps({'records':records,'plain_negative_calibration':{'argv':plain,'exit':r.returncode,'not_a_validation_pass':True},'optimized_runtime':sys.version,'claim':'All3 exact historical builders keep default rewriting and propagate false assertion failures; no full project suites replayed by this calibration'},indent=2))
print(json.dumps({'historical_runner_shapes':len(records),'false_assertions_surfaced':True,'actual_gh_or_nested_docker':0,'unsafe_plain_calibration_exit':r.returncode},indent=2))
