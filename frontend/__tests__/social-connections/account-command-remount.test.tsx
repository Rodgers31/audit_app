import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AccountPublishingControl from '@/components/admin/social/connections/AccountPublishingControl';
import { socialApi, sendSocialCommand } from '@/lib/api/social';
import { connectionApi } from '@/lib/api/socialConnections';
let actor='00000000-0000-4000-8000-000000000001';
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:actor}})}));
jest.mock('@/lib/auth/admin',()=>({useAdmin:()=>({isAdmin:true})}));
jest.mock('@/lib/api/social',()=>{const actual=jest.requireActual('@/lib/api/social');return {...actual,socialApi:{accountPublishing:jest.fn()},sendSocialCommand:jest.fn()};});
jest.mock('@/lib/api/socialConnections',()=>({connectionApi:{verifyPublishingAccess:jest.fn()}}));
const id='00000000-0000-4000-8000-000000000010', state={account_id:id,publishing_enabled:false,controls_version:1,state_token:'a'.repeat(64),enable_available:true,enable_blockers:[],global_publishing_enabled:false,delivery_holds:['GLOBAL_PUBLISHING_DISABLED']};
const load=socialApi.accountPublishing as jest.Mock,send=sendSocialCommand as jest.Mock,verify=connectionApi.verifyPublishingAccess as jest.Mock;
beforeEach(()=>{jest.clearAllMocks();sessionStorage.clear();actor='00000000-0000-4000-8000-000000000001';load.mockResolvedValue(state);});
async function open(){const view=render(<AccountPublishingControl accountId={id} name='Fixture' refresh={jest.fn()} canVerifyMeta/>);fireEvent.click(screen.getByRole('button',{name:'Refresh account publishing controls'}));await screen.findByRole('button',{name:'Enable publishing for Fixture'});return view;}
test.each(['enable','verify'])('%s keeps the original key and exact body through a real component remount',async kind=>{
 const api=kind==='enable'?send:verify;api.mockRejectedValueOnce(new Error('Outcome unknown')).mockResolvedValueOnce({...state,publishing_enabled:kind==='enable',controls_version:2,state_token:'b'.repeat(64)});
 const label=kind==='enable'?'Enable publishing for Fixture':'Verify existing publishing access for Fixture';
 const first=await open();fireEvent.click(screen.getByRole('button',{name:label}));await screen.findByRole('alert');const original=api.mock.calls[0].slice(0,3);first.unmount();
 const next=await open();fireEvent.click(screen.getByRole('button',{name:label}));await waitFor(()=>expect(api).toHaveBeenCalledTimes(2));expect(api.mock.calls[1].slice(0,3)).toEqual(original);next.unmount();
});
test.each(['unavailable','malformed','full'])('%s recovery refuses before account-side submission',async kind=>{
 const key='auditgava.social.commands.v1:'+actor;
 if(kind==='malformed')sessionStorage.setItem(key,'{bad');
 if(kind==='full')sessionStorage.setItem(key,JSON.stringify({version:1,actor,entries:Array.from({length:100},(_,n)=>({identity:'retained-'+n,key:'00000000-0000-4000-8000-000000000099'}))}));
 const original=Storage.prototype.setItem;
 if(kind==='unavailable')Storage.prototype.setItem=()=>{throw new Error('Storage denied');};
 try{const view=await open();fireEvent.click(screen.getByRole('button',{name:'Enable publishing for Fixture'}));await screen.findByRole('alert');expect(send).not.toHaveBeenCalled();view.unmount();}finally{Storage.prototype.setItem=original;}
});
