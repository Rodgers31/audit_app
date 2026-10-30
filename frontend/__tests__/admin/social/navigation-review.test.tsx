import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import SocialComposer from '@/components/admin/social/SocialComposer';
import {SocialEditorPage} from '@/components/admin/social/SocialWorkspace';
import AdminPageShell from '@/components/admin/AdminPageShell';
import AdminNav from '@/components/admin/AdminNav';
import StatusPage from '@/app/status/page';
import NavTrailTracker from '@/lib/navigation/NavTrailTracker';
import SmartBackLink from '@/lib/navigation/SmartBackLink';
import api from '@/lib/api/axios';
import {accounts,post,system} from '../../../tests/socialFixtures';

let mockActor='00000000-0000-4000-8000-000000000001';
let mockAdmin=true;
let mockPath:string|null|undefined;
const mockBack=jest.fn(()=>window.history.back());
const mockPush=jest.fn();
jest.mock('next/navigation',()=>({useRouter:()=>({back:mockBack,push:mockPush}),usePathname:()=>mockPath===undefined?window.location.pathname:mockPath,useSearchParams:()=>new URLSearchParams(window.location.search)}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:mockActor}})}));
jest.mock('@/lib/auth/admin',()=>({useAdmin:()=>({isAdmin:mockAdmin}),AdminGuard:({children}:{children:React.ReactNode})=>mockAdmin?children:null}));
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{get:jest.fn(),post:jest.fn(),patch:jest.fn()}}));
const clients:QueryClient[]=[];
const sleep=async()=>act(async()=>{await new Promise(resolve=>setTimeout(resolve,65));});
function provider(children:React.ReactNode){const c=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(c);return <QueryClientProvider client={c}>{children}</QueryClientProvider>;}
function seed(){window.history.replaceState({},'','/admin/social?page=4');window.history.pushState({},'','/admin/social/review');sessionStorage.clear();}
function trail(){sessionStorage.setItem('auditgava-nav-trail',JSON.stringify([{pathname:'/admin/social',search:'?page=4',ts:1},{pathname:'/admin/social/review',search:'',ts:2}]));}
function composer(){seed();const tree=render(provider(<><NavTrailTracker/><AdminPageShell title='Review draft' back={{href:'/admin/social',label:'Back to queue'}}><SocialComposer initialPost={post()} accounts={accounts} system={system}/></AdminPageShell></>));fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'Independent unsaved local edit'}});trail();return tree;}
beforeEach(()=>{jest.clearAllMocks();mockActor='00000000-0000-4000-8000-000000000001';mockAdmin=true;mockPath=undefined;mockBack.mockClear();mockPush.mockClear();(api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.includes('/accounts')?{accounts}:url.includes('/system/status')?system:post()}));});
afterEach(async()=>{cleanup();clients.forEach(c=>c.clear());clients.length=0;await sleep();jest.restoreAllMocks();sessionStorage.clear();});

it('one accepted dirty SmartBackLink action asks once and restores original queue query',async()=>{
 composer();const confirm=jest.spyOn(window,'confirm').mockReturnValue(true);fireEvent.click(screen.getByRole('link',{name:'← Back to queue'}));await sleep();
 expect(mockBack).toHaveBeenCalledTimes(1);expect(window.location.pathname+window.location.search).toBe('/admin/social?page=4');expect(confirm).toHaveBeenCalledTimes(1);
});
it('cancelled dirty SmartBackLink asks once and keeps draft and editor route',async()=>{
 composer();const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);fireEvent.click(screen.getByRole('link',{name:'← Back to queue'}));await sleep();
 expect(confirm).toHaveBeenCalledTimes(1);expect(mockBack).not.toHaveBeenCalled();expect(window.location.pathname).toBe('/admin/social/review');expect(screen.getByLabelText('Post text')).toHaveValue('Independent unsaved local edit');
});
it.each([{ctrlKey:true},{metaKey:true},{shiftKey:true},{button:1}])('modified dirty back click %j leaves current history and does not prompt',async modifiers=>{
 composer();const confirm=jest.spyOn(window,'confirm').mockReturnValue(true);fireEvent.click(screen.getByRole('link',{name:'← Back to queue'}),modifiers);await sleep();
 expect(mockBack).not.toHaveBeenCalled();expect(confirm).not.toHaveBeenCalled();expect(window.location.pathname).toBe('/admin/social/review');
});
it('accepting a Back link cannot be vetoed by an unexpected second prompt',async()=>{
 composer();const confirm=jest.spyOn(window,'confirm').mockReturnValueOnce(true).mockReturnValue(false);fireEvent.click(screen.getByRole('link',{name:'← Back to queue'}));await sleep();
 expect(confirm).toHaveBeenCalledTimes(1);expect(window.location.pathname+window.location.search).toBe('/admin/social?page=4');
});
it('a successful actual Composer save retires both navigation guards',async()=>{
 composer();const original=post();const saved=post({version:2,revision_id:'00000000-0000-4000-8000-000000000041',document:{...original.document,master:{...original.document.master,text:'Independent unsaved local edit'}}});
 (api.patch as jest.Mock).mockResolvedValue({data:saved});const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);
 fireEvent.click(screen.getByRole('button',{name:'Save draft'}));await screen.findByText(/Draft saved. Nothing has been queued for publication/);trail();
 fireEvent.click(screen.getByRole('link',{name:'← Back to queue'}));await sleep();expect(confirm).not.toHaveBeenCalled();expect(window.location.pathname+window.location.search).toBe('/admin/social?page=4');
});
it.each([false,true])('actual keyed editor retires departing actor guard (existing=%s)',async existing=>{
 seed();const c=new QueryClient({defaultOptions:{queries:{retry:false}}});clients.push(c);
 const tree=render(<QueryClientProvider client={c}><NavTrailTracker/><SocialEditorPage postId={existing?post().id:undefined}/></QueryClientProvider>);
 const field=await screen.findByLabelText('Post text');fireEvent.change(field,{target:{value:'Actor A private unsaved edit'}});
 mockActor='00000000-0000-4000-8000-000000000002';tree.rerender(<QueryClientProvider client={c}><NavTrailTracker/><SocialEditorPage postId={existing?post().id:undefined}/></QueryClientProvider>);
 await waitFor(()=>expect(screen.getByLabelText('Post text')).not.toHaveValue('Actor A private unsaved edit'));
 const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);act(()=>window.history.back());await sleep();expect(confirm).not.toHaveBeenCalled();
});
it('caller cancellation on SmartBackLink is respected without traversal',()=>{
 seed();trail();render(<SmartBackLink href='/admin/social' onClick={event=>event.preventDefault()}>Caller back</SmartBackLink>);fireEvent.click(screen.getByRole('link',{name:'Caller back'}));expect(mockBack).not.toHaveBeenCalled();
});
it('menu closes after route changes and status is the sole active primary link',()=>{
 window.history.replaceState({},'','/admin/social/new');const tree=render(<AdminNav/>);fireEvent.click(screen.getByRole('button',{name:'Menu'}));expect(screen.getByRole('button',{name:'Menu'})).toHaveAttribute('aria-expanded','true');
 window.history.pushState({},'','/status');tree.rerender(<AdminNav/>);expect(screen.getByRole('button',{name:'Menu'})).toHaveAttribute('aria-expanded','false');
 expect(screen.getByRole('link',{name:'System status'})).toHaveAttribute('aria-current','page');expect(screen.queryByRole('navigation',{name:'Social workspace'})).not.toBeInTheDocument();
});
it('unknown pathname keeps a working but unselected admin menu',()=>{
 mockPath=null;render(<AdminNav/>);expect(screen.getByRole('navigation',{name:'Admin navigation'})).toBeInTheDocument();expect(screen.getAllByRole('link').filter(n=>n.getAttribute('aria-current')==='page')).toHaveLength(0);
});
it.each(['loading','error','loaded'] as const)('status shared navigation remains usable on %s state',async mode=>{
 window.history.replaceState({},'','/status');if(mode==='loading')(api.get as jest.Mock).mockImplementation(()=>new Promise(()=>{}));
 if(mode==='error')(api.get as jest.Mock).mockRejectedValue(new Error('offline test refusal'));
 if(mode==='loaded')(api.get as jest.Mock).mockResolvedValue({data:{schema_version:2,status:'unknown',checked_at:new Date().toISOString(),database:{},sources:{},source_checks_in_progress:false,auto_seeder:null,execution:{owner:'dedicated',status:'not_observed',evidence_url:'/admin/etl'},alerts:[],summary:{errors:0,warnings:0,total_alerts:0}}});
 render(provider(<StatusPage/>));expect(screen.getByRole('navigation',{name:'Admin navigation'})).toBeInTheDocument();expect(screen.getByRole('link',{name:'System status'})).toHaveAttribute('aria-current','page');
 if(mode==='error')expect(await screen.findByRole('button',{name:'Retry'})).toBeInTheDocument();if(mode==='loaded')expect(await screen.findByText('Checks incomplete')).toBeInTheDocument();
});
it('status refuses to mount navigation or fetch private observations for a revoked admin',()=>{
 mockAdmin=false;render(provider(<StatusPage/>));expect(screen.queryByRole('navigation',{name:'Admin navigation'})).not.toBeInTheDocument();expect(api.get).not.toHaveBeenCalled();
});

it('a caller-cancelled accepted link cannot grant a later browser traversal permission',async()=>{
 composer();render(<SmartBackLink href='/admin/social' onClick={event=>event.preventDefault()}>Caller guarded back</SmartBackLink>);
 const confirm=jest.spyOn(window,'confirm').mockReturnValue(true);fireEvent.click(screen.getByRole('link',{name:'Caller guarded back'}));await sleep();
 expect(mockBack).not.toHaveBeenCalled();const calls=confirm.mock.calls.length;confirm.mockReturnValue(false);act(()=>window.history.back());await sleep();
 expect(confirm).toHaveBeenCalledTimes(calls+1);expect(window.location.pathname).toBe('/admin/social/review');expect(screen.getByLabelText('Post text')).toHaveValue('Independent unsaved local edit');
});
it('failed save retains both local edits and dirty browser-navigation protection',async()=>{
 composer();(api.patch as jest.Mock).mockRejectedValue(new Error('Owned save failure'));fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await waitFor(()=>expect(api.patch).toHaveBeenCalledTimes(1));await sleep();const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);act(()=>window.history.back());await sleep();
 expect(confirm).toHaveBeenCalledTimes(1);expect(window.location.pathname).toBe('/admin/social/review');expect(screen.getByLabelText('Post text')).toHaveValue('Independent unsaved local edit');
});

it('deep-link back fallback still refuses leaving an unsaved composer when cancelled',async()=>{
 composer();sessionStorage.clear();const confirm=jest.spyOn(window,'confirm').mockReturnValue(false);
 const allowed=fireEvent.click(screen.getByRole('link',{name:'← Back to queue'}));await sleep();
 expect(allowed).toBe(false);expect(confirm).toHaveBeenCalledTimes(1);expect(mockBack).not.toHaveBeenCalled();expect(window.location.pathname).toBe('/admin/social/review');
});
it('a nonmoving accepted traversal does not authorize later edits on the same draft',async()=>{
 composer();mockBack.mockImplementationOnce(()=>{});const confirm=jest.spyOn(window,'confirm').mockReturnValue(true);
 fireEvent.click(screen.getByRole('link',{name:'← Back to queue'}));await sleep();expect(window.location.pathname).toBe('/admin/social/review');
 fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'A later edit was never authorized to leave'}});confirm.mockReturnValue(false);act(()=>window.history.back());await sleep();
 expect(confirm).toHaveBeenCalledTimes(2);expect(window.location.pathname).toBe('/admin/social/review');
});
it.each(['actor','draft'] as const)('a nonmoving accepted traversal cannot leak to another %s',async change=>{
 seed();const id=post().id;const other='00000000-0000-4000-8000-000000000011';
 (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.includes('/accounts')?{accounts}:url.includes('/system/status')?system:post({id:url.endsWith(other)?other:id})}));
 const c=new QueryClient({defaultOptions:{queries:{retry:false}}});clients.push(c);
 const content=(postId:string)=><QueryClientProvider client={c}><NavTrailTracker/><AdminPageShell title='Review' back={{href:'/admin/social',label:'Back to queue'}}><SocialEditorPage postId={postId}/></AdminPageShell></QueryClientProvider>;
 const tree=render(content(id));fireEvent.change(await screen.findByLabelText('Post text'),{target:{value:'Earlier actor/draft unsaved text'}});trail();
 mockBack.mockImplementationOnce(()=>{});const confirm=jest.spyOn(window,'confirm').mockReturnValue(true);fireEvent.click(screen.getByRole('link',{name:'← Back to queue'}));await sleep();
 if(change==='actor')mockActor='00000000-0000-4000-8000-000000000002';
 if(change==='draft')window.history.replaceState(window.history.state,'','/admin/social/'+other);
 tree.rerender(content(change==='draft'?other:id));await waitFor(()=>expect(screen.getByLabelText('Post text')).not.toHaveValue('Earlier actor/draft unsaved text'));
 fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'New context edits must require their own consent'}});confirm.mockReturnValue(false);act(()=>window.history.back());await sleep();
 expect(confirm).toHaveBeenCalledTimes(2);expect(window.location.pathname).toBe(change==='draft'?'/admin/social/'+other:'/admin/social/review');
});
