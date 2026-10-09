import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import Etl from '@/app/admin/etl/page';
import api from '@/lib/api/axios';
import type { EtlCommand } from '@/lib/admin/etlDispatch';
import { CommandDetail } from '@/app/admin/etl/commands/[commandId]/CommandDetail';

let mockQuery = '';
let mockAllowed = true;
let mockActor = { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' };
let mockAuthEvent: (() => void) | undefined;
const mockPush = jest.fn(), mockReplace = jest.fn();
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: mockPush, replace: mockReplace }), useSearchParams: () => new URLSearchParams(mockQuery) }));
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true, default: ({ title, children }: {title:string;children:React.ReactNode}) => <main><h1>{title}</h1>{children}</main> }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: mockAllowed, isLoading: false }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ authUser: mockActor, user: mockActor }) }));
jest.mock('@/lib/supabase/client', () => ({ createClient: () => ({ auth: { onAuthStateChange: (fn: () => void) => {mockAuthEvent=fn; return {data:{subscription:{unsubscribe:jest.fn()}}};} } }) }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
const get = api.get as jest.Mock, post = api.post as jest.Mock;
const names = ['treasury','cob','oag','knbs','opendata','cra'];
const timestamp = '2026-10-09T12:00:00Z';
export const batch7Capability = () => ({timestamp:new Date().toISOString(),evidence:'worker_dispatch',available:true,reason:'Dedicated fixture worker ready.',generation:'11111111-1111-4111-8111-111111111111',worker:{status:'ready',last_seen_at:new Date(Date.now()-1000).toISOString(),expires_at:new Date(Date.now()+30000).toISOString()},sources:Object.fromEntries(names.map(source=>[source,{available:source==='oag',reason:source==='oag'?'Supported fixture audit runner.':'No approved mapping.'}]))});
export const batch7Command: EtlCommand = { id:'22222222-2222-4222-8222-222222222222',source:'oag',dry_run:false,status:'queued',version:1,created_at:timestamp,updated_at:timestamp,started_at:null,finished_at:null,job_id:null,outcome:null };
const manual = {available:false,reason:'No calendar execution evidence. No job was accepted.'};
const plan = {timestamp,evidence:'calendar_plan',manual_trigger:manual,summary:{sources_running_today:1,sources_skipping_today:5,total_sources:6,skip_percentage:83.3,efficiency_vs_fixed_schedule:'Calendar only',sources_to_run:[{source:'oag',reason:'Calendar fixture'}],sources_not_running:names.filter(s=>s!=='oag')},sources:Object.fromEntries(names.map(s=>[s,{should_run:s==='oag',reason:s==='oag'?'Calendar fixture':'Deferred',next_run:null,next_reason:'',current_period:'default'}]))};
const health = {timestamp,scheduler_status:'unverified',plan_status:'available',worker_status:'unverified',data_freshness:'unverified',manual_trigger:manual};
let capability: unknown;
export function batch7Mount(node:React.ReactNode=<Etl />) { const qc=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});const wrap=(next:React.ReactNode)=><QueryClientProvider client={qc}>{next}</QueryClientProvider>;const view=render(wrap(node));return {qc,...view,refresh:()=>view.rerender(wrap(React.isValidElement(node)?React.cloneElement(node):node))}; }
beforeEach(() => {
  HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  HTMLDialogElement.prototype.close=function(){this.open=false;};
  jest.clearAllMocks(); mockQuery='';mockAllowed=true;mockActor={id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'};capability=batch7Capability();
  Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
  get.mockImplementation(async (path:string) => ({data:path.endsWith('/schedule')?plan:path.endsWith('/health')?health:path.endsWith('/dispatch')?capability:path.endsWith('/commands')?{entries:[],page:1,page_size:20,total:0,has_more:false}:batch7Command}));
  post.mockResolvedValue({status:202,data:{ok:true,accepted:true,replayed:false,audit_recorded:true,command:batch7Command}});
});

async function readyButton(name='Run Now · oag') {
  const button=await screen.findByRole('button',{name});
  await waitFor(()=>expect(button).toBeEnabled());
  return button;
}
function hidden(value=true) {
  Object.defineProperty(document,'visibilityState',{configurable:true,value:value?'hidden':'visible'});
  act(()=>document.dispatchEvent(new Event('visibilitychange')));
}
function deferred<T>() { let resolve!:(value:T)=>void; const promise=new Promise<T>(done=>{resolve=done;});return {resolve,promise}; }

test.each(['unavailable','stale','malformed'])('%s evidence never enables source controls',async mode=>{
  const fresh=batch7Capability();
  capability=mode==='malformed'?{...fresh,available:'true'}:mode==='stale'?{...fresh,worker:{...fresh.worker,expires_at:new Date(Date.now()-1).toISOString()}}:{...fresh,available:false,generation:null,worker:{status:'unavailable',last_seen_at:null,expires_at:null},sources:Object.fromEntries(names.map(s=>[s,{available:false,reason:'Unavailable.'}]))};
  batch7Mount(); await screen.findByText(mode==='unavailable'?'Dedicated fixture worker ready.':'Worker evidence unavailable or malformed. Controls are disabled.');
  names.forEach(s=>expect(screen.getByRole('button',{name:'Run Now · '+s})).toBeDisabled());
  expect(post).not.toHaveBeenCalled();
});
test('dry run states no publication and a lost response can only recover manually with the same UUID',async()=>{
  post.mockRejectedValueOnce(new Error('Lost response'));
  batch7Mount();fireEvent.click(await readyButton('Dry Run · oag'));
  await screen.findByRole('button',{name:'Recover same intent'});
  expect(post).toHaveBeenCalledTimes(1);
  const first=post.mock.calls[0];
  expect(first[1].dry_run).toBe(true);
  post.mockResolvedValueOnce({status:202,data:{ok:true,accepted:true,replayed:true,audit_recorded:true,command:{...batch7Command,dry_run:true}}});
  fireEvent.click(screen.getByRole('button',{name:'Recover same intent'}));
  await screen.findByText('Original receipt recovered. No second command was accepted.');
  expect(post.mock.calls[1][2].headers['Idempotency-Key']).toBe(first[2].headers['Idempotency-Key']);
  expect(post).toHaveBeenCalledTimes(2);
});
test('a changed intent rotates the key and keeps real-run confirmation explicit',async()=>{
  post.mockRejectedValueOnce(new Error('Lost response'));
  batch7Mount();fireEvent.click(await readyButton('Dry Run · oag'));
  await screen.findByRole('button',{name:'Recover same intent'});
  const key=post.mock.calls[0][2].headers['Idempotency-Key'];
  fireEvent.click(await readyButton());
  expect(post).toHaveBeenCalledTimes(1);
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Confirm Run Now'}));
  await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  expect(post.mock.calls[1][2].headers['Idempotency-Key']).not.toBe(key);
});
test.each(['actor','role','renewal','hidden'])('deferred confirmation cannot cross %s lifetime change',async change=>{
  const view=batch7Mount();fireEvent.click(await readyButton());
  const confirm=within(screen.getByRole('dialog')).getByRole('button',{name:'Confirm Run Now'});
  if(change==='actor') {mockActor={id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'};view.refresh();}
  if(change==='role') {mockAllowed=false;view.refresh();mockAllowed=true;view.refresh();}
  if(change==='renewal') act(()=>mockAuthEvent?.());
  if(change==='hidden') {hidden();hidden(false);}
  fireEvent.click(confirm);
  expect(post).not.toHaveBeenCalled();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
test.each(['actor','role','renewal','hidden','unmount'])('in-flight acceptance cannot publish stale success after %s',async change=>{
  const pending=deferred<unknown>();post.mockReturnValue(pending.promise);
  const view=batch7Mount();fireEvent.click(await readyButton('Dry Run · oag'));
  await screen.findByText('Requesting durable acceptance…');
  const signal=post.mock.calls[0][2].signal;
  if(change==='actor') {mockActor={id:'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'};view.refresh();}
  if(change==='role') {mockAllowed=false;view.refresh();mockAllowed=true;view.refresh();}
  if(change==='renewal') act(()=>mockAuthEvent?.());
  if(change==='hidden') hidden();
  if(change==='unmount') view.unmount();
  expect(signal.aborted).toBe(true);
  await act(async()=>pending.resolve({status:202,data:{ok:true,accepted:true,replayed:false,audit_recorded:true,command:{...batch7Command,dry_run:true}}}));
  expect(screen.queryByText('Command accepted. Queued acceptance is not completed work.')).not.toBeInTheDocument();
  expect(view.qc.getQueriesData({queryKey:['admin','etl-command']}).every(([,value])=>value===undefined)).toBe(true);
});
test('visibility interruption retains the submitted intent for explicit same-key recovery',async()=>{
  const pending=deferred<unknown>();post.mockReturnValueOnce(pending.promise);
  batch7Mount();fireEvent.click(await readyButton('Dry Run · oag'));
  const key=post.mock.calls[0][2].headers['Idempotency-Key'];
  hidden();hidden(false);
  const recover=await screen.findByRole('button',{name:'Recover same intent'});
  post.mockResolvedValueOnce({status:202,data:{ok:true,accepted:true,replayed:true,audit_recorded:true,command:{...batch7Command,dry_run:true}}});
  fireEvent.click(recover);
  await screen.findByText('Original receipt recovered. No second command was accepted.');
  expect(post.mock.calls[1][2].headers['Idempotency-Key']).toBe(key);
});
test.each([401,403])('mutation %s removes capability/history and cannot expose a private failure',async status=>{
  post.mockRejectedValue({response:{status,data:{detail:'PRIVATE_DIAGNOSTIC'}}});
  const view=batch7Mount();fireEvent.click(await readyButton('Dry Run · oag'));
  await screen.findByText('Administrator access expired. Renew your session to verify access.');
  expect(screen.getByRole('button',{name:'Run Now · oag'})).toBeDisabled();
  expect(screen.queryByText('PRIVATE_DIAGNOSTIC')).not.toBeInTheDocument();
  expect(view.qc.getQueriesData({queryKey:['admin','etl-dispatch']}).every(([,value])=>value===undefined)).toBe(true);
});
test('initial hidden page makes no private reads and resumes with current capability',async()=>{
  hidden();batch7Mount();await act(async()=>{});
  expect(get).not.toHaveBeenCalled();
  hidden(false);await readyButton();
});
test('hostile command query is bounded and replaced before it reaches transport',async()=>{
  mockQuery='source=evil&status=wat&page=10001&page_size=999';
  batch7Mount();await screen.findByText('No commands match this page.');
  const call=get.mock.calls.find(([path])=>path.endsWith('/commands'));
  expect(call[1].params).toEqual({page:1,page_size:20});
  expect(mockReplace).toHaveBeenCalledWith('/admin/etl');
});
test.each(['mismatch','failed','interrupted'])('detail %s is truthful and offers receipt reads only',async state=>{
  const terminal={...batch7Command,status:state,version:3,started_at:timestamp,finished_at:timestamp,outcome:state==='failed'?'failed':'execution_unverified'};
  get.mockResolvedValue({data:state==='mismatch'?{...batch7Command,id:'33333333-3333-4333-8333-333333333333'}:terminal});
  batch7Mount(<CommandDetail commandId={batch7Command.id}/>);
  await screen.findByText(state==='mismatch'?'Could not verify this command receipt. Refresh to retry.':state==='failed'?'Failed — execution did not complete.':'Interrupted — execution unverified. Do not automatically repeat.');
  expect(screen.queryByRole('link',{name:/ingestion observation/})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/Run Now|Recover same intent/})).not.toBeInTheDocument();
});
test('active detail polls only while visible, then stops after terminal or error',async()=>{
  jest.useFakeTimers();
  let command={...batch7Command};
  get.mockImplementation(async()=>({data:command}));
  batch7Mount(<CommandDetail commandId={batch7Command.id}/>);
  await screen.findByText('Queued — accepted, awaiting execution.');
  const initial=get.mock.calls.length;
  await act(async()=>{jest.advanceTimersByTime(5001);});expect(get.mock.calls.length).toBe(initial+1);
  hidden();await act(async()=>{jest.advanceTimersByTime(20000);});expect(get.mock.calls.length).toBe(initial+1);
  command={...batch7Command,status:'failed',version:2,finished_at:timestamp,outcome:'failed'} as typeof batch7Command;
  hidden(false);await screen.findByText('Failed — execution did not complete.');
  const terminal=get.mock.calls.length;await act(async()=>{jest.advanceTimersByTime(20000);});expect(get).toHaveBeenCalledTimes(terminal);
  get.mockRejectedValue({response:{status:503}});
  fireEvent.click(screen.getByRole('button',{name:'Refresh receipt'}));
  await screen.findByText('Could not verify this command receipt. Refresh to retry.');
  const failed=get.mock.calls.length;await act(async()=>{jest.advanceTimersByTime(20000);});expect(get).toHaveBeenCalledTimes(failed);
  expect(screen.queryByText('Failed — execution did not complete.')).not.toBeInTheDocument();
});
afterEach(() => jest.useRealTimers());
test('fresh supported worker offers an explicit real-run confirmation and durable queued receipt', async () => {
  batch7Mount();
  const run=await screen.findByRole('button',{name:'Run Now · oag'});
  await waitFor(()=>expect(run).toBeEnabled());
  fireEvent.click(run);
  expect(post).not.toHaveBeenCalled();
  const dialog=screen.getByRole('dialog');
  expect(within(dialog).getByText(/publication/)).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole('button',{name:'Confirm Run Now'}));
  await screen.findByText('Command accepted. Queued acceptance is not completed work.');
  expect(post).toHaveBeenCalledTimes(1);
  expect(post.mock.calls[0][0]).toBe('/admin/etl/trigger/oag');
  expect(post.mock.calls[0][1]).toEqual({dry_run:false,dispatch_generation:'11111111-1111-4111-8111-111111111111'});
  expect(post.mock.calls[0][2].headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
  expect(screen.getByRole('link',{name:'View accepted command'})).toHaveAttribute('href',expect.stringContaining(batch7Command.id));
});
