import api from '@/lib/api/axios';
import { recoveredSocialCommand, recoverGeneratedRulePath, socialCommandIdentity, socialCommandKey } from '@/lib/api/socialCommandRecovery';
import { studioApi, decodeJob, Composition } from '@/lib/api/socialStudio';
import { post } from '@/tests/socialFixtures';
import '@/tests/socialRecoveryCrypto';
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{post:jest.fn(),get:jest.fn()}}));
const send=api.post as jest.Mock;
const actor='00000000-0000-4000-8000-000000000001', otherActor='00000000-0000-4000-8000-000000000002';
const sourceId='00000000-0000-4000-8000-000000000011', assetId='00000000-0000-4000-8000-000000000012', nextRevision='00000000-0000-4000-8000-000000000013', sha='a'.repeat(64);
const first='/automation/rules/00000000-0000-4000-8000-000000000021/versions', second='/automation/rules/00000000-0000-4000-8000-000000000022/versions';
const ruleBody={expected_version:0,name:'Independent reviewed rule'};
beforeEach(()=>{jest.clearAllMocks();sessionStorage.clear();});

test.each(['actor','method','body','version'] as const)('generated-rule recovery cannot borrow a different %s',kind=>{
 socialCommandKey(actor,socialCommandIdentity(actor,'post',first,ruleBody));
 const result=recoverGeneratedRulePath(kind==='actor'?otherActor:actor,kind==='method'?'patch':'post',second,kind==='body'?{...ruleBody,name:'Different'}:kind==='version'?{...ruleBody,expected_version:1}:ruleBody);
 expect(result).toBe(second);
});
test('generated-rule recovery preserves exact path and key; ambiguous matches refuse',()=>{
 const original=socialCommandKey(actor,socialCommandIdentity(actor,'post',first,ruleBody));
 expect(recoverGeneratedRulePath(actor,'post',second,ruleBody)).toBe(first);
 expect(socialCommandKey(actor,socialCommandIdentity(actor,'post',first,ruleBody))).toBe(original);
 socialCommandKey(actor,socialCommandIdentity(actor,'post',second,ruleBody));
 expect(()=>recoverGeneratedRulePath(actor,'post',second,ruleBody)).toThrow();
});

const composition:Composition={schema_version:1,template:'did_you_know',template_version:1,kind:'graphic',revision_id:sourceId,title:'Fixture',facts:[{id:'fact',text:'Fact',source_url:'https://example.invalid/report'},{id:'context',text:'Context',source_url:'https://example.invalid/report'}],scenes:[{fact_id:'fact',seconds:15}]};
const ready={id:sourceId,revision_id:sourceId,state:'ready',version:3,composition,input_hash:sha,runtime_hash:sha,sha256:sha,approved_sha256:sha,safe_error:null,cancel_requested:false,attempt:1,retry_of_id:null,inspection:{sha256:sha,mime_type:'image/png',byte_size:4,width:720,height:1280,duration_ms:null}};
const source=post({revision_id:sourceId,version:7}),wire={...source,version:8,revision_id:nextRevision,document:{...source.document,master:{...source.document.master,media:[...source.document.master.media,{asset_id:assetId,alt_text:'Fact Context',caption_asset_id:null}]}}};

test.each([{title:'An unrelated title'},{content_type:'correction'},{origin_type:'generated'}])('attachment acknowledgement preserves unchanged source metadata %#',async change=>{
 const body={expected_version:7,asset_id:assetId},path=`/studio/jobs/${sourceId}/attach`,identity=socialCommandIdentity(actor,'post',path,body),before=socialCommandKey(actor,identity);
 send.mockResolvedValue({data:{...wire,...change}});
 let rejected=false;
 try { await recoveredSocialCommand(actor,'post',path,body,key=>studioApi.attach(decodeJob(ready),assetId,7,key,source)); } catch { rejected=true; }
 const after=socialCommandKey(actor,identity);
 console.log(JSON.stringify({case:'attachment-source-metadata',field:Object.keys(change)[0],rejected,keyRetained:after===before}));
 expect({rejected,keyRetained:after===before}).toEqual({rejected:true,keyRetained:true});
});
test('attachment accepts the current backend exact append transition',async()=>{
 const body={expected_version:7,asset_id:assetId},path=`/studio/jobs/${sourceId}/attach`;
 send.mockResolvedValue({data:wire});
 await expect(recoveredSocialCommand(actor,'post',path,body,key=>studioApi.attach(decodeJob(ready),assetId,7,key,source))).resolves.toMatchObject({id:source.id,version:8});
 expect(JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries).toEqual([]);
});
