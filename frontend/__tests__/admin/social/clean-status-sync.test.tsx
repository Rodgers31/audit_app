import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import { SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, actorId, deliverySystem, post, publicationReceipt, target, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('@/components/admin/social/GeneratedEvidence', () => () => null);
const get = api.get as jest.Mock, send = api.post as jest.Mock;
let current: SocialPost;
const clients: QueryClient[] = [];
function mount(p = post()) {
  current = p;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(qc); qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={accounts} system={deliverySystem()} /></QueryClientProvider>);
  return qc;
}
async function update(qc: QueryClient, p: SocialPost) {
  current = p;
  await act(async () => { qc.setQueryData(socialKeys.detail(actorId, p.id), p); });
}
beforeEach(() => {
  jest.clearAllMocks(); window.history.replaceState({}, '', '/admin/social');
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/media/capabilities') ? { upload_available: false, library_available: true, allowed_mime_types: [], max_image_bytes: 10485760, max_video_bytes: 52428800, unavailable_reason: null } : current }));
  send.mockImplementation(async (path: string) => ({ data: path.endsWith('/validate') ? validation(current) : current }));
});
afterEach(() => { cleanup(); clients.splice(0).forEach(qc => qc.clear()); });

test('own generated publication reconciles its clean delivery version without inventing a new content revision or clearing human review', async () => {
  const p = post({ origin_type: 'generated', editorial_state: 'pending_review' });
  send.mockImplementation(async (path: string) => {
    if (path.endsWith('/validate')) return { data: validation(current) };
    const due = new Date().toISOString();
    current = post({ ...current, version: current.version + 1, editorial_state: 'approved', targets: [{ ...target('queued'), next_action_at: due }], publication: { revision_id: current.revision_id, scheduled_for: due, schedule_timezone: 'UTC', requested_local_time: due.slice(0, -1) } });
    return { data: publicationReceipt(current) };
  });
  mount(p);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Publish now', exact: true })).toBeEnabled());
  fireEvent.click(screen.getByRole('checkbox', { name: /I checked the facts and sources/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Publish now', exact: true }));
  await screen.findByText(/Publication accepted for 1 destination/);
  await screen.findByText('approved · version 2');
  expect(screen.queryByRole('button', { name: 'Load current revision' })).not.toBeInTheDocument();
  expect(screen.queryByText(/newer.*(revision|post version) is available/i)).not.toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: /I checked the facts and sources/ })).toBeChecked();
  expect(screen.queryByRole('link', { name: /View Facebook post/ })).not.toBeInTheDocument();
  expect(send.mock.calls.map(([path]) => path.split('/').at(-1))).toEqual(['validate', 'publish']);
  expect(screen.queryByText('Checking the saved revision…')).not.toBeInTheDocument();
  expect(screen.getByText('Publication was requested for this saved revision. Review the delivery results below.')).toBeVisible();
});

test('clean same-revision status refresh updates the post version without resetting input or attestation', async () => {
  const p = post(), qc = mount(p);
  fireEvent.click(screen.getByRole('checkbox', { name: /I checked the facts and sources/ }));
  await update(qc, post({ ...p, version: 2, editorial_state: 'approved', targets: [target('ready')], publication: {} }));
  await screen.findByText('approved · version 2');
  expect(screen.getByLabelText('Post text')).toHaveValue(p.document.master.text);
  expect(screen.getByRole('checkbox', { name: /I checked the facts and sources/ })).toBeChecked();
  expect(screen.queryByRole('button', { name: 'Load current revision' })).not.toBeInTheDocument();
  expect(send).not.toHaveBeenCalled();
});

test('same-revision delivery refresh preserves dirty local text and explicit stale review', async () => {
  const p = post(), qc = mount(p);
  fireEvent.change(screen.getByLabelText('Post text'), { target: { value: 'Keep this local edit.' } });
  await update(qc, post({ ...p, version: 2, editorial_state: 'pending_review' }));
  expect(screen.getByLabelText('Post text')).toHaveValue('Keep this local edit.');
  expect(await screen.findByText(/A newer saved post version is available/)).toHaveTextContent('Your local edits are preserved.');
  expect(screen.getByRole('button', { name: 'Load current revision' })).toBeDisabled();
  expect(screen.getByText('Unsaved edits')).toBeInTheDocument();
});

test.each(['new revision', 'conflicting content'])('%s cannot silently overwrite a clean draft', async change => {
  const p = post(), qc = mount(p);
  await update(qc, post({ ...p, version: 2, ...(change === 'new revision' ? { revision_id: '00000000-0000-4000-8000-000000000042' } : { document: { ...p.document, master: { ...p.document.master, text: 'Different saved content.' } } }) }));
  expect(screen.getByLabelText('Post text')).toHaveValue(p.document.master.text);
  await screen.findByText(/A newer saved post version is available/);
  expect(screen.getByText('draft · version 1')).toBeInTheDocument();
  expect(screen.getByText(/A newer saved post version is available/)).not.toHaveTextContent('Your local edits are preserved.');
  expect(screen.getByRole('button', { name: 'Load current revision' })).toBeEnabled();
});

test('an in-flight command defers clean status reconciliation until its response settles', async () => {
  let finish: (value: unknown) => void = () => { throw new Error('Validation did not start'); };
  const p = post(), qc = mount(p);
  send.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await update(qc, post({ ...p, version: 2, editorial_state: 'pending_review' }));
  expect(await screen.findByRole('button', { name: 'Load current revision' })).toBeDisabled();
  await act(async () => { finish({ data: validation(p) }); });
  await screen.findByText('pending review · version 2');
  expect(screen.queryByRole('button', { name: 'Load current revision' })).not.toBeInTheDocument();
});


test('a generated ready authorization still validates the refreshed post version before human publication', async () => {
  const p=post({origin_type:'generated',editorial_state:'pending_review'}),qc=mount(p);
  await waitFor(()=>expect(send).toHaveBeenCalledTimes(1));
  await update(qc,post({...p,version:2,editorial_state:'approved',targets:[target('ready')],publication:{scheduled_for:null}}));
  await screen.findByText('approved · version 2');
  await waitFor(()=>expect(send).toHaveBeenCalledTimes(2));
  expect(send.mock.calls.map(([path,body])=>({action:path.split('/').at(-1),version:body.expected_version}))).toEqual([{action:'validate',version:1},{action:'validate',version:2}]);
  await waitFor(()=>expect(screen.getByRole('button',{name:'Publish now',exact:true})).toBeEnabled());
});
