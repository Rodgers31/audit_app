import api from '@/lib/api/axios';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import fixtures from '@/tests/socialAcknowledgementContractEdges.json';
import { Composition, studioApi } from '@/lib/api/socialStudio';
import { privacyApi } from '@/lib/api/socialPrivacy';
import { recoveredSocialCommand, socialCommandIdentity, socialCommandKey } from '@/lib/api/socialCommandRecovery';
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{post:jest.fn(),get:jest.fn()}}));
const send=api.post as jest.Mock,actor='00000000-0000-4000-8000-000000000001',id='00000000-0000-4000-8000-000000000011',other='00000000-0000-4000-8000-000000000012',asset='abcdefab-cdef-4abc-8def-abcdefabcdef';
const base=fixtures.cases.find(row=>row.name==='studio-unmodified')!.normalized!;
const job=(composition:unknown)=>({id:other,revision_id:id,state:'queued',version:1,composition,input_hash:'a'.repeat(64),runtime_hash:null,sha256:null,inspection:null,approved_sha256:null,safe_error:null,cancel_requested:false,attempt:1,retry_of_id:null});
beforeEach(()=>{jest.clearAllMocks();sessionStorage.clear();});
test('the independent oracle is bound to shipping Python/Pydantic/image and actual current model sources',()=>{
 expect(fixtures.runtime.python.startsWith('3.12.16 ')).toBe(true);expect(fixtures.runtime.pydantic).toBe('2.14.2');expect(fixtures.image_id).toBe('sha256:bc6b9576f5d8c1b4b1797fd72a629c244499c220686d1aa433a40db55a93da9a');
 for(const [file,hash] of Object.entries(fixtures.sources))expect(createHash('sha256').update(readFileSync(resolve(__dirname,'../../../../backend',file))).digest('hex')).toBe(hash);
});
test.each(fixtures.cases.filter(row=>row.name.startsWith('unicode-')))('shipping Text projection $name preserves raw request and exact retry identity',async row=>{
 const body=row.raw as unknown as Composition,path='/studio/jobs',identity=socialCommandIdentity(actor,'post',path,body),original=socialCommandKey(actor,identity);send.mockResolvedValue({data:job(row.normalized??base)});
 const call=recoveredSocialCommand(actor,'post',path,body,key=>studioApi.create(body,key));
 if(row.normalized!==null){await expect(call).resolves.toBeDefined();expect(JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries).toHaveLength(0);}
 else{await expect(call).rejects.toBeDefined();expect(socialCommandKey(actor,identity)).toBe(original);}
 expect(send.mock.calls[0][1]).toEqual(body);expect(send.mock.calls[0][2].headers['Idempotency-Key']).toBe(original);
});
test.each(fixtures.cases.filter(row=>row.name.startsWith('uuid-')))('shipping UUID projection $name preserves raw request and exact retry identity',async row=>{
 const body=row.raw,path='/privacy/plans',identity=socialCommandIdentity(actor,'post',path,body),original=socialCommandKey(actor,identity),normalized=row.normalized as {receipt_id:string;policy_key:string;policy_hash:string;evidence:string;media_assets:string[]}|null;
 send.mockResolvedValue({data:{id:original,receipt_id:other,proposed_by:actor,policy_key:'fixture',policy_hash:'a'.repeat(64),plan_hash:'b'.repeat(64),evidence:'Independently reviewed scope.',scope:{credentials:[],flows:[],media_assets:[{id:normalized?.media_assets[0]??asset,scope_hash:'c'.repeat(64)}]},decision:'pending_review',approved_by:null,execution:null}});
 const call=recoveredSocialCommand(actor,'post',path,body,key=>privacyApi.command('/plans',body,key,{actor}));
 if(normalized!==null){await expect(call).resolves.toBeDefined();expect(JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries).toHaveLength(0);}
 else{await expect(call).rejects.toBeDefined();expect(socialCommandKey(actor,identity)).toBe(original);}
 expect(send.mock.calls[0][1]).toEqual(body);expect(send.mock.calls[0][2].headers['Idempotency-Key']).toBe(original);
});
test('legitimate text trimming does not equate changed facts or titles',async()=>{
 const row=fixtures.cases.find(row=>row.name==='studio-title-space')!,body=row.raw as unknown as Composition,path='/studio/jobs',identity=socialCommandIdentity(actor,'post',path,body),original=socialCommandKey(actor,identity);
 send.mockResolvedValue({data:job({...row.normalized,title:'A different meaning'})});await expect(recoveredSocialCommand(actor,'post',path,body,key=>studioApi.create(body,key))).rejects.toBeDefined();expect(socialCommandKey(actor,identity)).toBe(original);
 send.mockResolvedValue({data:job({...row.normalized,facts:[{id:'fact',text:'Different fact',source_url:'https://fixture.invalid/source'},{id:'context',text:'Context',source_url:'https://fixture.invalid/source'}]})});await expect(recoveredSocialCommand(actor,'post',path,body,key=>studioApi.create(body,key))).rejects.toBeDefined();expect(socialCommandKey(actor,identity)).toBe(original);
});

test('a lost text response retries the exact raw body/key before accepting its canonical ACK',async()=>{
 const row=fixtures.cases.find(row=>row.name==='studio-title-space')!,body=row.raw as unknown as Composition,path='/studio/jobs',identity=socialCommandIdentity(actor,'post',path,body),original=socialCommandKey(actor,identity);
 send.mockRejectedValueOnce(new Error('Unconfirmed response')).mockResolvedValueOnce({data:job(row.normalized)});
 await expect(recoveredSocialCommand(actor,'post',path,body,key=>studioApi.create(body,key))).rejects.toBeDefined();
 await expect(recoveredSocialCommand(actor,'post',path,body,key=>studioApi.create(body,key))).resolves.toBeDefined();
 for(const call of send.mock.calls){expect(call[1]).toEqual(body);expect(call[2].headers['Idempotency-Key']).toBe(original);}
 expect(JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries).toHaveLength(0);
});
test('canonical proposal UUID ACKs preserve raw identifiers and original key through uncertainty and wrong semantics',async()=>{
 const body={receipt_id:'urn:uuid:'+asset.toUpperCase(),policy_key:'fixture',policy_hash:'a'.repeat(64),evidence:'Independently reviewed scope.',erase_credentials:['{'+asset.toUpperCase()+'}'],erase_flows:[asset.replaceAll('-','').toUpperCase()],media_assets:[asset.toUpperCase()]},path='/privacy/plans',identity=socialCommandIdentity(actor,'post',path,body),original=socialCommandKey(actor,identity);
 const wire={id:original,receipt_id:asset,proposed_by:actor,policy_key:body.policy_key,policy_hash:body.policy_hash,plan_hash:'b'.repeat(64),evidence:body.evidence,scope:{credentials:[{id:asset,version:2}],flows:[{id:asset,content_hash:'c'.repeat(64),identity_hash:'d'.repeat(64)}],media_assets:[{id:asset,scope_hash:'e'.repeat(64)}]},decision:'pending_review',approved_by:null,execution:null};
 send.mockRejectedValueOnce(new Error('Unconfirmed response')).mockResolvedValueOnce({data:{...wire,scope:{...wire.scope,media_assets:[{id:other,scope_hash:'e'.repeat(64)}]}}}).mockResolvedValueOnce({data:wire});
 const run=()=>recoveredSocialCommand(actor,'post',path,body,key=>privacyApi.command('/plans',body,key,{actor}));
 await expect(run()).rejects.toBeDefined();await expect(run()).rejects.toBeDefined();expect(socialCommandKey(actor,identity)).toBe(original);await expect(run()).resolves.toBeDefined();
 for(const call of send.mock.calls){expect(call[1]).toEqual(body);expect(call[2].headers['Idempotency-Key']).toBe(original);}
 expect(JSON.parse(sessionStorage.getItem('auditgava.social.commands.v1:'+actor)!).entries).toHaveLength(0);
});
