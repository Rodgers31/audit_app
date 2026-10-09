import examples from './batch7_etl_ui_examples.json';
import { commandFilters, commandProgress, dispatchCurrent, parseCommand, parseCommandAcceptance, parseCommandList, parseDispatchCapability } from '@/lib/admin/etlDispatch';
const now=Date.parse(examples.capability_ready.timestamp);
const clone=<T,>(v:T):T=>JSON.parse(JSON.stringify(v));
const expected={page:1,page_size:20,source:'' as const,status:'' as const};
test('frozen unavailable/ready/replayed examples retain calendar-independent evidence',()=>{
  expect(parseDispatchCapability(examples.capability_unavailable,now).available).toBe(false);
  const ready=parseDispatchCapability(examples.capability_ready,now);
  expect(dispatchCurrent(ready,now)).toBe(true);
  expect(dispatchCurrent(ready,Date.parse(ready.worker.expires_at!))).toBe(false);
  expect(parseCommandAcceptance(examples.accepted,{source:'oag',dry_run:true},202).command.status).toBe('queued');
  expect(parseCommandAcceptance(examples.replayed,{source:'oag',dry_run:true},202).replayed).toBe(true);
  expect(parseCommandList(examples.list,expected).total).toBe(1);
});
test.each([null,{},[],{...examples.capability_ready,available:'true'},{...examples.capability_ready,evidence:'calendar_plan'},
  {...examples.capability_ready,generation:null},{...examples.capability_ready,generation:'ABC'},
  {...examples.capability_ready,sources:{}},{...examples.capability_ready,reason:''},
  {...examples.capability_ready,reason:'https://private.invalid/token'},
  {...examples.capability_ready,worker:{...examples.capability_ready.worker,status:'unavailable'}}])
('malformed capability %j fails closed',raw=>expect(()=>parseDispatchCapability(raw,now)).toThrow());
test.each(['available','reason','generation','timestamp','worker','sources'])('missing capability %s cannot certify readiness',key=>{
  const raw:Record<string,unknown>=clone(examples.capability_ready);delete raw[key];
  expect(()=>parseDispatchCapability(raw,now)).toThrow();
});
test.each(['2026-02-30T12:00:00Z','2026-10-09T24:00:00Z','2026-10-09T12:00:00','2026-10-09T12:00:00+03:00','2026-10-09T12:00:60Z'])('real UTC timestamp required: %s',value=>{
  expect(()=>parseCommand({...examples.detail,created_at:value})).toThrow();
});
test('exact six sources, global support and live lease are required',()=>{
  const extra={...examples.capability_ready,sources:{...examples.capability_ready.sources,unknown:{available:true,reason:'Supported.'}}};
  expect(()=>parseDispatchCapability(extra,now)).toThrow();
  expect(()=>parseDispatchCapability({...examples.capability_ready,available:false,generation:null,worker:{status:'unavailable',last_seen_at:null,expires_at:null}},now)).toThrow();
  expect(()=>parseDispatchCapability(examples.capability_ready,now+30000)).toThrow();
  expect(()=>parseDispatchCapability(examples.capability_ready,NaN)).toThrow();
});
test.each([true,0,-1,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,'3',null])('strict positive version %j',version=>{
  expect(()=>parseCommand({...examples.detail,version})).toThrow();
});
test.each([true,0,-1,NaN,Infinity,2147483648,'1',null])('completed receipt needs actual bounded observation %j',job_id=>{
  expect(()=>parseCommand({...examples.detail,job_id})).toThrow();
});
test.each([
  {...examples.detail,dry_run:'false'}, {...examples.detail,status:'healthy'},
  {...examples.detail,outcome:'failed'}, {...examples.detail,started_at:null},
  {...examples.detail,finished_at:null}, {...examples.detail,updated_at:examples.detail.created_at},
  {...examples.accepted.command,job_id:1}, {...examples.accepted.command,outcome:'completed'},
  {...examples.accepted.command,status:'running'}, {...examples.accepted.command,status:'failed'},
  {...examples.detail,status:'interrupted',outcome:'completed'}, {...examples.detail,errors:['private']},
])('inconsistent receipt %j is not rendered as success',raw=>expect(()=>parseCommand(raw)).toThrow());
test('requested identity, source/mode/HTTP acceptance and persisted audit must match',()=>{
  expect(()=>parseCommand(examples.detail,'33333333-3333-4333-8333-333333333333')).toThrow();
  expect(()=>parseCommandAcceptance(examples.accepted,{source:'cra',dry_run:true},202)).toThrow();
  expect(()=>parseCommandAcceptance(examples.accepted,{source:'oag',dry_run:false},202)).toThrow();
  expect(()=>parseCommandAcceptance(examples.accepted,{source:'oag',dry_run:true},200)).toThrow();
  expect(()=>parseCommandAcceptance({...examples.accepted,audit_recorded:false},{source:'oag',dry_run:true},202)).toThrow();
});
test('refresh cannot regress version, status, intent, observation or recorded timestamps',()=>{
  const completed=parseCommand(examples.detail),queued=parseCommand(examples.accepted.command);
  expect(commandProgress(completed,queued)).toEqual(completed);
  expect(()=>commandProgress(queued,completed)).toThrow();
  expect(()=>commandProgress({...completed,job_id:2,version:4},completed)).toThrow();
  expect(()=>commandProgress({...completed,source:'cra',version:4},completed)).toThrow();
  expect(()=>commandProgress({...completed,updated_at:'2026-10-09T12:00:04Z'},completed)).toThrow();
});
test.each([true,-1,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,'1'])('invalid total %j rejects history',total=>{
  expect(()=>parseCommandList({...examples.list,total},expected)).toThrow();
});
test('history enforces exact bounds, identity uniqueness, filters, counts and has_more',()=>{
  for(const raw of [{...examples.list,page:2},{...examples.list,page_size:51},{...examples.list,has_more:true},{...examples.list,entries:[]},{...examples.list,total:2,entries:[examples.detail,examples.detail]}]) expect(()=>parseCommandList(raw,expected)).toThrow();
  expect(()=>parseCommandList(examples.list,{...expected,page:10001})).toThrow();
  expect(()=>parseCommandList(examples.list,{...expected,page_size:51})).toThrow();
  expect(()=>parseCommandList(examples.list,{...expected,source:'cra'})).toThrow();
  expect(()=>parseCommandList(examples.list,{...expected,status:'failed'})).toThrow();
  expect(parseCommandList({entries:[],page:5,page_size:20,total:1,has_more:false},{...expected,page:5}).entries).toEqual([]);
});
test('equal timestamp instants still require descending UUID order',()=>{
  const first={...examples.detail,id:'11111111-1111-4111-8111-111111111111'};
  const second={...examples.detail,id:'33333333-3333-4333-8333-333333333333',created_at:examples.detail.created_at.replace('Z','+00:00')};
  expect(()=>parseCommandList({...examples.list,total:2,entries:[first,second]},expected)).toThrow();
});
test('URL bounds exclude paths, duplicates, unknown filters and overflow',()=>{
  expect(commandFilters(new URLSearchParams('page=NaN&page_size=51&source=../../oag&status=healthy')).canonical.toString()).toBe('');
  expect(commandFilters(new URLSearchParams('source=oag&status=interrupted&page=10000&page_size=50&unknown=secret')).canonical.toString()).toBe('source=oag&status=interrupted&page_size=50&page=10000');
});
