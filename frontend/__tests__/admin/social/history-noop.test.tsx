import {act,cleanup,fireEvent,render,screen} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import SocialComposer from '@/components/admin/social/SocialComposer';
import AdminPageShell from '@/components/admin/AdminPageShell';
import NavTrailTracker from '@/lib/navigation/NavTrailTracker';
import api from '@/lib/api/axios';
import {accounts,post,system} from '../../../tests/socialFixtures';
const mockBack=jest.fn(()=>window.history.back());
jest.mock('next/navigation',()=>({useRouter:()=>({back:mockBack}),usePathname:()=>window.location.pathname,useSearchParams:()=>new URLSearchParams(window.location.search)}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:'00000000-0000-4000-8000-000000000001'}})}));
jest.mock('@/lib/auth/admin',()=>({useAdmin:()=>({isAdmin:true})}));
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{get:jest.fn(),post:jest.fn(),patch:jest.fn()}}));
const settle=async()=>act(async()=>{await new Promise(resolve=>setTimeout(resolve,70));});
afterEach(()=>{cleanup();jest.restoreAllMocks();});
it('REAL first-entry Back cannot leave approval for later edited Forward navigation',async()=>{
 expect(window.history.length).toBe(1);
 window.history.replaceState({},'','/admin/social/review');
 window.history.pushState({},'','/admin/social?page=4');
 act(()=>window.history.back());await settle();expect(window.location.pathname).toBe('/admin/social/review');
 (api.get as jest.Mock).mockResolvedValue({data:post()});const client=new QueryClient({defaultOptions:{queries:{retry:false}}});
 const tree=render(<QueryClientProvider client={client}><NavTrailTracker/><AdminPageShell title='Review' back={{href:'/admin/social',label:'Back to queue'}}><SocialComposer initialPost={post()} accounts={accounts} system={system}/></AdminPageShell></QueryClientProvider>);
 fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'First local edit'}});
 sessionStorage.setItem('auditgava-nav-trail',JSON.stringify([{pathname:'/admin/social',search:'?page=4',ts:1},{pathname:'/admin/social/review',search:'',ts:2}]));
 const confirm=jest.spyOn(window,'confirm').mockReturnValue(true);
 fireEvent.click(screen.getByRole('link',{name:'← Back to queue'}));await settle();
 expect(mockBack).toHaveBeenCalledTimes(1);expect(window.location.pathname).toBe('/admin/social/review'); // Actual Back is out of range.
 fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'Later edit after the attempted action'}});confirm.mockReturnValue(false);
 act(()=>window.history.forward());await settle();
 try {expect(window.location.pathname).toBe('/admin/social/review');expect(confirm).toHaveBeenCalledTimes(2);}
 finally {tree.unmount();client.clear();}
});
