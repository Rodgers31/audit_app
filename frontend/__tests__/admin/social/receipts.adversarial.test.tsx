import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import { decodePost, SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, actorId, instagramId, post, system, target, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));

const get = api.get as jest.Mock, send = api.post as jest.Mock, patch = api.patch as jest.Mock;
let clients: QueryClient[];
function mount(p: SocialPost) {
  const decoded = decodePost(p);
  get.mockResolvedValue({ data: decoded });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(qc); qc.setQueryData(socialKeys.detail(actorId, p.id), decoded);
  render(<QueryClientProvider client={qc}><SocialComposer initialPost={decoded} accounts={accounts} system={system} /></QueryClientProvider>);
}
beforeEach(() => {
  jest.clearAllMocks(); clients = [];
  Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => '00000000-0000-4000-8000-000000000099' });
});
afterEach(() => clients.forEach(qc => qc.clear()));

test.each(['empty', 'partial', 'duplicate', 'different post'])('a %s publication receipt cannot certify acceptance of all selected destinations', async attack => {
  const base = post();
  const p = post({ document: { ...base.document, targets: [base.document.targets[0], { account_id: instagramId, format: 'image', overrides: {} }] } });
  const targets = [target('queued'), target('queued', 'instagram')].map(t => ({ id: t.id, account_id: t.account_id, platform: t.platform, status: 'queued' }));
  const receipt = { post_id: p.id, publication_id: '00000000-0000-4000-8000-000000000060', status: 'queued', scheduled_for: null, targets };
  if (attack === 'empty') receipt.targets = [];
  if (attack === 'partial') receipt.targets = targets.slice(0, 1);
  if (attack === 'duplicate') receipt.targets = [targets[0], { ...targets[0], id: '00000000-0000-4000-8000-000000000052' }];
  if (attack === 'different post') receipt.post_id = '00000000-0000-4000-8000-000000000011';
  send.mockImplementation(async path => ({ data: path.endsWith('/validate') ? validation(p) : receipt }));
  mount(p);
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Publish now' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Publish now' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled());
  expect(send.mock.calls.some(c => c[0].endsWith('/publish'))).toBe(true);
  expect(screen.queryByText(/Publication accepted/)).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent(/INVALID RESPONSE/);
});

test.each(['old version', 'different post'])('a successful save response containing %s cannot discard the pending local edit', async attack => {
  const p = post();
  const response = post({ ...(attack === 'different post' ? { id: '00000000-0000-4000-8000-000000000011', version: 2 } : {}) });
  patch.mockResolvedValue({ data: response }); mount(p);
  fireEvent.change(screen.getByLabelText('Master text'), { target: { value: 'Local facts that must survive a wrong save receipt' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled());
  expect(patch).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText('Master text')).toHaveValue('Local facts that must survive a wrong save receipt');
  expect(screen.queryByText(/Draft saved/)).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent(/INVALID RESPONSE/);
});
