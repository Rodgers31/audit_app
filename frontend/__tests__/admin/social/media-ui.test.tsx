import { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SocialMedia from '@/components/admin/social/SocialMedia';
import SocialOverrides from '@/components/admin/social/SocialOverrides';
import api from '@/lib/api/axios';
import { DocumentTarget, MediaReference, SocialContent } from '@/lib/api/social';
import { MediaAsset } from '@/lib/api/socialMedia';
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
const actor = '00000000-0000-4000-8000-000000000001', id = '00000000-0000-4000-8000-000000000101';
const get = api.get as jest.Mock, post = api.post as jest.Mock;
const capabilities = { upload_available: true, library_available: true, allowed_mime_types: ['image/png'], max_image_bytes: 10485760, max_video_bytes: 52428800, unavailable_reason: null };
function asset(): MediaAsset { return { id, version: 2, filename: 'proof.png', state: 'ready', mime_type: 'image/png', byte_size: 4, sha256: 'a'.repeat(64), width: 2, height: 2, duration_ms: null, default_alt_text: 'Original description', safe_error: null, created_at: new Date().toISOString() }; }
function signed(upload = false) {
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  return `https://${'a'.repeat(32)}.r2.cloudflarestorage.com/media-test/${upload ? `quarantine/${actor}/${id}/source` : `ready/${id}/original`}?${new URLSearchParams({ 'X-Amz-Algorithm': 'AWS4-HMAC-SHA256', 'X-Amz-Credential': `fake/${stamp.slice(0,8)}/auto/s3/aws4_request`, 'X-Amz-Date': stamp, 'X-Amz-Expires': '300', 'X-Amz-SignedHeaders': upload ? 'host;content-length;content-type;if-none-match' : 'host', 'X-Amz-Signature': 'b'.repeat(64) })}`;
}
function grant() { return { asset: { ...asset(), state: 'pending', version: 1, mime_type: null, byte_size: null, sha256: null, width: null, height: null }, method: 'PUT', url: signed(true), headers: { 'Content-Type': 'image/png', 'If-None-Match': '*' }, expires_at: new Date(Date.now() + 299000).toISOString() }; }
function Harness({ initial = [] }: { initial?: MediaReference[] }) { const [media, setMedia] = useState(initial); return <><SocialMedia label='Master' media={media} onChange={setMedia} /><output data-testid='document'>{JSON.stringify(media)}</output></>; }
function mount(tree = <Harness />) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{tree}</QueryClientProvider>); }
const originalFetch = global.fetch;
beforeEach(() => {
  jest.clearAllMocks(); Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => `00000000-0000-4000-8000-${String(Math.random()).slice(2).padEnd(12, '0').slice(0, 12)}` });
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/capabilities') ? capabilities : path.endsWith('/preview') ? { asset: asset(), url: signed(), expires_at: new Date(Date.now()+299000).toISOString() } : { assets: [asset()], total: 1, page: 1, page_size: 20, has_more: false } }));
  post.mockImplementation(async (path: string) => ({ data: path.endsWith('/complete') ? asset() : grant() }));
  global.fetch = jest.fn().mockResolvedValue({ ok: true, status: 200 });
});
afterEach(() => { global.fetch = originalFetch; });
async function open(name: string) { await waitFor(() => expect(screen.getByRole('button', { name })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name })); }
async function startUpload() { await open('Upload media'); fireEvent.change(screen.getByLabelText('Media file'), { target: { files: [new File(['data'], 'proof.png', { type: 'image/png' })] } }); fireEvent.click(screen.getByRole('button', { name: 'Upload and inspect' })); }

test('library selection retains default alt, supports intentional empty alt and excludes private grants from documents', async () => {
  mount(); await open('Choose from library'); fireEvent.click(await screen.findByRole('button', { name: 'Use proof.png' }));
  expect(screen.getByLabelText('Master media 1 alt text')).toHaveValue('Original description');
  expect(screen.getByTestId('document')).not.toHaveTextContent('https');
  fireEvent.change(screen.getByLabelText('Master media 1 alt text'), { target: { value: '' } });
  expect(screen.getByTestId('document')).toHaveTextContent('"alt_text":""');
  fireEvent.click(screen.getByRole('button', { name: 'Remove Master media 1' })); expect(screen.getByTestId('document')).toHaveTextContent('[]');
});
test('filename search submits explicitly and type filters remain bounded', async () => {
  mount(); await open('Choose from library'); await screen.findByRole('button', { name: 'Use proof.png' }); const calls=get.mock.calls.length;
  fireEvent.change(screen.getByLabelText('Search filenames'), { target: { value: 'proof' } }); expect(get.mock.calls).toHaveLength(calls);
  fireEvent.keyDown(screen.getByLabelText('Search filenames'), { key: 'Enter' });
  await waitFor(() => expect(get).toHaveBeenCalledWith('/admin/social/media/assets', expect.objectContaining({ params: expect.objectContaining({ q: 'proof', page: 1, page_size: 20 }) })));
  fireEvent.change(screen.getByLabelText('Media type'), { target: { value: 'image' } });
  await waitFor(() => expect(get).toHaveBeenCalledWith('/admin/social/media/assets', expect.objectContaining({ params: expect.objectContaining({ kind: 'image' }) })));
});
test('upload directly uses isolated storage fetch and selects only after authoritative completion', async () => {
  mount(); await startUpload(); await screen.findByLabelText('Master media 1 alt text');
  expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/quarantine/'), expect.objectContaining({ credentials: 'omit', redirect: 'error', headers: { 'Content-Type': 'image/png', 'If-None-Match': '*' } }));
  expect(post).toHaveBeenCalledWith(`/admin/social/media/uploads/${id}/complete`, { expected_version: 1 }, expect.anything());
});
test('lost accepted PUT then412 reaches inspection using original grant and command', async () => {
  const fetch=global.fetch as jest.Mock; fetch.mockRejectedValueOnce(new Error('lost response')).mockResolvedValueOnce({ ok: false, status: 412 });
  mount(); await startUpload(); const retry=await screen.findByRole('button', { name: 'Retry this upload' });
  expect(post.mock.calls.filter(call=>call[0].endsWith('/complete'))).toHaveLength(0); fireEvent.click(retry);
  await screen.findByLabelText('Master media 1 alt text'); expect(fetch).toHaveBeenCalledTimes(2); expect(fetch.mock.calls[0][0]).toBe(fetch.mock.calls[1][0]);
  expect(post.mock.calls.filter(call=>call[0].endsWith('/uploads'))).toHaveLength(1); expect(post.mock.calls.filter(call=>call[0].endsWith('/complete'))).toHaveLength(1);
});
test('ambiguous completion retries same key/version without a second byte upload', async () => {
  let count=0; post.mockImplementation(async (path: string) => { if(!path.endsWith('/complete')) return { data: grant() }; if(++count===1) throw { isAxiosError: true }; return { data: asset() }; });
  mount(); await startUpload(); fireEvent.click(await screen.findByRole('button', { name: 'Retry this upload' })); await screen.findByLabelText('Master media 1 alt text');
  const calls=post.mock.calls.filter(call=>call[0].endsWith('/complete')); expect(calls).toHaveLength(2); expect(calls[0]).toEqual(calls[1]); expect(global.fetch).toHaveBeenCalledTimes(1);
});
test('private previews load on demand and refresh after an expired storage response', async () => {
  mount(<Harness initial={[{ asset_id: id, alt_text: 'Post description', caption_asset_id: null }]} />);
  expect(get.mock.calls.some(call=>call[0].endsWith('/preview'))).toBe(false); fireEvent.click(screen.getByRole('button', { name: 'Load private preview' }));
  const image=await screen.findByRole('img', { name: 'Post description' }); expect(image).toHaveAttribute('src',expect.stringContaining('/ready/'));
  fireEvent.error(image); fireEvent.click(screen.getByRole('button',{ name:'Refresh private preview' })); await screen.findByRole('img',{ name:'Post description' }); expect(get.mock.calls.filter(call=>call[0].endsWith('/preview'))).toHaveLength(2);
});
test('unconfigured upload stays disabled while a usable library remains enabled', async () => {
  get.mockResolvedValue({ data:{ ...capabilities, upload_available:false, allowed_mime_types:[], unavailable_reason:'Storage is unavailable.' } });
  mount(); await screen.findByText('Storage is unavailable.'); expect(screen.getByRole('button',{ name:'Upload media' })).toBeDisabled(); expect(screen.getByRole('button',{ name:'Choose from library' })).toBeEnabled();
});
test('account media and intentional empty alt text remain isolated from other accounts', async () => {
  function Accounts() {
    const master:SocialContent={ text:'',link:null,hashtags:[],media:[] }, [targets,setTargets]=useState<DocumentTarget[]>([{ account_id:actor,format:'image',overrides:{} },{ account_id:id,format:'image',overrides:{} }]), [selected,select]=useState(0);
    return <><button onClick={()=>select(1)}>Second account</button><SocialOverrides target={targets[selected]} master={master} onChange={value=>setTargets(current=>current.map(item=>item.account_id===value.account_id?value:item))} /><output data-testid='accounts'>{JSON.stringify(targets)}</output></>;
  }
  mount(<Accounts />); fireEvent.click(screen.getByRole('button',{ name:'Customize media' })); await open('Choose from library'); fireEvent.click(await screen.findByRole('button',{ name:'Use proof.png' }));
  fireEvent.change(screen.getByLabelText('Account media 1 alt text'),{ target:{ value:'' } }); const document=JSON.parse(screen.getByTestId('accounts').textContent!);
  expect(document[0].overrides.media).toEqual({ mode:'replace',value:[{ asset_id:id,alt_text:'',caption_asset_id:null }] }); expect(document[1].overrides).toEqual({});
  fireEvent.click(screen.getByRole('button',{ name:'Second account' })); expect(screen.queryByLabelText('Account media 1 alt text')).not.toBeInTheDocument();
});

test('late upload attachment uses current parent state and preserves newer text edits', async () => {
  let finish!: (value: unknown) => void;
  post.mockImplementation((path: string) => path.endsWith('/complete') ? new Promise(resolve=>{ finish=resolve; }) : Promise.resolve({ data:grant() }));
  function Editor() {
    const [input,setInput]=useState({ text:'Original',media:[] as MediaReference[] });
    return <><button onClick={()=>setInput({ ...input,text:'Edited' })}>Edit text while uploading</button><SocialMedia label='Master' media={input.media} onChange={media=>setInput({ ...input,media })} /><output data-testid='parent'>{JSON.stringify(input)}</output></>;
  }
  mount(<Editor />); await startUpload(); await waitFor(()=>expect(post.mock.calls.some(call=>call[0].endsWith('/complete'))).toBe(true));
  fireEvent.click(screen.getByRole('button',{ name:'Edit text while uploading' })); finish({ data:asset() });
  await screen.findByLabelText('Master media 1 alt text'); expect(screen.getByTestId('parent')).toHaveTextContent('Edited');
});
test('late completion does not attach to a changed editor context', async () => {
  let finish!: (value: unknown) => void; const attach=jest.fn();
  post.mockImplementation((path: string) => path.endsWith('/complete') ? new Promise(resolve=>{ finish=resolve; }) : Promise.resolve({ data:grant() }));
  function Editor() { const [context,setContext]=useState('account-one'); return <><button onClick={()=>setContext('account-two')}>Switch upload context</button><SocialMedia contextKey={context} label='Account' media={[]} onChange={attach} /></>; }
  mount(<Editor />); await startUpload(); await waitFor(()=>expect(post.mock.calls.some(call=>call[0].endsWith('/complete'))).toBe(true));
  fireEvent.click(screen.getByRole('button',{ name:'Switch upload context' })); finish({ data:asset() });
  await waitFor(()=>expect(screen.queryByText('Inspecting actual media bytes…')).not.toBeInTheDocument()); expect(attach).not.toHaveBeenCalled();
});
test('unmounted upload may complete to the library but cannot invoke an old attachment callback', async () => {
  let finish!: (value: unknown) => void; const attach=jest.fn();
  post.mockImplementation((path: string) => path.endsWith('/complete') ? new Promise(resolve=>{ finish=resolve; }) : Promise.resolve({ data:grant() }));
  const tree=mount(<SocialMedia label='Master' media={[]} onChange={attach} />); await startUpload();
  await waitFor(()=>expect(post.mock.calls.some(call=>call[0].endsWith('/complete'))).toBe(true)); tree.unmount(); finish({ data:asset() });
  await new Promise(resolve=>setTimeout(resolve,20)); expect(attach).not.toHaveBeenCalled();
});

test('each media control group keeps unique accessible descriptions when runtime is unavailable', async () => {
  get.mockResolvedValue({ data:{ ...capabilities,upload_available:false,library_available:false,allowed_mime_types:[],unavailable_reason:'Private media is not configured.' } });
  const tree=mount(<div>{['Master','Account','Account'].map((label,index)=><section aria-label={`Media group ${index}`} key={index}><SocialMedia label={label} media={[]} onChange={jest.fn()} /></section>)}</div>);
  await waitFor(()=>expect(screen.getAllByText('Private media is not configured.')).toHaveLength(3));
  const ids=Array.from(tree.container.querySelectorAll('section')).map(section=>{
    const buttons=section.querySelectorAll('button'),id=buttons[0].getAttribute('aria-describedby');
    expect(id).toBeTruthy(); expect(buttons[1]).toHaveAttribute('aria-describedby',id); expect(section.querySelector(`[id="${id}"]`)).toHaveTextContent('Private media is not configured.');
    expect(buttons[0]).toBeDisabled(); expect(buttons[1]).toBeDisabled(); return id;
  });
  expect(new Set(ids).size).toBe(3);
});
