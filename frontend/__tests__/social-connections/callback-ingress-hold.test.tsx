import { fireEvent, render, screen, within } from '@testing-library/react';
import PlatformAccounts from '@/components/admin/social/connections/PlatformAccounts';
import { platformConnectionApi } from '@/lib/api/socialPlatformConnections';

jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{get:jest.fn(),post:jest.fn()}}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:'11111111-1111-4111-8111-111111111111'}})}));
jest.mock('@/lib/hooks/useSocial',()=>({useSocialAccounts:()=>({data:[{id:'11111111-1111-4111-8111-111111111111',platform:'threads',display_name:'Inert Threads',connection_state:'connected',publishing_enabled:false}],refetch:jest.fn()})}));
let mockBlockers=['CALLBACK_INGRESS_UNVERIFIED'];
jest.mock('@tanstack/react-query',()=>({useQuery:({queryKey}:{queryKey:string[]})=>({data:{provider:queryKey[1],available:false,blockers:mockBlockers,scopes:[],provider_api_version:'fixture',publishing_enabled:false},refetch:jest.fn(),isPending:false})}));
const id='11111111-1111-4111-8111-111111111111';
afterEach(()=>jest.restoreAllMocks());

test.each([false,true])('privacy hold preserves grant maintenance without bypassing another blocker: %s',async extra=>{
  mockBlockers=['CALLBACK_INGRESS_UNVERIFIED',...(extra?['PRODUCT_ACCESS_UNVERIFIED']:[])];
  const start=jest.spyOn(platformConnectionApi,'start');
  jest.spyOn(platformConnectionApi,'health').mockResolvedValue({account_id:id,platform:'threads',connection_state:'connected',credential_id:id,credential_version:1,access_expires_at:'2099-01-01T00:00:00Z',refresh_pending:false,reconnect_required:false,publishing_enabled:false});
  render(<PlatformAccounts/>);
  for(const name of ['Threads','X','TikTok'])expect(screen.getByRole('button',{name:`Connect ${name}`})).toBeDisabled();
  const panel=within(screen.getByRole('region',{name:'Threads accounts'}));
  expect(panel.getByText(/New connections are paused until callback privacy is verified/)).toBeInTheDocument();
  fireEvent.click(panel.getByRole('button',{name:'Inspect Inert Threads connection'}));
  const renewal=await panel.findByRole('button',{name:'Renew existing grant'});
  if(extra)expect(renewal).toBeDisabled();else expect(renewal).toBeEnabled();
  expect(panel.getByRole('button',{name:'Disable local connection'})).toBeEnabled();
  expect(start).not.toHaveBeenCalled();
});
