import SocialComposer from '@/components/admin/social/SocialComposer';
import { postDestinationIssue } from '@/components/admin/social/socialDocument';
import { automaticMediaFormats } from '@/components/admin/social/automaticMediaFormat';
import api from '@/lib/api/axios';
import { SocialApiError, SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { deliverySystem, publicationReceipt, accounts, actorId, facebookId, post, system, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
// Source-evidence decoding is covered separately; media selection and composer
// persistence/validation/preview in these tests are the real components/hooks.
jest.mock('@/components/admin/social/GeneratedEvidence', () => () => null);
const get=api.get as jest.Mock, send=api.post as jest.Mock, patch=api.patch as jest.Mock;
let saved: SocialPost, qc: QueryClient, kind: 'image/png' | 'video/mp4';
const mediaId='00000000-0000-4000-8000-000000000101';
function asset() { return { id:mediaId,version:1,filename:kind==='image/png'?'report.png':'report.mp4',state:'ready',mime_type:kind,byte_size:123,width:1200,height:630,duration_ms:kind==='video/mp4'?15000:null,sha256:'a'.repeat(64),default_alt_text:kind==='image/png'?'An inspected source illustration':null,safe_error:null,created_at:'2026-10-29T12:00:00Z' }; }
function preview() {
  const stamp=new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z$/,'Z');
  const query=new URLSearchParams({'X-Amz-Algorithm':'AWS4-HMAC-SHA256','X-Amz-Credential':`fixture/${stamp.slice(0,8)}/auto/s3/aws4_request`,'X-Amz-Date':stamp,'X-Amz-Expires':'300','X-Amz-SignedHeaders':'host','X-Amz-Signature':'b'.repeat(64)});
  return {asset:asset(),url:`https://${'a'.repeat(32)}.r2.cloudflarestorage.com/owned/${mediaId}?${query}`,expires_at:new Date(Date.now()+299000).toISOString()};
}
beforeEach(() => {
  jest.clearAllMocks();kind='image/png';
  saved=post({origin_type:'generated',editorial_state:'pending_review',content_type:'budget_update',references:[{url:'https://www.kra.go.ke/source',label:'Kenya Revenue Authority'}],document:{schema_version:1,master:{text:'Kenya: KSh 561 billion reported for PAYE. Figures and sources on AuditGava.',link:'https://www.auditgava.com/reports/revenue_by_source/1?view=financial&record=1&snapshot='+ 'a'.repeat(64),hashtags:['#PAYE','#Kenya','#AuditGava'],media:[]},targets:[{account_id:facebookId,format:'text',overrides:{hashtags:{mode:'replace',value:['#PAYE','#Kenya']}}}]}});
  qc=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});qc.setQueryData(socialKeys.detail(actorId,saved.id),saved);
  Object.defineProperty(crypto,'randomUUID',{configurable:true,value:()=>`00000000-0000-4000-8000-${String(Math.random()).slice(2).padEnd(12,'0').slice(0,12)}`});
  get.mockImplementation(async (path:string) => ({data:path.endsWith('/media/capabilities')?{upload_available:false,library_available:true,allowed_mime_types:[],max_image_bytes:10485760,max_video_bytes:52428800,unavailable_reason:null}:path.endsWith('/media/assets')?{assets:[asset()],total:1,page:1,page_size:20,has_more:false}:path.endsWith('/preview')?preview():saved}));
  send.mockImplementation(async (path:string,body:unknown) => {
    if (!path.endsWith('/validate')) throw new Error('Only read-only validation is admitted by this fixture');
    return {data:validation(saved)};
  });
  patch.mockImplementation(async (_path:string,body:Partial<SocialPost>) => {saved=post({...saved,...body,version:saved.version+1,revision_id:'00000000-0000-4000-8000-000000000041'});return {data:saved};});
});
afterEach(()=>qc.clear());
const readyAccounts=accounts.map(a=>({...a,capabilities:{...a.capabilities,supported_formats:['text','image','reel'] as ('text'|'image'|'reel')[]}}));
function mount(destinationAccounts=readyAccounts, status={...system,publishing_enabled:false}){return render(<QueryClientProvider client={qc}><SocialComposer initialPost={saved} accounts={destinationAccounts} system={status} /></QueryClientProvider>);}

test.each(['image/png','video/mp4'] as const)('add %s, review saved preview without writing or Save & validate',async mime=>{
  kind=mime;mount();
  await waitFor(()=>expect(send.mock.calls.filter(c=>c[0].endsWith('/validate'))).toHaveLength(1));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Choose from library'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Choose from library'}));
  fireEvent.click(await screen.findByRole('button',{name:`Use ${mime==='image/png'?'report.png':'report.mp4'}`}));
  await waitFor(()=>expect(patch).toHaveBeenCalledTimes(1),{timeout:2500});
  await waitFor(()=>expect(send.mock.calls.filter(c=>c[0].endsWith('/validate'))).toHaveLength(2));
  const document=patch.mock.calls[0][1].document;
  expect(document.targets[0].format).toBe(mime==='image/png'?'image':'reel');
  expect(document.master.text).toContain('KSh 561 billion');expect(document.master.hashtags).toEqual(['#PAYE','#Kenya','#AuditGava']);
  expect(document.targets[0].overrides.hashtags.value).toEqual(['#PAYE','#Kenya']);
  expect(document.master.media).toEqual([{asset_id:mediaId,alt_text:mime==='image/png'?'An inspected source illustration':null,caption_asset_id:null}]);
  expect(patch.mock.calls[0][1].references).toEqual([{url:'https://www.kra.go.ke/source',label:'Kenya Revenue Authority'}]);
  expect(send.mock.calls[1][1]).toMatchObject({expected_version:2});
  expect(screen.getByRole('region',{name:'Resolved post preview'})).toHaveTextContent('#PAYE #Kenya');
  expect(screen.getByRole('button',{name:'Publish now'})).toBeDisabled();
  expect(send.mock.calls.every(c=>c[0].endsWith('/validate'))).toBe(true);
});

test('unknown capabilities or incompatible media retain every target and never claim support',()=>{
  const unknown=accounts.map(a=>({...a,capabilities:{...a.capabilities,supported_formats:[]}}));
  const document={...saved.document,master:{...saved.document.master,media:[{asset_id:mediaId,alt_text:null,caption_asset_id:null}]}};
  expect(automaticMediaFormats(document,unknown,new Map([[mediaId,'image/png']])).targets).toEqual(document.targets);
  expect(automaticMediaFormats(document,accounts,new Map()).targets).toEqual(document.targets);
});


test.each([',',';',')',''])('an adjacent external caption URL after %s still blocks publication',separator=>{
  expect(postDestinationIssue({...saved.document.master,text:'Read https://www.auditgava.com/budget'+separator+'https://evil.test/source'})).toMatch(/AuditGava/);
  expect(postDestinationIssue({...saved.document.master,text:'Read https://www.auditgava.com/budget'+separator+'https://www.auditgava.com/debt'})).toBeNull();
});


test('a delayed autosave stops its validation chain when the composer unmounts',async()=>{
  let complete: ((value: unknown)=>void) | undefined;
  patch.mockImplementation((_path:string,body:Partial<SocialPost>)=>new Promise(resolve=>{
    const updated=post({...saved,...body,version:saved.version+1,revision_id:'00000000-0000-4000-8000-000000000041'});
    complete=()=>resolve({data:updated});
  }));
  const view=mount();
  await waitFor(()=>expect(send).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button',{name:'Choose from library'}));
  fireEvent.click(await screen.findByRole('button',{name:'Use report.png'}));
  await waitFor(()=>expect(patch).toHaveBeenCalledTimes(1),{timeout:2500});
  view.unmount();complete!({});
  await new Promise(resolve=>setTimeout(resolve,40));
  expect(send).toHaveBeenCalledTimes(1);
});

test('legacy generated copy names missing preparation instead of claiming it is prepared',()=>{
  saved={...saved,document:{...saved.document,master:{...saved.document.master,hashtags:[]},targets:[{account_id:facebookId,format:'text',overrides:{}}]}};
  mount();
  expect(screen.getByText('Copy needs preparation')).toBeInTheDocument();
  expect(screen.getByText('Facebook: add relevant hashtags or a topic.')).toBeInTheDocument();
  expect(screen.queryByText(/source references are prepared/)).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Publish now'})).toBeDisabled();
  expect(send.mock.calls.some(c=>c[0].endsWith('/prepare'))).toBe(false);
});

test('complete copy requests review without claiming publication or source readiness',()=>{
  mount();
  expect(screen.getByText('Review saved copy')).toBeInTheDocument();
  expect(screen.getByText(/Source and account checks still apply/)).toBeInTheDocument();
  expect(screen.queryByText('Copy needs preparation')).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Publish now'})).toBeDisabled();
});

test('an empty account hashtag override is incomplete even when the master has hashtags',()=>{
  saved={...saved,document:{...saved.document,targets:[{account_id:facebookId,format:'text',overrides:{hashtags:{mode:'replace',value:[]}}}]}};
  mount();
  expect(screen.getByText('Copy needs preparation')).toBeInTheDocument();
  expect(screen.getByText('Facebook: add relevant hashtags or a topic.')).toBeInTheDocument();
});

test('missing captions, destinations and source references stay visible',()=>{
  saved={...saved,references:[],document:{...saved.document,master:{...saved.document.master,text:' ',link:null},targets:[{account_id:facebookId,format:'text',overrides:{}}]}};
  mount();
  expect(screen.getByText('Copy needs preparation')).toBeInTheDocument();
  expect(screen.getByText('Facebook: add a caption.')).toBeInTheDocument();
  expect(screen.getByText('Facebook: add a valid AuditGava destination.')).toBeInTheDocument();
  expect(screen.getByText('Add supporting source references.')).toBeInTheDocument();
});

test('an edited generated caption is labelled unsaved until the saved revision is adopted',()=>{
  mount();
  fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'Updated caption awaiting save.'}});
  expect(screen.getByText('Unsaved copy')).toBeInTheDocument();
  expect(screen.queryByText('Review saved copy')).not.toBeInTheDocument();
});

test('preparation identifies each selected account when platforms repeat',()=>{
  const second={...readyAccounts[0],id:'00000000-0000-4000-8000-000000000099',display_name:'Community Page'};
  saved={...saved,document:{...saved.document,master:{...saved.document.master,text:''},targets:[{account_id:facebookId,format:'text',overrides:{}},{account_id:second.id,format:'text',overrides:{}}]}};
  mount([...readyAccounts,second]);
  expect(screen.getByText('Facebook · AuditGava test Page: add a caption.')).toBeInTheDocument();
  expect(screen.getByText('Facebook · Community Page: add a caption.')).toBeInTheDocument();
});

test('a refused current-source preparation stays visibly held without changing the saved revision',async()=>{
  send.mockImplementation(async(path:string)=>{
    if(path.endsWith('/prepare'))throw new SocialApiError('SOURCE_REVIEW_REQUIRED','Current source authority changed. Review its evidence again.');
    return {data:validation(saved)};
  });
  mount();
  await waitFor(()=>expect(send.mock.calls.some(c=>c[0].endsWith('/validate'))).toBe(true));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh caption & hashtags'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Refresh caption & hashtags'}));
  await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('Current source authority changed. Review its evidence again.'));
  expect(screen.getByText('Source review required')).toBeInTheDocument();
  expect(screen.queryByText('Review saved copy')).not.toBeInTheDocument();
  expect(patch).not.toHaveBeenCalled();
  expect(screen.getByRole('button',{name:'Publish now'})).toBeDisabled();
});


test('generated draft media remains discoverable from the default preview and publishes only after a human decision', async () => {
  send.mockImplementation(async (path:string) => ({data:path.endsWith('/validate')?validation(saved):publicationReceipt(saved)}));
  mount(readyAccounts, deliverySystem());
  expect(screen.getByRole('button',{name:'Preview',exact:true})).toHaveAttribute('aria-pressed','true');
  await waitFor(()=>expect(screen.getByRole('button',{name:'Choose from library'})).toBeEnabled());
  expect(screen.getByRole('button',{name:'Choose from library'}).closest('[data-composer-panel]')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Choose from library'}));
  fireEvent.click(await screen.findByRole('button',{name:'Use report.png'}));
  await waitFor(()=>expect(patch).toHaveBeenCalledTimes(1),{timeout:2500});
  await waitFor(()=>expect(screen.getByRole('button',{name:'Publish now'})).toBeEnabled());
  expect(screen.getByRole('region',{name:'Resolved post preview'})).toHaveTextContent('An inspected source illustration');
  expect(send.mock.calls.every(([path])=>path.endsWith('/validate'))).toBe(true);
  fireEvent.click(screen.getByRole('checkbox',{name:/I checked the facts and sources/}));
  fireEvent.click(screen.getByRole('button',{name:'Publish now'}));
  await screen.findByText(/Publication accepted for 1 destination/);
  expect(send.mock.calls.find(([path])=>path.endsWith('/publish'))[1]).toEqual({expected_version:2,revision_id:saved.revision_id,acknowledged_warning_codes:[],review_attestation:{facts_checked:true,sources_checked:true}});
  expect(screen.queryByRole('link',{name:/View Facebook post/})).not.toBeInTheDocument();
});
