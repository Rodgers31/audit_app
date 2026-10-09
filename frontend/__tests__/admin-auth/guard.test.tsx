import { render, screen } from '@testing-library/react';
import { AdminGuard, useHasRole } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: jest.fn() }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn() }) }));
const actor='00000000-0000-4000-8000-000000000001';
function Probe() { return <span>{useHasRole('admin').hasRole ? 'granted' : 'denied'}</span>; }
test.each(['admin','not-admin',{admin:false},['admin',true],['admin',''],['admin',null],['admin',' '],null])('guard rejects malformed roles %p', roles=>{
  (useAuth as jest.Mock).mockReturnValue({user:{id:actor,roles},authUser:{id:actor},isAuthenticated:true,isLoading:false});
  render(<><AdminGuard><span>private controls</span></AdminGuard><Probe/></>);
  expect(screen.queryByText('private controls')).not.toBeInTheDocument();
  expect(screen.getByText('denied')).toBeInTheDocument();
});
test('guard rejects profile of a different identity',()=>{
  (useAuth as jest.Mock).mockReturnValue({user:{id:'other',roles:['admin']},authUser:{id:actor},isAuthenticated:true,isLoading:false});
  render(<AdminGuard><span>private controls</span></AdminGuard>);
  expect(screen.queryByText('private controls')).not.toBeInTheDocument();
});
test.each([['admin'],['citizen','admin','legacy-role']])('guard retains legitimate arrays %p', (...roles)=>{
  (useAuth as jest.Mock).mockReturnValue({user:{id:actor,roles},authUser:{id:actor},isAuthenticated:true,isLoading:false});
  render(<AdminGuard><span>private controls</span></AdminGuard>);
  expect(screen.getByText('private controls')).toBeInTheDocument();
});
