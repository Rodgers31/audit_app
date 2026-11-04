import api from '@/lib/api/axios';
import {recoveredSocialCommand,socialCommandIdentity,socialCommandKey} from '@/lib/api/socialCommandRecovery';
import {studioApi,Composition} from '@/lib/api/socialStudio';
import {platformConnectionApi,PlatformChoice} from '@/lib/api/socialPlatformConnections';
import {privacyApi,PrivacyPlan} from '@/lib/api/socialPrivacy';
import fixtures from '@/tests/socialAcknowledgementShipping.json';
import '@/tests/socialRecoveryCrypto';
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{post:jest.fn(),get:jest.fn()}}));
const send=api.post as jest.Mock, actor='00000000-0000-4000-8000-000000000001',id='00000000-0000-4000-8000-000000000011',other='00000000-0000-4000-8000-000000000012';
const composition:Composition={schema_version:1,template:'did_you_know',template_version:1,kind:'graphic',revision_id:id,title:'Fixture',facts:[{id:'fact',text:'Fact',source_url:'https://fixture.invalid/source'},{id:'context',text:'Context',source_url:'https://fixture.invalid/source'}],scenes:[{fact_id:'fact',seconds:15}]};
function normalized(body:Composition){const row=fixtures.cases.find(row=>JSON.stringify(row.raw)===JSON.stringify(body));if(!row)throw new Error('Missing shipping contract fixture');return row.normalized;}
function wire(body:Composition){return {id:other,revision_id:id,state:'queued',version:1,composition:normalized(body),input_hash:'a'.repeat(64),runtime_hash:null,sha256:null,inspection:null,approved_sha256:null,safe_error:null,cancel_requested:false,attempt:1,retry_of_id:null};}
beforeEach(()=>{jest.resetAllMocks();sessionStorage.clear();});
test.each(['unmodified','title-space','fact-space'] as const)('legitimate backend-normalized studio creation %s must acknowledge and clear exact original key',async kind=>{
 const body={...composition,...(kind==='title-space'?{title:' Fixture '}:{}),facts:composition.facts.map(f=>({...f,text:kind==='fact-space'?' '+f.text+' ':f.text}))};
 const identity=socialCommandIdentity(actor,'post','/studio/jobs',body),key=socialCommandKey(actor,identity);send.mockResolvedValue({data:wire(body)});
 let failed:unknown;try{await recoveredSocialCommand(actor,'post','/studio/jobs',body,k=>studioApi.create(body,k));}catch(e){failed=e;}
 expect(send.mock.calls[0][1]).toEqual(body);expect(send.mock.calls[0][2].headers['Idempotency-Key']).toBe(key);
 console.log(JSON.stringify({case:kind,errorCode:(failed as {code?:string})?.code,entries:JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries.length}));
 expect(failed).toBeUndefined();expect(JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries).toHaveLength(0);
});
test('legitimate platform confirmation DTO needs no invented subject echo',async()=>{
 const choice:PlatformChoice={flow_id:id,external_account_id:'external-subject',display_name:'Fixture',handle:null,granted_scopes:[],expires_at:'2027-01-01T00:00:00Z'},body={external_account_id:choice.external_account_id,reason:'Confirm the exact provider account'};
 send.mockResolvedValue({data:{flow_id:id,account:{id:other,platform:'threads',connection_state:'connected',display_name:'Fixture',handle:null,publishing_enabled:false},credential_id:other,credential_version:1}});
 await expect(recoveredSocialCommand(actor,'post',`/platform-connections/threads/flows/${id}/confirm`,body,key=>platformConnectionApi.confirm('threads',choice,key))).resolves.toEqual({account_id:other});
 expect(JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries).toHaveLength(0);
});
test('legitimate completed privacy reconciliation preserves exact operation and scope proof',async()=>{
 const prior:PrivacyPlan={id,receipt_id:other,proposed_by:other,policy_key:'fixture',policy_hash:'a'.repeat(64),plan_hash:'b'.repeat(64),evidence:'Independently reviewed scope.',scope:{credentials:[{id:other,version:2}],flows:[],media_assets:[]},decision:'approved',approved_by:actor,execution:{id:other,state:'outcome_unknown',version:2,result:{}}};
 send.mockResolvedValue({data:{...prior,execution:{...prior.execution,state:'completed',version:3,result:{scope_completed:true,request_completed:false,local_erasure_verified:true,media:[],retained:['audit']}}}});
 await expect(recoveredSocialCommand(actor,'post',`/privacy/plans/${id}/reconcile`,{expected_version:2},key=>privacyApi.command(`/plans/${id}/reconcile`,{expected_version:2},key,{actor,plan:prior}))).resolves.toBeDefined();
 expect(JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries).toHaveLength(0);
});
test.each(['lowercase','uppercase'] as const)('legitimate privacy proposal media UUID %s must acknowledge backend canonical UUID',async kind=>{
 const asset='abcdefab-cdef-4abc-8def-abcdefabcdef',body={receipt_id:other,policy_key:'fixture',policy_hash:'a'.repeat(64),evidence:'Independently reviewed scope.',erase_credentials:[],erase_flows:[],media_assets:[kind==='uppercase'?asset.toUpperCase():asset]};
 const canonical=fixtures.cases.find(row=>row.name==='privacy-'+kind);if(!canonical)throw new Error('Missing shipping privacy fixture');
 const identity=socialCommandIdentity(actor,'post','/privacy/plans',body),key=socialCommandKey(actor,identity);
 send.mockResolvedValue({data:{id:key,receipt_id:other,proposed_by:actor,policy_key:'fixture',policy_hash:'a'.repeat(64),plan_hash:'b'.repeat(64),evidence:body.evidence,scope:{credentials:[],flows:[],media_assets:[{id:(canonical.normalized as {media_assets:string[]}).media_assets[0],scope_hash:'c'.repeat(64)}]},decision:'pending_review',approved_by:null,execution:null}});
 let failed:unknown;try{await recoveredSocialCommand(actor,'post','/privacy/plans',body,k=>privacyApi.command('/plans',body,k,{actor}));}catch(e){failed=e;}
 expect(send.mock.calls[0][1]).toEqual(body);console.log(JSON.stringify({case:'privacy-'+kind,errorCode:(failed as {code?:string})?.code}));
 expect(failed).toBeUndefined();expect(JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries).toHaveLength(0);
});
