import { render, screen } from '@testing-library/react';
import { AuthProvider, useAuth } from '@/lib/auth/AuthProvider';
import { useAdmin } from '@/lib/auth/admin';
const actor='00000000-0000-4000-8000-000000000001';
const mockSingle=jest.fn();
jest.mock('@/lib/supabase/client',()=>({createClient:()=>({auth:{getSession:async()=>({data:{session:{user:{id:'00000000-0000-4000-8000-000000000001'}}}}),onAuthStateChange:()=>({data:{subscription:{unsubscribe:()=>{}}}})},from:()=>({select:()=>({eq:()=>({maybeSingle:()=>mockSingle()})})})})}));
function Probe(){ const {user,isLoading}=useAuth(); const {isAdmin}=useAdmin(); return <span>{isLoading?'loading':isAdmin?'admin':user?'citizen':'no-profile'}</span>; }
test.each([{id:'other',roles:['admin']},{id:actor,roles:'admin'},{id:actor,roles:['admin',null]}])('real provider withholds malformed or mismatched profile %p',async profile=>{
 mockSingle.mockResolvedValue({data:profile,error:null});render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('no-profile');
});
test('real provider retains the legitimate profile',async()=>{mockSingle.mockResolvedValue({data:{id:actor,roles:['citizen','admin','legacy']},error:null});render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('admin');});
