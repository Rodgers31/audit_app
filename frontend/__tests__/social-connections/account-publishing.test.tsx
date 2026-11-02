import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import AccountPublishingControl from '@/components/admin/social/connections/AccountPublishingControl';
import { decodeAccountPublishing, socialApi, sendSocialCommand } from '@/lib/api/social';
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:jest.fn(()=>({user:{id:'admin-a'}}))}));
jest.mock('@/lib/api/social',()=>{const actual=jest.requireActual('@/lib/api/social');return {...actual,socialApi:{...actual.socialApi,accountPublishing:jest.fn()},sendSocialCommand:jest.fn()};});
const {useAuth}=jest.requireMock('@/lib/auth/AuthProvider');
const id='4aadebe9-11ce-4207-afce-836cd86cc9da';
const state={account_id:id,publishing_enabled:false,controls_version:1,state_token:'a'.repeat(64),enable_available:true,enable_blockers:[],global_publishing_enabled:false,delivery_holds:['GLOBAL_PUBLISHING_DISABLED']};
const load=socialApi.accountPublishing as jest.Mock, send=sendSocialCommand as jest.Mock;
beforeEach(()=>{jest.clearAllMocks();useAuth.mockReturnValue({user:{id:'admin-a'}});load.mockResolvedValue(state);send.mockResolvedValue({...state,publishing_enabled:true,controls_version:2,state_token:'b'.repeat(64)});});
async function open(){fireEvent.click(screen.getByRole('button',{name:'Refresh account publishing controls'}));await screen.findByRole('button',{name:'Enable publishing for Fixture Page'});}
test('explicit enable remains separate from global switch; then pause is supported',async()=>{
 const refresh=jest.fn();render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={refresh}/>);expect(load).not.toHaveBeenCalled();await open();
 expect(screen.getByText(/Global publishing is off/)).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Enable publishing for Fixture Page'}));await screen.findByRole('button',{name:'Pause publishing for Fixture Page'});
 expect(send).toHaveBeenCalledWith(`/accounts/${id}/publishing`,expect.objectContaining({expected_controls_version:1,expected_state:state.state_token,publishing_enabled:true}),expect.any(String),expect.any(Function),'patch');expect(refresh).toHaveBeenCalledTimes(1);
 send.mockResolvedValue({...state,controls_version:3,state_token:'c'.repeat(64)});fireEvent.click(screen.getByRole('button',{name:'Pause publishing for Fixture Page'}));await screen.findByRole('button',{name:'Enable publishing for Fixture Page'});
});
test('unsupported or uncertain state blocks enable while pause stays available',async()=>{
 load.mockResolvedValue({...state,enable_available:false,enable_blockers:['DELIVERY_UNRESOLVED']});const {unmount}=render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={jest.fn()}/>);await open();expect(screen.getByRole('button',{name:'Enable publishing for Fixture Page'})).toBeDisabled();expect(send).not.toHaveBeenCalled();unmount();
 load.mockResolvedValue({...state,publishing_enabled:true,enable_available:false,enable_blockers:['CREDENTIAL_UNAVAILABLE']});render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={jest.fn()}/>);fireEvent.click(screen.getByRole('button',{name:'Refresh account publishing controls'}));expect(await screen.findByRole('button',{name:'Pause publishing for Fixture Page'})).toBeEnabled();
});
test('ambiguous transport keeps same key and body for explicit retry, without optimistic enable',async()=>{
 send.mockRejectedValueOnce(new Error('Outcome not confirmed'));render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={jest.fn()}/>);await open();fireEvent.click(screen.getByRole('button',{name:'Enable publishing for Fixture Page'}));await screen.findByRole('alert');expect(screen.getByText(/^Account publishing is paused/)).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Enable publishing for Fixture Page'}));await screen.findByRole('button',{name:'Pause publishing for Fixture Page'});expect(send.mock.calls[0].slice(0,3)).toEqual(send.mock.calls[1].slice(0,3));
});
test('late old-actor response cannot update new session',async()=>{
 let resolve!:(v:unknown)=>void;load.mockReturnValue(new Promise(r=>{resolve=r;}));const refresh=jest.fn();const {rerender}=render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={refresh}/>);fireEvent.click(screen.getByRole('button',{name:'Refresh account publishing controls'}));useAuth.mockReturnValue({user:{id:'admin-b'}});rerender(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={refresh}/>);await act(async()=>{resolve(state);});expect(screen.queryByRole('button',{name:'Enable publishing for Fixture Page'})).not.toBeInTheDocument();expect(refresh).not.toHaveBeenCalled();
});
test.each([{enable_available:'false'},{publishing_enabled:1},{controls_version:0},{state_token:'bad'},{account_id:'bad'},{enable_available:false},{enable_blockers:null},{unexpected:true}])('malformed readiness refuses %#',change=>{expect(()=>decodeAccountPublishing({...state,...change})).toThrow();});

test.each([{controls_version:1,state_token:'b'.repeat(64)},{controls_version:9,state_token:'b'.repeat(64)},{controls_version:2,state_token:state.state_token}])('rejects incoherent mutation witness %#',async change=>{
 const refresh=jest.fn();send.mockImplementation((_path,_body,_key,decode)=>Promise.resolve(decode({...state,publishing_enabled:true,...change})));
 render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={refresh}/>);await open();fireEvent.click(screen.getByRole('button',{name:'Enable publishing for Fixture Page'}));
 await waitFor(()=>expect(screen.getByRole('alert')).toBeVisible());expect(refresh).not.toHaveBeenCalled();expect(screen.queryByRole('button',{name:'Pause publishing for Fixture Page'})).not.toBeInTheDocument();
});
test('rejects omitted global-off hold',()=>{expect(()=>decodeAccountPublishing({...state,delivery_holds:[]})).toThrow();});

test('batched refresh clicks share a synchronous in-flight lock',async()=>{
 let resolve!:(v:unknown)=>void;load.mockReturnValue(new Promise(r=>{resolve=r;}));render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={jest.fn()}/>);
 const button=screen.getByRole('button',{name:'Refresh account publishing controls'});
 act(()=>{button.dispatchEvent(new MouseEvent('click',{bubbles:true}));button.dispatchEvent(new MouseEvent('click',{bubbles:true}));});
 expect(load).toHaveBeenCalledTimes(1);await act(async()=>{resolve(state);});
});

test('unreadable platform controls explain blocked enable while pause remains available',async()=>{
 load.mockResolvedValue({...state,publishing_enabled:true,enable_available:false,enable_blockers:['PLATFORM_CONTROLS_UNAVAILABLE'],delivery_holds:[...state.delivery_holds,'PLATFORM_CONTROLS_UNAVAILABLE']});
 render(<AccountPublishingControl accountId={id} name='Fixture Page' refresh={jest.fn()}/>);fireEvent.click(screen.getByRole('button',{name:'Refresh account publishing controls'}));
 expect(await screen.findByText('Platform publishing controls are unreadable. An administrator must repair them before enabling publishing.')).toBeVisible();expect(screen.getByRole('button',{name:'Pause publishing for Fixture Page'})).toBeEnabled();
});
