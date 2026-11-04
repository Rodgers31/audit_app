import React from 'react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {fireEvent,render,screen,waitFor,cleanup} from '@testing-library/react';
const mockReact=React, mockReactQuery={QueryClient,QueryClientProvider,...jest.requireActual('@tanstack/react-query')};
const mockApi={get:jest.fn(),post:jest.fn()};
const mockActor={id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'};
const mockPush=jest.fn(),mockReplace=jest.fn();
jest.mock('next/navigation',()=>({useRouter:()=>({push:mockPush,replace:mockReplace}),useSearchParams:()=>new URLSearchParams()}));
jest.mock('@/lib/auth/admin',()=>({useAdmin:()=>({isAdmin:true,isLoading:false})}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({authUser:mockActor,user:mockActor})}));
jest.mock('@/lib/supabase/client',()=>({createClient:()=>({auth:{onAuthStateChange:()=>({data:{subscription:{unsubscribe:jest.fn()}}})}})}));
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:mockApi}));
const names=['treasury','cob','oag','knbs','opendata','cra'];
const generation='11111111-1111-4111-8111-111111111111';
const stamp='2026-11-04T03:00:00Z';
const durable=new Map<string,unknown>();const keys:string[]=[];const clients:QueryClient[]=[];
function fullDocumentReload(){
 cleanup();for(const client of clients.splice(0))client.clear();jest.resetModules();
 // The document's JS module graph is recreated; browser sessionStorage survives.
 jest.doMock('react',()=>mockReact);jest.doMock('@tanstack/react-query',()=>mockReactQuery);
 const Panel=require('@/app/admin/etl/DispatchPanel').default;
 const qc=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0},mutations:{retry:false}}});clients.push(qc);
 return render(<QueryClientProvider client={qc}><Panel/></QueryClientProvider>);
}
beforeEach(()=>{
 sessionStorage.clear();keys.length=0;durable.clear();jest.clearAllMocks();
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
 HTMLDialogElement.prototype.showModal=function(){this.open=true;};HTMLDialogElement.prototype.close=function(){this.open=false;};
 mockApi.get.mockImplementation(async(path:string)=>({data:path.endsWith('/dispatch')?{
  timestamp:new Date().toISOString(),evidence:'worker_dispatch',available:true,reason:'Inert worker ready.',generation,
  worker:{status:'ready',last_seen_at:new Date(Date.now()-1000).toISOString(),expires_at:new Date(Date.now()+30000).toISOString()},
  sources:Object.fromEntries(names.map(s=>[s,{available:s==='oag',reason:'Inert per-source capability.'}]))
 }:path.endsWith('/commands')?{entries:Array.from(durable.values()).reverse(),page:1,page_size:20,total:durable.size,has_more:false}:Array.from(durable.values())[0]}));
 mockApi.post.mockImplementation(async(path:string,body:unknown,options:{headers:Record<string,string>})=>{
  const key=options.headers['Idempotency-Key'];keys.push(key);
  let command=durable.get(key);
  if(!command){command={id:'22222222-2222-4222-8222-'+String(durable.size+1).padStart(12,'0'),source:'oag',dry_run:true,status:'queued',version:1,created_at:stamp,updated_at:stamp,started_at:null,finished_at:null,job_id:null,outcome:null};durable.set(key,command);}
  if(keys.length===1)throw new Error('Acknowledgement lost after durable acceptance');
  return{status:202,data:{ok:true,accepted:true,replayed:durable.size===1,audit_recorded:true,command}};
 });
});
test('same actor full reload recovers original ambiguous command before requesting identical work',async()=>{
 fullDocumentReload();
 const first=await screen.findByRole('button',{name:'Dry Run · oag'});await waitFor(()=>expect(first).toBeEnabled());
 fireEvent.click(first);await screen.findByRole('button',{name:'Recover same intent'});
 expect(keys).toHaveLength(1);expect(durable.size).toBe(1);
 fullDocumentReload();
 const again=await screen.findByRole('button',{name:'Dry Run · oag'});await waitFor(()=>expect(again).toBeEnabled());
 // History retains the accepted command. Repeating the identical operation must
 // recover its original key, rather than create a second durable command.
 await screen.findByText('Queued — accepted, awaiting execution.');
 fireEvent.click(screen.queryByRole('button',{name:'Recover same intent'})??again);
 await waitFor(()=>expect(keys).toHaveLength(2));
 expect(keys[1]).toBe(keys[0]);expect(durable.size).toBe(1);
});

afterEach(()=>{cleanup();for(const client of clients.splice(0))client.clear();jest.restoreAllMocks();});
const recoveryNotice='Browser command recovery is unavailable. Keep this tab open and reconcile the unconfirmed command before starting another.';
const storagePrefix='auditgava.etl.submitted-intent.v1:';
const originalIntent={source:'oag',dry_run:true,key:'44444444-4444-4444-8444-444444444444',generation};
const retained=()=>({version:1,actorId:mockActor.id,intent:originalIntent});
async function refusedWithoutPost(){
  await screen.findByText(recoveryNotice);
  for(const name of names){
    expect(screen.getByRole('button',{name:'Dry Run · '+name})).toBeDisabled();
    expect(screen.getByRole('button',{name:'Run Now · '+name})).toBeDisabled();
  }
  expect(mockApi.post).not.toHaveBeenCalled();
}
test('unreadable browser command journal visibly refuses every new command',async()=>{
 fullDocumentReload();cleanup();for(const client of clients.splice(0))client.clear();
 jest.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw new Error('private storage error');});
 fullDocumentReload();await refusedWithoutPost();expect(screen.queryByText('private storage error')).not.toBeInTheDocument();
});
test.each(['{','null','[]',JSON.stringify({...retained(),version:true}),JSON.stringify({...retained(),actorId:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'}),JSON.stringify({...retained(),intent:{...originalIntent,dry_run:1}}),JSON.stringify({...retained(),intent:{...originalIntent,source:'unsupported'}}),JSON.stringify({...retained(),extra:1}),'x'.repeat(2049)].map((raw,index)=>({case:'malformed-'+index,raw})))('malformed retained command journal refuses before a POST: $case',async({raw})=>{
 sessionStorage.setItem(storagePrefix+mockActor.id,raw);fullDocumentReload();await refusedWithoutPost();
});
test('quota failure prevents a new durable command request',async()=>{
 fullDocumentReload();const button=await screen.findByRole('button',{name:'Dry Run · oag'});await waitFor(()=>expect(button).toBeEnabled());
 jest.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('quota');});
 fireEvent.click(button);await refusedWithoutPost();
});
test('failed journal readback prevents POST and preserves the stored original identity',async()=>{
 fullDocumentReload();const button=await screen.findByRole('button',{name:'Dry Run · oag'});await waitFor(()=>expect(button).toBeEnabled());
 const originalGet=Storage.prototype.getItem;let wrote=false;const originalSet=Storage.prototype.setItem;
 jest.spyOn(Storage.prototype,'setItem').mockImplementation(function(this:Storage,key:string,value:string){originalSet.call(this,key,value);wrote=true;});
 jest.spyOn(Storage.prototype,'getItem').mockImplementation(function(this:Storage,key:string){return wrote&&key===storagePrefix+mockActor.id?null:originalGet.call(this,key);});
 fireEvent.click(button);await refusedWithoutPost();
 const stored=originalGet.call(sessionStorage,storagePrefix+mockActor.id);expect(stored).not.toBeNull();expect(JSON.parse(stored!).intents[0].key).toMatch(/^[0-9a-f-]{36}$/);
});
test('a late acknowledgement cannot clear another actor or a different retained key',()=>{
 fullDocumentReload();const journal=require('@/app/admin/etl/submittedIntent');const second='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
 journal.rememberSubmittedIntent(mockActor.id,originalIntent);journal.rememberSubmittedIntent(second,{...originalIntent,key:'55555555-5555-4555-8555-555555555555'});
 journal.clearSubmittedIntent(mockActor.id,'66666666-6666-4666-8666-666666666666');expect(journal.submittedIntent(mockActor.id)).toEqual(originalIntent);
 journal.clearSubmittedIntent(mockActor.id,originalIntent.key);expect(journal.submittedIntent(mockActor.id)).toBeNull();expect(journal.submittedIntent(second).key).toBe('55555555-5555-4555-8555-555555555555');
});
