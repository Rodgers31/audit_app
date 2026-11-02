import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import { SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, actorId, deliverySystem, post, target, validation } from '@/tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
// Drive the actual composer's async media ownership callback independently of
// uploader details, which have separate real-component/byte fixtures.
jest.mock('@/components/admin/social/SocialMedia', () => ({ __esModule: true,
  default: ({ onBusyChange }: { onBusyChange?: (busy: boolean) => void }) =>
    <button type='button' onClick={() => onBusyChange?.(true)}>Begin inert media operation</button> }));
const get = api.get as jest.Mock, send = api.post as jest.Mock;
let server: SocialPost, qc: QueryClient;
beforeEach(() => {
  jest.clearAllMocks(); server = post();
  window.history.replaceState({}, '', '/admin/social');
  qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  qc.setQueryData(socialKeys.detail(actorId, server.id), server);
  get.mockImplementation(async () => ({ data: server }));
  send.mockImplementation(async () => ({ data: validation(server) }));
});
afterEach(() => qc.clear());
function mount() {
  return render(<QueryClientProvider client={qc}><SocialComposer initialPost={server} accounts={accounts} system={deliverySystem()} /></QueryClientProvider>);
}
async function receive(next: SocialPost) {
  const oldKey = socialKeys.detail(actorId, post().id);
  server = next;
  await act(async () => { qc.setQueryData(oldKey, next); });
}
const metadata = () => post({ version: 2, editorial_state: 'approved', delivery_status: 'queued', targets: [target('queued')], publication: {} });

test('clean identical immutable revision adopts newer delivery metadata without a false revision conflict', async () => {
  mount(); await receive(metadata());
  await screen.findByText('approved · version 2');
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Load current revision' })).not.toBeInTheDocument());
  expect(screen.getByLabelText('Post text', { exact: true })).toHaveValue(post().document.master.text);
  expect(screen.getByRole('button', { name: 'Cancel unsent deliveries' })).toBeEnabled();
  expect(send).not.toHaveBeenCalled();
});
test('dirty local text is preserved even when the server revision content is unchanged', async () => {
  mount(); fireEvent.change(screen.getByLabelText('Post text', { exact: true }), { target: { value: 'Independent unsaved text' } });
  await receive(metadata());
  expect(await screen.findByRole('button', { name: 'Load current revision' })).toBeDisabled();
  expect(screen.getByLabelText('Post text', { exact: true })).toHaveValue('Independent unsaved text');
  expect(send).not.toHaveBeenCalled();
});
test.each(['revision', 'content', 'post'] as const)('%s identity drift cannot be silently adopted', async drift => {
  mount(); const next = metadata();
  if (drift === 'revision') next.revision_id = '00000000-0000-4000-8000-000000000041';
  if (drift === 'content') next.document = { ...next.document, master: { ...next.document.master, text: 'Different server text' } };
  if (drift === 'post') next.id = '00000000-0000-4000-8000-000000000011';
  await receive(next);
  expect(await screen.findByRole('button', { name: 'Load current revision' })).toBeEnabled();
  expect(screen.getByLabelText('Post text', { exact: true })).toHaveValue(post().document.master.text);
  expect(send).not.toHaveBeenCalled();
});
test('active media ownership prevents metadata adoption while its callback remains busy', async () => {
  mount(); fireEvent.click(screen.getByRole('button', { name: 'Begin inert media operation' }));
  await receive(metadata());
  expect(await screen.findByRole('button', { name: 'Load current revision' })).toBeDisabled();
  expect(send).not.toHaveBeenCalled();
});
test('an in-flight validation retains its original version until the command settles', async () => {
  let finish: ((value: unknown) => void) | undefined;
  send.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  mount(); fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
  await receive(metadata());
  expect(await screen.findByRole('button', { name: 'Load current revision' })).toBeDisabled();
  expect(send.mock.calls[0][1]).toMatchObject({ expected_version: 1 });
  await act(async () => { finish?.({ data: validation(post()) }); });
});
