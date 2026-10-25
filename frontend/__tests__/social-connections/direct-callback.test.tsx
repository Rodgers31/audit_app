import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { decodeDirectStartedFlow, decodeConnectionStatus, connectionApi, ConnectionError } from '@/lib/api/socialConnections';
import { receiveDirectMetaCallback, launchDirectMeta } from '@/components/admin/social/connections/callbackSecurity';
import MetaAccounts from '@/components/admin/social/connections/MetaAccounts';
import { saveConnectionRecovery } from '@/components/admin/social/connections/connectionRecovery';
jest.mock('@/lib/api/axios', () => ({ __esModule:true, default:{get:jest.fn(),post:jest.fn()} }));
jest.mock('@/lib/hooks/useSocial', () => ({useSocialAccounts:jest.fn()}));
jest.mock('@/lib/hooks/useSocialConnections', () => ({useMetaAccountHealth:jest.fn(),useMetaConnectionStatus:jest.fn()}));
jest.mock('@/lib/auth/AuthProvider', () => ({useAuth:()=>({user:{id:'actor'}})}));
const hooks=jest.requireMock('@/lib/hooks/useSocialConnections'), social=jest.requireMock('@/lib/hooks/useSocial');
const id='4aadebe9-11ce-4207-afce-836cd86cc9da', callback='https://api.example.test/api/v1/social/oauth/meta/callback';
const flow={flow_id:id,launch_url:'https://api.example.test/api/v1/social/oauth/meta/launch',launch_token:'x'.repeat(43),expires_at:new Date(Date.now()+600000).toISOString()};
const status={provider:'meta',available:true,blockers:[],access_mode:'owned_standard',scopes:[],publishing_adapter_available:false,direct_callback:callback};
const discovery={flow_id:id,expires_at:flow.expires_at,granted_scopes:[],choices:[]};
beforeEach(()=>{jest.restoreAllMocks();window.sessionStorage.clear();social.useSocialAccounts.mockReturnValue({data:[],refetch:jest.fn()});hooks.useMetaConnectionStatus.mockReturnValue({data:status,refetch:jest.fn()});});
test('direct response permits no code/state or credential and exact API launch only',()=>{
  expect(decodeConnectionStatus(status).direct_callback).toBe(callback); expect(decodeDirectStartedFlow(flow,callback)).toEqual(flow);
  for(const invalid of [{...flow,code:'INERT'}, {...flow,state:'INERT'}, {...flow,launch_url:flow.launch_url+'?launch_token=INERT'}, {...flow,launch_url:flow.launch_url.replace('api.example.test','evil.example')}, {...flow,launch_token:true}]) expect(()=>decodeDirectStartedFlow(invalid,callback)).toThrow();
});
test('reference message rejects wrong origin/window/attempt/extra data',()=>{
  const popup={} as Window, event={origin:'https://api.example.test',source:popup,data:{type:'auditgava-meta-ready',flow_id:id}};
  expect(receiveDirectMetaCallback(event,event.origin,popup,id)).toBe(true);
  for(const bad of [{...event,origin:'https://evil.example'},{...event,source:{} as Window},{...event,data:{...event.data,flow_id:'other'}},{...event,data:{...event.data,code:'INERT'}},{...event,data:{...event.data,state:'INERT'}},{...event,data:{...event.data,access_token:'INERT'}}]) expect(receiveDirectMetaCallback(bad,event.origin,popup,id)).toBe(false);
});
test('launch nonce uses a transient top-level POST body',()=>{
  let captured:HTMLFormElement|undefined;
  jest.spyOn(HTMLFormElement.prototype,'submit').mockImplementation(function(this:HTMLFormElement){captured=this.cloneNode(true) as HTMLFormElement;});
  launchDirectMeta('owned-popup',flow);
  expect(captured?.method).toBe('post');expect(captured?.action).toBe(flow.launch_url);expect(captured?.target).toBe('owned-popup');
  expect(captured?.querySelector('input[name=launch_token]')?.getAttribute('value')).toBe(flow.launch_token);expect(document.querySelector('form')).toBeNull();
});
test('Accounts uses direct transport and ignores credential-bearing messages',async()=>{
  const popup={close:jest.fn()} as unknown as Window; jest.spyOn(window,'open').mockReturnValue(popup);
  const submit=jest.spyOn(HTMLFormElement.prototype,'submit').mockImplementation(()=>{});
  const start=jest.spyOn(connectionApi,'startDirect').mockResolvedValue(flow), legacy=jest.spyOn(connectionApi,'start');
  const finish=jest.spyOn(connectionApi,'completeDirect').mockResolvedValue(discovery);
  render(<MetaAccounts/>);fireEvent.click(screen.getByRole('button',{name:'Connect owned Meta accounts'}));
  await waitFor(()=>expect(submit).toHaveBeenCalledTimes(1));expect(start).toHaveBeenCalledWith(window.location.origin,callback,undefined);expect(legacy).not.toHaveBeenCalled();
  await act(async()=>{window.dispatchEvent(new MessageEvent('message',{origin:'https://api.example.test',source:popup,data:{type:'auditgava-meta-ready',flow_id:id,code:'INERT'}}));});expect(finish).not.toHaveBeenCalled();
  await act(async()=>{for(let i=0;i<2;i++)window.dispatchEvent(new MessageEvent('message',{origin:'https://api.example.test',source:popup,data:{type:'auditgava-meta-ready',flow_id:id}}));});
  await screen.findByRole('heading',{name:'Confirm account identities'});expect(finish).toHaveBeenCalledTimes(1);expect(finish).toHaveBeenCalledWith(id,expect.any(String));
});
test('explicit recovery recovers already exchanged choices without code replay',async()=>{
  saveConnectionRecovery('actor',id,flow.expires_at);
  const finish=jest.spyOn(connectionApi,'completeDirect').mockRejectedValue(new ConnectionError('OAUTH_STATE_USED','Used'));
  const choices=jest.spyOn(connectionApi,'choices').mockResolvedValue(discovery);
  render(<MetaAccounts/>);fireEvent.click(await screen.findByRole('button',{name:'Recover account choices'}));
  await screen.findByRole('heading',{name:'Confirm account identities'});expect(finish).toHaveBeenCalledTimes(1);expect(choices).toHaveBeenCalledWith(id);
});
