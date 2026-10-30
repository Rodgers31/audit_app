// Executable Spec findings retained as product regressions; all transport is mocked.
import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import GenerationPreview from '@/components/admin/social/GenerationPreview';
import api from '@/lib/api/axios';
import {generationApi,decodeSourceRecords} from '@/lib/api/socialGeneration';

let mockActor='actor-A',mockAdmin=true,mockSearch=new URLSearchParams();
jest.mock('next/navigation',()=>({useSearchParams:()=>mockSearch}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:mockActor}})}));
jest.mock('@/lib/auth/admin',()=>({useAdmin:()=>({isAdmin:mockAdmin})}));
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{get:jest.fn(),post:jest.fn(),patch:jest.fn()}}));
const get=api.get as jest.Mock,post=api.post as jest.Mock;
const caps=['pending_bills','national_budget','revenue_by_source'].map(domain=>({domain,financial:true,reports:true,reason:'qualified_native_cells_required'}));
const job=(id:number,domain='pending_bills',change={})=>({id,domain,status:'completed',dry_run:false,started_at:'2026-10-28T10:00:00Z',finished_at:'2026-10-28T10:01:00Z',duration_seconds:60,items_processed:1,items_created:1,items_updated:0,errors:[],error_count:0,diagnostics_redacted:true,created_at:'2026-10-28T10:00:00Z',metadata:{source_mode:'live'},...change});
const source=(selection:any,total=1)=>({...selection,page_size:25,total,record_ids:Array.from({length:Math.min(25,Math.max(0,total-(selection.page-1)*25))},(_,i)=>(selection.reports?900:selection.ingestion_id*10)+(selection.page-1)*25+i),has_more:selection.page*25<total});
const deferred=<T,>()=>{let resolve!:(value:T)=>void,reject!:(error:unknown)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
beforeEach(()=>{jest.clearAllMocks();mockActor='actor-A';mockAdmin=true;mockSearch=new URLSearchParams();
  Object.defineProperty(crypto,'randomUUID',{configurable:true,value:()=> '00000000-0000-4000-8000-000000000123'});
  get.mockImplementation(async(path:string,config:any)=>{
    if(path.endsWith('/capabilities'))return {data:[...caps,{domain:'audits',financial:false,reports:true,reason:'financial_adapter_unavailable'}]};
    if(path.endsWith('/source-records'))return {data:source(config.params)};
    if(path==='/admin/ingestion-jobs')return {data:{jobs:[job(7,config.params.domain),job(8,config.params.domain)],total:2,page:config.params.page,page_size:20,has_more:false}};
    const selected=path.match(/\/admin\/ingestion-jobs\/(\d+)$/);if(selected)return {data:job(Number(selected[1]))};
    throw Error('Unexpected GET '+path);
  });
  post.mockImplementation(async(path:string,body:any)=>path.endsWith('/preview')?{data:{drafts_enabled:true,results:body.record_ids.map((record_id:number)=>({record_id,status:'baseline',reason:'first_observation',source_document_id:3}))}}:{data:{results:[{status:'baseline',post_id:null,sequence:0}]}});
});
function mount(){const qc=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0},mutations:{retry:false}}});const wrap=()=> <QueryClientProvider client={qc}><GenerationPreview/></QueryClientProvider>;return {...render(wrap()),qc,wrap};}
async function choose(id='7'){
  await screen.findByRole('option',{name:/job #7/});
  fireEvent.change(screen.getByLabelText('Completed live job'),{target:{value:id}});
  await waitFor(()=>expect(screen.getByRole('button',{name:'2. Preview without saving'})).toBeEnabled());
}
async function preview(){fireEvent.click(screen.getByRole('button',{name:'2. Preview without saving'}));await screen.findByRole('heading',{name:'Preview outcome'});}
async function detect(){fireEvent.click(screen.getByText('3. Run explicit detection for this preview'));fireEvent.change(screen.getByLabelText('Reason for this manual action'),{target:{value:'Independent explicit source check'}});fireEvent.click(screen.getByRole('button',{name:'Confirm manual detection'}));}

test('normal named selection previews without writes, then reasoned detection retains exact batch and backfill choice',async()=>{
  mount();await choose();
  if(screen.queryByLabelText(/record ids|ingestion id/i))throw Error('PASTED_IDS_REQUIRED');
  await preview();expect(post.mock.calls.map(c=>c[0])).toEqual(['/admin/social/generation/preview']);
  await detect();await waitFor(()=>expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[1][0]).toBe('/admin/social/generation/detect');
  expect(post.mock.calls[1][1]).toEqual({domain:'pending_bills',ingestion_id:7,backfill:false,record_ids:[70],reason:'Independent explicit source check'});
});

test('report/financial switch invalidates preview and resolves extraction IDs rather than reusing financial IDs',async()=>{
  mount();await choose();await preview();
  fireEvent.change(screen.getByLabelText('Content to check'),{target:{value:'report'}});
  await waitFor(()=>expect(screen.queryByRole('heading',{name:'Preview outcome'})).not.toBeInTheDocument());
  await waitFor(()=>expect(screen.getByRole('button',{name:'2. Preview without saving'})).toBeEnabled());
  await preview();expect(post.mock.calls[1][1]).toEqual(expect.objectContaining({reports:true,record_ids:[900]}));
  await detect();await waitFor(()=>expect(post).toHaveBeenCalledTimes(3));
  expect(post.mock.calls[2][0]).toBe('/admin/social/generation/detect-reports');
  expect(post.mock.calls[2][1]).not.toHaveProperty('reports');
});

test('historic backfill stays explicit and requires a new preview',async()=>{
  mount();await choose();await preview();
  fireEvent.click(screen.getByText('Historic draft or evidence refresh'));
  fireEvent.click(screen.getByLabelText('Explicitly preview a backfill or refresh'));
  expect(screen.queryByRole('heading',{name:'Preview outcome'})).not.toBeInTheDocument();
  await preview();expect(post.mock.calls[1][1].backfill).toBe(true);
  expect(screen.getByText(/manual action.*historic draft/)).toBeInTheDocument();
  await detect();await waitFor(()=>expect(post).toHaveBeenCalledTimes(3));expect(post.mock.calls[2][1].backfill).toBe(true);
});

test('runtime-off preview cannot become an enabled detection control',async()=>{
  post.mockImplementation(async(_path,body)=>({data:{drafts_enabled:false,results:body.record_ids.map((record_id:number)=>({record_id,status:'baseline',reason:'first_observation',source_document_id:3}))}}));
  mount();await choose();await preview();
  fireEvent.click(screen.getByText('3. Run explicit detection for this preview'));
  fireEvent.change(screen.getByLabelText('Reason for this manual action'),{target:{value:'A valid independent reason'}});
  expect(screen.getByRole('button',{name:'Confirm manual detection'})).toBeDisabled();
  expect(post).toHaveBeenCalledTimes(1);
});

test('late old record list cannot supply the newly selected job',async()=>{
  const old=deferred<any>(),original=get.getMockImplementation()!;
  get.mockImplementation((path,config)=>path.endsWith('/source-records')&&config.params.ingestion_id===7?old.promise:original(path,config));
  mount();await screen.findByRole('option',{name:/job #7/});fireEvent.change(screen.getByLabelText('Completed live job'),{target:{value:'7'}});
  await waitFor(()=>expect(get.mock.calls.some(([p,c])=>p.endsWith('/source-records')&&c.params.ingestion_id===7)).toBe(true));
  fireEvent.change(screen.getByLabelText('Completed live job'),{target:{value:'8'}});
  await waitFor(()=>expect(screen.getByRole('button',{name:'2. Preview without saving'})).toBeEnabled());
  await act(async()=>old.resolve({data:source({domain:'pending_bills',ingestion_id:7,reports:false,page:1})}));
  await preview();expect(post.mock.calls[0][1]).toEqual(expect.objectContaining({ingestion_id:8,record_ids:[80]}));
});

test('late old preview cannot reappear for a new administrator',async()=>{
  const pending=deferred<any>();post.mockImplementation(()=>pending.promise);
  const view=mount();await choose();fireEvent.click(screen.getByRole('button',{name:'2. Preview without saving'}));
  await waitFor(()=>expect(post).toHaveBeenCalledTimes(1));mockActor='actor-B';view.rerender(view.wrap());
  await act(async()=>pending.resolve({data:{drafts_enabled:true,results:[{record_id:70,status:'eligible_change',reason:'semantic_evidence_changed',source_document_id:3}]}}));
  await waitFor(()=>expect(screen.queryByRole('status',{name:/checking/i})).not.toBeInTheDocument());
  if(screen.queryByRole('heading',{name:'Preview outcome'}))throw Error('LATE_PREVIEW_CROSSED_ACTOR');
});

test('late detection acknowledgement is not presented under a new administrator',async()=>{
  const pending=deferred<any>(),original=post.getMockImplementation()!;
  post.mockImplementation((path,body,...rest)=>path.endsWith('/preview')?original(path,body,...rest):pending.promise);
  const view=mount();await choose();await preview();await detect();await waitFor(()=>expect(post).toHaveBeenCalledTimes(2));
  mockActor='actor-B';view.rerender(view.wrap());
  await act(async()=>pending.resolve({data:{results:[{status:'draft_created',post_id:'00000000-0000-4000-8000-000000000777',sequence:1}]}}));
  await waitFor(()=>expect(screen.queryByRole('heading',{name:'Preview outcome'})).not.toBeInTheDocument());
  if(screen.queryByRole('link',{name:'Review generated draft'}))throw Error('LATE_DETECTION_CROSSED_ACTOR');
});

test.each(['domain','ingestion_id','reports','page'])('actual API rejects a source response bound to different %s',async field=>{
  const selection={domain:'pending_bills',ingestion_id:7,reports:false,page:1};const mismatch:any={domain:'national_budget',ingestion_id:8,reports:true,page:2};
  const response=source({...selection,[field]:mismatch[field]},field==='page'?26:1);
  get.mockResolvedValue({data:response});await expect(generationApi.sourceRecords(selection)).rejects.toThrow();
});

test.each([true,NaN,Infinity,-1,0,2147483648,'1',null])('candidate decoder rejects hostile record ID %s',id=>{
  expect(()=>decodeSourceRecords({...source({domain:'pending_bills',ingestion_id:7,reports:false,page:1}),record_ids:[id]})).toThrow();
});

test('candidate pagination exactly covers all 1000 bounded identities',()=>{
  const all:number[]=[];
  for(let page=1;page<=40;page++){const value=decodeSourceRecords(source({domain:'pending_bills',ingestion_id:7,reports:false,page},1000));all.push(...value.record_ids);}
  expect(all).toEqual(Array.from({length:1000},(_,i)=>70+i));
});
