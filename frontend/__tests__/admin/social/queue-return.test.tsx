import SocialWorkspace from '@/components/admin/social/SocialWorkspace';
import api from '@/lib/api/axios';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {accounts,post,system} from '../../../tests/socialFixtures';
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{get:jest.fn(),post:jest.fn(),patch:jest.fn()}}));
jest.mock('@/lib/auth/admin',()=>({useAdmin:()=>({isAdmin:true})}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:'00000000-0000-4000-8000-000000000001'}})}));
jest.mock('next/navigation',()=>({useRouter:()=>({push:jest.fn()})}));
const get=api.get as jest.Mock;
function mount(){const qc=new QueryClient({defaultOptions:{queries:{retry:false}}});return render(<QueryClientProvider client={qc}><SocialWorkspace/></QueryClientProvider>);}
beforeEach(()=>{jest.clearAllMocks();window.history.replaceState({},'', '/admin/social');get.mockImplementation(async(path,opts)=>({data:path.endsWith('/accounts')?{accounts}:path.endsWith('/system/status')?system:{posts:[post()],page:opts.params.page,total:21,page_size:20,has_more:opts.params.page===1}}));});
afterEach(()=>window.history.replaceState({},'', '/'));
test('queue selection survives the full review route and browser history',async()=>{
 const tree=mount();await screen.findByRole('link',{name:post().title});
 fireEvent.click(screen.getByText('Filter & history'));fireEvent.change(screen.getByLabelText('View'),{target:{value:'history'}});fireEvent.change(screen.getByLabelText('Origin'),{target:{value:'generated'}});
 await screen.findByText('21 history posts');fireEvent.click(screen.getByRole('button',{name:'Next page'}));await screen.findByText('Page 2');
 expect(window.location.search).toContain('view=history');expect(window.location.search).toContain('origin=generated');expect(window.location.search).toContain('page=2');
 const link=screen.getByRole('link',{name:post().title});expect(link.getAttribute('href')).toContain('queue=');tree.unmount();get.mockClear();mount();
 await screen.findByText('Page 2');expect(screen.getByLabelText('View')).toHaveValue('history');expect(screen.getByLabelText('Origin')).toHaveValue('generated');
 expect(get.mock.calls.filter(([path])=>path.endsWith('/posts')).every(([,opts])=>opts.params.page===2&&opts.params.delivery_filter==='history'&&opts.params.origin_type==='generated')).toBe(true);
});
test('the primary link includes its visible action in its accessible name',async()=>{mount();await waitFor(()=>{const link=screen.getAllByRole('link').find(link=>link.textContent?.includes('Open draft'));expect(link).toBeDefined();expect(link).toHaveAccessibleName(/Open draft/);});});
