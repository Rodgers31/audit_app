import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { decodeConnectionStatus, decodeDiscoveredFlow, decodeStartedFlow, decodeAccountHealth, decodeSelectedAccounts, connectionApi } from '@/lib/api/socialConnections';
import { receiveMetaCallback } from '@/components/admin/social/connections/callbackSecurity';
import MetaAccounts from '@/components/admin/social/connections/MetaAccounts';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/lib/hooks/useSocial', () => ({ useSocialAccounts: jest.fn() }));
jest.mock('@/lib/hooks/useSocialConnections', () => ({ useMetaAccountHealth: jest.fn(), useMetaConnectionStatus: jest.fn() }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 'actor' } }) }));
const { useSocialAccounts } = jest.requireMock('@/lib/hooks/useSocial');
const { useMetaAccountHealth, useMetaConnectionStatus } = jest.requireMock('@/lib/hooks/useSocialConnections');
const id='4aadebe9-11ce-4207-afce-836cd86cc9da', state='a'.repeat(43);
const status={ provider:'meta',available:false,blockers:['CONNECTIONS_DISABLED'],access_mode:'owned_standard',scopes:['pages_show_list'],publishing_adapter_available:false };
const choice={page_id:'901',display_name:'AuditGava',tasks:['CREATE_CONTENT'],instagram_id:'801',instagram_name:'AuditGava IG',instagram_handle:'auditgava',page_eligible:true,instagram_eligible:false,missing_page_scopes:[],missing_instagram_scopes:['instagram_content_publish']};
const discovery={flow_id:id,expires_at:new Date(Date.now()+600000).toISOString(),granted_scopes:['pages_show_list'],choices:[choice]};
const health={account_id:id,external_account_id:'901',api_product:'facebook_pages',connection_method:'facebook_login',connection_state:'connected',credential_kind:'facebook_page',credential_id:id,credential_version:1,key_version:'v1',access_expires_at:null,data_access_expires_at:null,parent_access_expires_at:null,parent_data_access_expires_at:null,parent_grant_reconnect_required:false,granted_scopes:['pages_show_list'],missing_scopes:[],checked_at:null,last_api_success_at:null,reconnect_required:false,publishing_enabled:false,renewal_strategy:'facebook_login_reconnect',provider_revocation_confirmed:false};
const account={id,platform:'facebook',display_name:'AuditGava',handle:null,profile_url:'https://www.facebook.com/901',connection_state:'connected',publishing_enabled:false,capabilities:{rules_version:'social-v1',provider_api_version:'v26.0',eligible:true,supported_formats:[],feature_states:{publishing:'unsupported'},limits:{},granted_scopes:[],required_scopes:[],price_class:'free',source_links:[],verified_at:null,adapter_available:false}};
beforeEach(() => {
  jest.restoreAllMocks();
  useSocialAccounts.mockReturnValue({ data: [], refetch: jest.fn(), isPending:false });
  useMetaConnectionStatus.mockReturnValue({ data:status, refetch:jest.fn(), isPending:false });
  useMetaAccountHealth.mockReturnValue({ data:health, refetch:jest.fn(), isPending:false });
});
test('fail closed on contradictory availability, secret fields and hostile DTOs',()=>{
  expect(decodeConnectionStatus(status).available).toBe(false);
  expect(()=>decodeConnectionStatus({...status,available:true})).toThrow();
  expect(()=>decodeDiscoveredFlow({...discovery,access_token:'fake-secret'})).toThrow();
  expect(()=>decodeDiscoveredFlow({...discovery,choices:[{...choice,instagram_eligible:true}]})).toThrow();
  expect(()=>decodeAccountHealth({...health,credential_version:true})).toThrow();
  expect(()=>decodeAccountHealth({...health,encrypted_bundle:'fake-secret'})).toThrow();
  expect(()=>decodeSelectedAccounts({flow_id:id,accounts:[{...account,access_token:'fake-secret'}]})).toThrow();
  expect(()=>decodeSelectedAccounts({flow_id:id,accounts:[{...account,capabilities:{...account.capabilities,access_token:'fake-secret'}}]})).toThrow();
  expect(decodeSelectedAccounts({flow_id:id,accounts:[account]}).accounts[0].display_name).toBe('AuditGava');
});
test('authorization URL requires Meta code flow without credential parameters',()=>{
  const authorize_url='https://www.facebook.com/v26.0/dialog/oauth?response_type=code&state='+state;
  expect(decodeStartedFlow({flow_id:id,expires_at:discovery.expires_at,authorize_url}).flow_id).toBe(id);
  for(const url of [authorize_url+'&access_token=fake-secret',authorize_url.replace('www.facebook.com','evil.example'),authorize_url.replace('response_type=code','response_type=token')]) expect(()=>decodeStartedFlow({flow_id:id,expires_at:discovery.expires_at,authorize_url:url})).toThrow();
});
test('callback origin, source and state bind the active popup',()=>{
  const popup={} as Window, other={} as Window, origin='https://admin.example.test';
  const event={origin,source:popup,data:{type:'auditgava-meta-callback',code:'short-code',state,denied:false}};
  expect(receiveMetaCallback(event,origin,popup,state)?.code).toBe('short-code');
  for(const hostile of [{...event,origin:'https://evil.example'},{...event,source:other},{...event,data:{...event.data,state:'b'.repeat(43)}},{...event,data:{...event.data,access_token:'fake-secret'}}]) expect(receiveMetaCallback(hostile,origin,popup,state)).toBeNull();
});
test('missing app configuration disables connect and keeps empty identities honest',()=>{
  render(<MetaAccounts />);
  expect(screen.getByRole('button',{name:'Connect owned Meta accounts'})).toBeDisabled();
  expect(screen.getByText(/No Meta accounts are connected/)).toBeInTheDocument();
  expect(screen.getByText(/Meta connections are unavailable/)).toBeInTheDocument();
});
test('actual identity health and shared grant disconnect are visible',()=>{
  useSocialAccounts.mockReturnValue({data:[account],refetch:jest.fn(),isPending:false});
  render(<MetaAccounts />);
  expect(screen.getByRole('heading',{name:'Facebook Page · AuditGava'})).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Reconnect identity'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Connection details'}));
  expect(screen.getByText('Account ID: 901')).toBeInTheDocument();
  expect(screen.getByText(/Disconnect disables both destinations/)).toBeInTheDocument();
  expect(screen.getByText(/No timed expiry reported; authorization remains revocable/)).toBeInTheDocument();
});
test('callback completes once and explicitly selected Page excludes ungranted Instagram',async()=>{
  useMetaConnectionStatus.mockReturnValue({data:{...status,available:true,blockers:[]},refetch:jest.fn(),isPending:false});
  const popup={location:{replace:jest.fn()},close:jest.fn()} as unknown as Window;
  jest.spyOn(window,'open').mockReturnValue(popup);
  jest.spyOn(connectionApi,'start').mockResolvedValue({flow_id:id,expires_at:discovery.expires_at,authorize_url:'https://www.facebook.com/v26.0/dialog/oauth?response_type=code&state='+state+'&redirect_uri='+encodeURIComponent(window.location.origin+'/admin/social/accounts/callback')});
  const complete=jest.spyOn(connectionApi,'complete').mockResolvedValue(discovery);
  const select=jest.spyOn(connectionApi,'select').mockResolvedValue({flow_id:id,accounts:[]});
  render(<MetaAccounts />);
  fireEvent.click(screen.getByRole('button',{name:'Connect owned Meta accounts'}));
  await waitFor(()=>expect(popup.location.replace).toHaveBeenCalled());
  const event=new MessageEvent('message',{origin:window.location.origin,source:popup,data:{type:'auditgava-meta-callback',code:'short-code',state,denied:false}});
  await act(async () => { window.dispatchEvent(event); window.dispatchEvent(event); });
  await screen.findByRole('heading',{name:'Confirm account identities'});
  expect(complete).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button',{name:'Confirm selected identities'})).toBeDisabled();
  fireEvent.change(screen.getByRole('combobox',{name:'Facebook Page'}),{target:{value:'901'}});
  expect(screen.getByRole('checkbox')).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Confirm selected identities'}));
  await waitFor(()=>expect(select).toHaveBeenCalledWith(id,'901',null,expect.any(String)));
  await screen.findByText('Selected accounts connected. Publishing remains disabled.');
});
