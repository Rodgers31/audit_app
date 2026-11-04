import api from '@/lib/api/axios';
import { recoveredSocialCommand, socialCommandIdentity, socialCommandKey } from '@/lib/api/socialCommandRecovery';
import { platformConnectionApi, PlatformChoice } from '@/lib/api/socialPlatformConnections';
import { studioApi, Composition } from '@/lib/api/socialStudio';
import { privacyApi } from '@/lib/api/socialPrivacy';
import '@/tests/socialRecoveryCrypto';
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { post: jest.fn(), get: jest.fn() } }));
const post = api.post as jest.Mock;
const actor='00000000-0000-4000-8000-000000000001', id='00000000-0000-4000-8000-000000000011', other='00000000-0000-4000-8000-000000000012';
const keyOf = (path:string, body:object) => socialCommandKey(actor,socialCommandIdentity(actor,'post',path,body));
beforeEach(()=>{jest.resetAllMocks();sessionStorage.clear();});
const choice: PlatformChoice={flow_id:id,external_account_id:'account-a',display_name:'Fixture',handle:null,granted_scopes:[],expires_at:'2027-01-01T00:00:00Z'};
const composition:Composition={schema_version:1,template:'did_you_know',template_version:1,kind:'graphic',revision_id:id,title:'Fixture',facts:[{id:'fact',text:'Fact',source_url:'https://example.invalid/source'},{id:'context',text:'Context',source_url:'https://example.invalid/source'}],scenes:[{fact_id:'fact',seconds:15}]};
function job(){return {id:other,revision_id:other,state:'queued',version:1,composition:{...composition,revision_id:other},sha256:null,approved_sha256:null,safe_error:null,cancel_requested:false,attempt:1,retry_of_id:null,input_hash:'a'.repeat(64),runtime_hash:null,inspection:null};}
test('control: malformed confirmation rejects and preserves original key',async()=>{
 const path=`/platform-connections/threads/flows/${id}/confirm`,body={external_account_id:choice.external_account_id,reason:'Confirm the exact provider account'},before=keyOf(path,body);
 post.mockResolvedValue({data:{}});
 await expect(recoveredSocialCommand(actor,'post',path,body,key=>platformConnectionApi.confirm('threads',choice,key))).rejects.toThrow();
 expect(keyOf(path,body)).toBe(before);
});
test('wrong-flow confirmation must reject and retain original key',async()=>{
 const path=`/platform-connections/threads/flows/${id}/confirm`,body={external_account_id:choice.external_account_id,reason:'Confirm the exact provider account'},before=keyOf(path,body);
 post.mockResolvedValue({data:{flow_id:other,account:{id:other,publishing_enabled:false}}});
 let rejected=false;try{await recoveredSocialCommand(actor,'post',path,body,key=>platformConnectionApi.confirm('threads',choice,key));}catch{rejected=true;}
 const after=keyOf(path,body);console.log(JSON.stringify({case:'wrong-flow',rejected,keyChanged:after!==before,submittedPath:post.mock.calls[0][0]}));
 expect({rejected,keyUnchanged:after===before}).toEqual({rejected:true,keyUnchanged:true});
});
test('wrong-revision studio create acknowledgement must reject and retain original key',async()=>{
 const path='/studio/jobs',before=keyOf(path,composition);post.mockResolvedValue({data:job()});
 let rejected=false;try{await recoveredSocialCommand(actor,'post',path,composition,key=>studioApi.create(composition,key));}catch{rejected=true;}
 const after=keyOf(path,composition);console.log(JSON.stringify({case:'wrong-studio-revision',rejected,keyChanged:after!==before,submittedPath:post.mock.calls[0][0]}));
 expect({rejected,keyUnchanged:after===before}).toEqual({rejected:true,keyUnchanged:true});
});
test('wrong-plan privacy decision acknowledgement must reject and retain original key',async()=>{
 const path=`/privacy/plans/${id}/decision`,body={decision:'approved',reason:'Independently checked this scope',plan_hash:'a'.repeat(64)},before=keyOf(path,body);
 post.mockResolvedValue({data:{id:other,receipt_id:other,proposed_by:other,policy_key:'fixture',policy_hash:'b'.repeat(64),plan_hash:'c'.repeat(64),evidence:'Other scope',scope:{credentials:[],flows:[],media_assets:[]},decision:'approved',approved_by:actor,execution:null}});
 let rejected=false;try{await recoveredSocialCommand(actor,'post',path,body,key=>privacyApi.command(`/plans/${id}/decision`,body,key));}catch{rejected=true;}
 const after=keyOf(path,body);console.log(JSON.stringify({case:'wrong-plan',rejected,keyChanged:after!==before,submittedPath:post.mock.calls[0][0]}));
 expect({rejected,keyUnchanged:after===before}).toEqual({rejected:true,keyUnchanged:true});
});
