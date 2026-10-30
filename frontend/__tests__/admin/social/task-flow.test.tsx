import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, post, system, validation } from '../../../tests/socialFixtures';
jest.mock('@/lib/api/axios', () => ({ __esModule:true, default:{get:jest.fn(),post:jest.fn(),patch:jest.fn()} }));
jest.mock('@/lib/auth/admin', () => ({useAdmin:()=>({isAdmin:true})}));
jest.mock('@/lib/auth/AuthProvider', () => ({useAuth:()=>({user:{id:'00000000-0000-4000-8000-000000000001'}})}));
const get=api.get as jest.Mock,send=api.post as jest.Mock,patch=api.patch as jest.Mock;
function mount(p?:ReturnType<typeof post>){const qc=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});return render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={accounts} system={{...system,publishing_enabled:false}} /></QueryClientProvider>);}
beforeEach(()=>{jest.clearAllMocks();Object.defineProperty(crypto,'randomUUID',{configurable:true,value:()=> '00000000-0000-4000-8000-000000000123'});});
test('a normal manual draft needs post text rather than a hidden metadata title',async()=>{
 get.mockResolvedValue({data:post()});send.mockImplementation(async(_path,body)=>({data:post(body)}));
 mount();fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'Read the source behind this county figure.\n\nReporting period matters.'}});
 fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await screen.findByText('Draft saved. Nothing has been queued for publication.');
 expect(send.mock.calls[0][1].title).toBe('Read the source behind this county figure.');
 expect(send.mock.calls[0][1].document.master.text).toBe('Read the source behind this county figure.\n\nReporting period matters.');
 expect(send.mock.calls[0][0]).toBe('/admin/social/posts');
});
test('generated evidence follows the newly saved immutable revision',async()=>{
 const p=post({origin_type:'generated'});let current=p;
 send.mockImplementation(async(path:string)=>{if(!path.endsWith('/validate'))throw new Error('Only validation admitted');return {data:validation(current)};});
 get.mockImplementation(async(path:string)=>({data:path.endsWith('/evidence')?{post_id:p.id,revision_id:current.revision_id,source_event_id:null,generator_metadata:{template_version:'factual-v1'},evidence:{evidence_version:1,source:{source_type:'cob',source_key:'fixture',ingestion_id:'1',facts:[]}}}:current}));
 patch.mockImplementation(async(_path,body)=>{current=post({...p,...body,version:2,revision_id:'00000000-0000-4000-8000-000000000042'});return {data:current};});
 mount(p);await waitFor(()=>expect(screen.getByRole('button',{name:'Save & validate'})).toBeEnabled());await waitFor(()=>expect(get.mock.calls.filter(([path])=>path.endsWith('/evidence'))).toHaveLength(1));
 fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'An edited statement needs a fresh review.'}});fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await screen.findByText('Draft saved. Nothing has been queued for publication.');
 await waitFor(()=>expect(get.mock.calls.filter(([path])=>path.endsWith('/evidence'))).toHaveLength(2));
 expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
