"""Execute the exact frozen coordinator with census/run ports; never launch GitHub."""
import copy,importlib.util,json,pathlib,sys,types,unittest
P=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('reviewed_merge_guard',P/'merge_guard.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
def forbidden(*a,**k):raise AssertionError('Uninjected subprocess forbidden')
guard.subprocess.run=forbidden
BASE=json.loads((P/'review-census-20261031T174045Z.json').read_text())[0]
# A classified synthetic resolved thread permits executable nested-pagination controls.
BASE['inline']=[{'id':991,'body':'resolved owned fixture','user':{'login':'fixture-reviewer'}}]
BASE['graphql']['reviewThreads']={'totalCount':1,'pageInfo':{'hasNextPage':False},'nodes':[{'id':'owned-thread','isResolved':True,'comments':{'totalCount':1,'pageInfo':{'hasNextPage':False},'nodes':[{'databaseId':991,'body':'resolved owned fixture','author':{'login':'fixture-reviewer'}}]}}]}
HEAD=BASE['headRefOid'];ACCEPTED=copy.deepcopy(guard.material(BASE));TRACES=[]
POLICY=types.SimpleNamespace(returncode=1,stdout='',stderr='GraphQL: Base branch policy prohibits the merge')
GOOD=types.SimpleNamespace(returncode=0,stdout='merged (injected)',stderr='')
def change(path,value):
 def mutate(d):
  target=d
  for key in path[:-1]:target=target[key]
  target[path[-1]]=copy.deepcopy(value)
 return mutate
BAD={
 'changed_head':change(['headRefOid'],'0'*40),
 'new_review_body':change(['reviews',0,'body'],'NEW UNCLASSIFIED BODY'),
 'pending_bot_view_request':change(['reviewRequests'],[{'login':'copilot-pull-request-reviewer[bot]'}]),
 'pending_bot_rest_request':change(['requests','users'],[{'login':'copilot-pull-request-reviewer[bot]'}]),
 'unresolved_thread':change(['graphql','reviewThreads','nodes',0,'isResolved'],False),
 'incomplete_thread_pagination':change(['graphql','reviewThreads','pageInfo','hasNextPage'],True),
 'incomplete_nested_pagination':change(['graphql','reviewThreads','nodes',0,'comments','pageInfo','hasNextPage'],True),
 'incomplete_review_count':change(['graphql','reviews','totalCount'],len(BASE['reviews'])+1),
 'incomplete_comment_count':change(['graphql','comments','totalCount'],len(BASE['comments'])+1),
 'incomplete_inline_count':change(['graphql','reviewThreads','nodes',0,'comments','totalCount'],2),
 'reviewer_changes_requested':change(['reviews',0,'state'],'CHANGES_REQUESTED'),
 'aggregate_changes_requested':change(['reviewDecision'],'CHANGES_REQUESTED'),
 'failed_check':change(['statusCheckRollup'],[{'__typename':'CheckRun','status':'COMPLETED','conclusion':'FAILURE'}]),
 'pending_check':change(['statusCheckRollup'],[{'__typename':'CheckRun','status':'IN_PROGRESS','conclusion':None}]),
 'closing_reference':change(['closingIssuesReferences'],[{'number':802}]),
 'boolean_census_count':change(['graphql','reviews','totalCount'],True),
 'pending_review':change(['reviews',0,'state'],'PENDING'),
 'unknown_check':change(['statusCheckRollup'],[{'__typename':'UnrecognizedCheck','state':'SUCCESS'}]),
}
class Ports:
 def __init__(self,censuses,returns):self.censuses=censuses;self.returns=returns;self.reads=0;self.argv=[]
 def census(self):
  if self.reads>=len(self.censuses):raise AssertionError('Unexpected extra census')
  value=self.censuses[self.reads];self.reads+=1
  if isinstance(value,Exception):raise value
  return copy.deepcopy(value)
 def run(self,argv):
  expected=['gh','pr','merge','863','--merge','--match-head-commit',HEAD]+(['--admin']if self.argv else [])
  if argv!=expected:raise AssertionError('Unexpected mutation argv '+repr(argv))
  if len(self.argv)>=len(self.returns):raise AssertionError('Unexpected extra merge attempt')
  result=self.returns[len(self.argv)];self.argv.append(list(argv));return result
 def record(self,name,outcome):TRACES.append({'case':name,'outcome':outcome,'census_calls':self.reads,'injected_merge_argv':self.argv,'actual_external_calls':0})
class GuardTests(unittest.TestCase):
 def run_positive(self,returns,allow,expected,reads,commands):
  ports=Ports([BASE,BASE],returns);result=guard.coordinate(863,HEAD,ACCEPTED,ports.census,ports.run,allow_override=allow);self.assertEqual(result,expected);self.assertEqual(ports.reads,reads);self.assertEqual(len(ports.argv),commands);ports.record(self.id(),result)
 def test_normal_success(self):self.run_positive([GOOD],False,'normal',1,1)
 def test_explicit_override_does_not_bypass_normal_first(self):self.run_positive([GOOD],True,'normal',1,1)
 def test_policy_block_without_explicit_optin(self):self.run_positive([POLICY],False,'maintainer_override_required',1,1)
 def test_protected_branch_block_without_optin(self):self.run_positive([types.SimpleNamespace(returncode=1,stdout='',stderr='Protected branch policy refused')],False,'maintainer_override_required',1,1)
 def test_explicit_override_requires_fresh_second_census(self):self.run_positive([POLICY,GOOD],True,'authorized_override',2,2)
 def test_truthy_nonboolean_optin_cannot_authorize_admin(self):self.run_positive([POLICY],1,'maintainer_override_required',1,1)
 def test_unexpected_normal_rejection_refuses(self):
  ports=Ports([BASE],[types.SimpleNamespace(returncode=1,stdout='',stderr='Authentication failed')]);
  with self.assertRaisesRegex(RuntimeError,'Unexpected normal'):guard.coordinate(863,HEAD,ACCEPTED,ports.census,ports.run,allow_override=True)
  self.assertEqual((ports.reads,len(ports.argv)),(1,1));ports.record(self.id(),'refused')
 def test_empty_normal_rejection_refuses(self):
  ports=Ports([BASE],[types.SimpleNamespace(returncode=1,stdout='',stderr='')]);
  with self.assertRaisesRegex(RuntimeError,'Unexpected normal'):guard.coordinate(863,HEAD,ACCEPTED,ports.census,ports.run,allow_override=True)
  self.assertEqual((ports.reads,len(ports.argv)),(1,1));ports.record(self.id(),'refused')
 def test_failed_override_refuses_without_further_attempt(self):
  ports=Ports([BASE,BASE],[POLICY,types.SimpleNamespace(returncode=1,stdout='',stderr='admin denied')]);
  with self.assertRaisesRegex(RuntimeError,'override failed'):guard.coordinate(863,HEAD,ACCEPTED,ports.census,ports.run,allow_override=True)
  self.assertEqual((ports.reads,len(ports.argv)),(2,2));ports.record(self.id(),'refused')
 def test_initial_census_exception_refuses_before_any_command(self):
  ports=Ports([RuntimeError('census unavailable')],[GOOD]);
  with self.assertRaises(RuntimeError):guard.coordinate(863,HEAD,ACCEPTED,ports.census,ports.run,allow_override=True)
  self.assertEqual((ports.reads,len(ports.argv)),(1,0));ports.record(self.id(),'refused')
 def test_late_census_exception_refuses_admin(self):
  ports=Ports([BASE,RuntimeError('late census unavailable')],[POLICY,GOOD]);
  with self.assertRaises(RuntimeError):guard.coordinate(863,HEAD,ACCEPTED,ports.census,ports.run,allow_override=True)
  self.assertEqual((ports.reads,len(ports.argv)),(2,1));ports.record(self.id(),'refused')
 def test_other_pr_allowlist_refuses(self):
  ports=Ports([BASE],[GOOD]);
  with self.assertRaises(RuntimeError):guard.coordinate(862,HEAD,ACCEPTED,ports.census,ports.run,allow_override=True)
  self.assertEqual((ports.reads,len(ports.argv)),(1,0));ports.record(self.id(),'refused')
def make_bad(name,mutate,late):
 def test(self):
  bad=copy.deepcopy(BASE);mutate(bad);ports=Ports([BASE,bad]if late else [bad],[POLICY,GOOD]if late else [GOOD])
  with self.assertRaises(RuntimeError):guard.coordinate(863,HEAD,ACCEPTED,ports.census,ports.run,allow_override=True)
  self.assertEqual(ports.reads,2 if late else 1);self.assertEqual(len(ports.argv),1 if late else 0);self.assertFalse(any('--admin'in a for a in ports.argv));ports.record(self.id(),'refused after first policy rejection'if late else 'refused before first command')
 return test
for name,mutate in BAD.items():
 for late in [False,True]:setattr(GuardTests,'test_'+('late_'if late else 'initial_')+name,make_bad(name,mutate,late))
if __name__=='__main__':
 label=sys.argv[1];sys.argv=sys.argv[:1];suite=unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests);result=unittest.TextTestRunner(verbosity=2).run(suite);(P/(label+'-traces.json')).write_text(json.dumps(TRACES,indent=2));(P/(label+'-result.json')).write_text(json.dumps({'mode':sys.flags.optimize,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'external_calls':0},indent=2));raise SystemExit(0 if result.wasSuccessful()else 1)
