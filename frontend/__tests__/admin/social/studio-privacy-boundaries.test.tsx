// Independent Standards actor-boundary and held-state controls retained as regressions.
import React from 'react';
import {render,screen,fireEvent,waitFor,cleanup,act} from '@testing-library/react';
import {post as sourcePost} from '../../../tests/socialFixtures';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import AdminLayout from '@/app/admin/layout';
import SocialStudio from '@/components/admin/social/SocialStudio';
import PrivacyReview from '@/components/admin/social/PrivacyReview';
import {socialApi} from '@/lib/api/social';
import {studioApi} from '@/lib/api/socialStudio';
import {privacyApi} from '@/lib/api/socialPrivacy';
let mockActor='actor-one',mockRoles=['admin'];
const mockRouter={push:jest.fn(),replace:jest.fn()};
jest.mock('next/navigation',()=>({useRouter:()=>mockRouter,usePathname:()=>'/admin/social/studio'}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:mockActor,roles:mockRoles},authUser:{id:mockActor},isLoading:false,isAuthenticated:true})}));
jest.mock('@/lib/api/social',()=>({...jest.requireActual('@/lib/api/social'),socialApi:{posts:jest.fn(),post:jest.fn()}}));
jest.mock('@/lib/api/socialStudio',()=>({...jest.requireActual('@/lib/api/socialStudio'),studioApi:{capabilities:jest.fn(),jobs:jest.fn(),calendar:jest.fn(),analytics:jest.fn(),create:jest.fn(),approve:jest.fn(),attach:jest.fn()}}));
jest.mock('@/lib/api/socialPrivacy',()=>({...jest.requireActual('@/lib/api/socialPrivacy'),privacyApi:{queue:jest.fn(),detail:jest.fn(),command:jest.fn()}}));
const clients:QueryClient[]=[];
function mount(node:React.ReactNode){const qc=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0},mutations:{retry:false}}});clients.push(qc);return render(<QueryClientProvider client={qc}><AdminLayout>{node}</AdminLayout></QueryClientProvider>);}
beforeEach(()=>{
 jest.clearAllMocks();mockActor='actor-one';mockRoles=['admin'];
 (socialApi.posts as jest.Mock).mockImplementation(async()=>({posts:[{id:'post-'+mockActor,title:'PRIVATE '+mockActor+' draft'}],total:1,page:1,page_size:25,has_more:false}));
 (studioApi.capabilities as jest.Mock).mockResolvedValue({rendering_available:false,unavailable_reason:'Owned renderer unavailable',analytics_reason:'Collection unavailable',uploads_enabled:false});
 (studioApi.jobs as jest.Mock).mockResolvedValue({jobs:[],page:1,has_more:false});
 (studioApi.calendar as jest.Mock).mockResolvedValue({items:[],page:1,has_more:false});
 (privacyApi.queue as jest.Mock).mockResolvedValue({requests:[],page:1,has_more:false,policies:[],workflow_enabled:false,execution_enabled:false});
});
afterEach(()=>{cleanup();clients.splice(0).forEach(q=>q.clear());});
test('actual shared layout and Studio do not retain previous actor private source posts',async()=>{
 const view=mount(<SocialStudio/>);await screen.findByRole('option',{name:'PRIVATE actor-one draft'});
 mockActor='actor-two';view.rerender(<QueryClientProvider client={clients[0]}><AdminLayout><SocialStudio/></AdminLayout></QueryClientProvider>);
 await waitFor(()=>expect(screen.queryByRole('option',{name:'PRIVATE actor-one draft'})).not.toBeInTheDocument());
 expect(await screen.findByRole('option',{name:'PRIVATE actor-two draft'})).toBeInTheDocument();
});
test('role loss removes the Studio source workflow through actual shared guard',async()=>{
 const view=mount(<SocialStudio/>);await screen.findByRole('option',{name:'PRIVATE actor-one draft'});mockRoles=['viewer'];
 view.rerender(<QueryClientProvider client={clients[0]}><AdminLayout><SocialStudio/></AdminLayout></QueryClientProvider>);
 expect(await screen.findByText('Access Restricted')).toBeInTheDocument();expect(screen.queryByRole('option',{name:'PRIVATE actor-one draft'})).not.toBeInTheDocument();
});
test('unavailable Studio cannot queue media and calendar task performs reads only',async()=>{
 mount(<SocialStudio/>);await screen.findByText('Owned renderer unavailable');expect(screen.getByRole('button',{name:'Queue local render'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Publication calendar'}));
 expect(await screen.findByText('No scheduled publications in this month.')).toBeInTheDocument();expect(screen.queryByLabelText('Source post')).not.toBeInTheDocument();
 expect(screen.queryByRole('heading',{name:'Graphics and short video'})).not.toBeInTheDocument();
 expect(studioApi.create).not.toHaveBeenCalled();expect(studioApi.approve).not.toHaveBeenCalled();expect(studioApi.attach).not.toHaveBeenCalled();
});
test('privacy closed workflow and execution remain disabled and never mutate',async()=>{
 mount(<PrivacyReview/>);expect(await screen.findByText(/Privacy approval is disabled/)).toBeInTheDocument();expect(screen.getByText(/Execution is disabled/)).toBeInTheDocument();expect(privacyApi.command).not.toHaveBeenCalled();expect(screen.queryByRole('button',{name:'Execute approved scope'})).not.toBeInTheDocument();
});
test('privacy read failure never presents an empty queue or leaks transport diagnostics',async()=>{
 (privacyApi.queue as jest.Mock).mockRejectedValue(new Error('PRIVATE_FIXTURE_DIAGNOSTIC'));mount(<PrivacyReview/>);
 await screen.findByRole('alert');expect(screen.queryByText('No privacy requests on this page.')).not.toBeInTheDocument();expect(document.body).not.toHaveTextContent('PRIVATE_FIXTURE_DIAGNOSTIC');expect(privacyApi.command).not.toHaveBeenCalled();
});

test('a late old Studio source read is aborted and cannot replace the next actor',async()=>{
 let resolve!:(value:unknown)=>void,signal:AbortSignal|undefined;
 (socialApi.posts as jest.Mock).mockImplementation((_page,_state,readSignal)=>mockActor==='actor-one'?(signal=readSignal,new Promise(r=>{resolve=r;})):Promise.resolve({posts:[{id:'post-two',title:'PRIVATE actor-two draft'}],has_more:false}));
 const view=mount(<SocialStudio/>);await waitFor(()=>expect(signal).toBeDefined());
 mockActor='actor-two';view.rerender(<QueryClientProvider client={clients[0]}><AdminLayout><SocialStudio/></AdminLayout></QueryClientProvider>);
 expect(await screen.findByRole('option',{name:'PRIVATE actor-two draft'})).toBeInTheDocument();
 expect(signal!.aborted).toBe(true);
 await act(async()=>resolve({posts:[{id:'old',title:'LATE actor-one source'}],has_more:false}));
 expect(screen.queryByRole('option',{name:'LATE actor-one source'})).not.toBeInTheDocument();
 expect(clients[0].getQueryCache().getAll().some(q=>q.queryKey[2]==='actor-one')).toBe(false);
});

test('late render acceptance cannot restore previous actor local notices or selection',async()=>{
 const source=sourcePost({title:'PRIVATE actor-one draft',references:[{url:'https://example.invalid/source',label:'Owned source'}]});
 (socialApi.posts as jest.Mock).mockResolvedValue({posts:[source],has_more:false});
 (socialApi.post as jest.Mock).mockResolvedValue(source);
 (studioApi.capabilities as jest.Mock).mockResolvedValue({rendering_available:true});
 let resolve!:(value:unknown)=>void;(studioApi.create as jest.Mock).mockImplementation(()=>new Promise(r=>{resolve=r;}));
 const view=mount(<SocialStudio/>);await screen.findByRole('option',{name:source.title});
 fireEvent.change(screen.getByLabelText('Source post'),{target:{value:source.id}});
 await waitFor(()=>expect(screen.getByLabelText('Title · 70 characters')).toHaveValue(source.title));
 for(const role of ['report','publisher','publication date'])fireEvent.change(screen.getByLabelText(`Verified ${role} · 180 characters`),{target:{value:'Owned verified fixture text'}});
 const queue=screen.getByRole('button',{name:'Queue local render'});await waitFor(()=>expect(queue).toBeEnabled());fireEvent.click(queue);
 await waitFor(()=>expect(studioApi.create).toHaveBeenCalledTimes(1));
 mockActor='actor-two';view.rerender(<QueryClientProvider client={clients[0]}><AdminLayout><SocialStudio/></AdminLayout></QueryClientProvider>);
 await act(async()=>resolve({id:'OLD-RENDER-ACCEPTANCE'}));
 expect(screen.queryByText(/Render queued/)).not.toBeInTheDocument();
 expect(screen.getByLabelText('Source post')).toHaveValue('');
 expect(screen.getByRole('button',{name:'Create media'})).toHaveAttribute('aria-pressed','true');
});

test('privacy actor transition retires the selected request and local review reason',async()=>{
 (privacyApi.queue as jest.Mock).mockImplementation(async()=>({requests:[{id:'request-'+mockActor,kind:'data_deletion',state:'received'}],total:1,page:1,has_more:false,policies:{},workflow_enabled:false,execution_enabled:false}));
 (privacyApi.detail as jest.Mock).mockResolvedValue({kind:'data_deletion',resolution:'resolved',plans:[{id:'old-plan',policy_key:'owned',decision:'pending_review',evidence:'PRIVATE actor-one evidence',scope:{credentials:[],flows:[],media_assets:[]},proposed_by:'other',execution:null}]});
 const view=mount(<PrivacyReview/>);fireEvent.click(await screen.findByRole('button',{name:/request-actor-one/}));
 fireEvent.change(await screen.findByLabelText('Independent review reason'),{target:{value:'PRIVATE actor-one review reason'}});
 mockActor='actor-two';view.rerender(<QueryClientProvider client={clients[0]}><AdminLayout><PrivacyReview/></AdminLayout></QueryClientProvider>);
 await screen.findByRole('button',{name:/request-actor-two/});
 expect(screen.queryByLabelText('Independent review reason')).not.toBeInTheDocument();
 expect(screen.queryByText('PRIVATE actor-one evidence')).not.toBeInTheDocument();
 expect(privacyApi.detail).toHaveBeenCalledTimes(1);
 expect(privacyApi.command).not.toHaveBeenCalled();
});
