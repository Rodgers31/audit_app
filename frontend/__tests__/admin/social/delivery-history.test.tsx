import SocialComposer from '@/components/admin/social/SocialComposer';
import SocialWorkspace from '@/components/admin/social/SocialWorkspace';
import api from '@/lib/api/axios';
import { decodeHistory, decodeSummary, SocialApiError, socialApi } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { accounts, actorId, post, system, target } from '../../../tests/socialFixtures';
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));
const get = api.get as jest.Mock;
function receipt() {
  return { ...target('cancelled'), publication_id: '00000000-0000-4000-8000-000000000061',
    revision_id: '00000000-0000-4000-8000-000000000041', approved_by: actorId, approved_at: '2026-10-03T12:00:00Z',
    scheduled_for: '2027-01-05T07:00:00Z', cancel_requested_at: null, revoked_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
}
function revised(count = 1) { return Object.assign(post(), { historical_targets: [receipt()], historical_target_count: count }); }
function mount(p = revised(), workspace = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  return render(<QueryClientProvider client={qc}>{workspace ? <SocialWorkspace /> : <SocialComposer initialPost={p} accounts={accounts} system={system} />}</QueryClientProvider>);
}
beforeEach(() => jest.clearAllMocks());
test('past receipt stays separate from draft publication and current command targets', async () => {
  const p = revised(); get.mockResolvedValue({ data: p }); mount(p);
  const region = await screen.findByRole('region', { name: 'Delivery history' });
  expect(within(region).getByText('cancelled')).toBeInTheDocument();
  expect(within(region).getByText(/2027-01-05T07:00:00Z/)).toBeInTheDocument();
  expect(within(region).getByText(/00000000-0000-4000-8000-000000000041/)).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: 'Schedule management' })).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/Reason to retry/)).not.toBeInTheDocument();
});
test('history endpoint is fetched only on inspection and pages exact post receipts', async () => {
  const p = revised(21), first = Array.from({ length: 20 }, (_, i) => ({ ...receipt(), id: `00000000-0000-4000-8000-${String(100 + i).padStart(12, '0')}` }));
  p.historical_targets = first;
  const last = { ...receipt(), id: '00000000-0000-4000-8000-000000000120', state: 'published' as const, remote_url: 'https://example.org/confirmed-past', published_at: '2026-10-05T12:00:00Z' };
  get.mockImplementation(async (path, options) => ({ data: path.endsWith('/history') ? { post_id: p.id, targets: options.params.page === 1 ? first : [last], total: 21, page: options.params.page, page_size: 20, has_more: options.params.page === 1 } : p }));
  const { container } = mount(p);
  expect(get.mock.calls.filter(([path]) => path.endsWith('/history'))).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: 'Inspect all delivery history' }));
  await screen.findByText('Delivery history page 1 of 2');
  fireEvent.click(screen.getByRole('button', { name: 'Next history page' }));
  const link = await screen.findByRole('link', { name: 'View historical Facebook post' });
  expect(link).toHaveAttribute('href', last.remote_url);
  expect(screen.getByText(/Confirmed publication: 2026-10-05T12:00:00Z/)).toBeInTheDocument();
  expect(get).toHaveBeenCalledWith(`/admin/social/posts/${p.id}/history`, expect.objectContaining({ params: { page: 2, page_size: 20 } }));
  if (process.env.SOCIAL_SCHEDULE_VISUAL_DIR) {
    const { mkdirSync, readFileSync, writeFileSync } = await import('fs');
    const { resolve } = await import('path');
    const dir = resolve(process.env.SOCIAL_SCHEDULE_VISUAL_DIR); mkdirSync(dir, { recursive: true });
    const css = readFileSync(resolve('components/admin/social/social.module.css'), 'utf8');
    writeFileSync(resolve(dir, 'history.html'), `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Delivery history fixture</title><link rel="stylesheet" href="global.css"><style>${css}</style></head><body><div style="padding:8px;background:#fff6e5;text-align:center">TEST FIXTURES · NO LIVE ACCOUNTS OR PUBLICATION</div><div class="workspace">${container.innerHTML}</div></body></html>`);
  }
});
test('global history renders revoked receipts even though current draft targets are empty', async () => {
  const p = revised(); get.mockImplementation(async path => ({ data: path.endsWith('/accounts') ? { accounts } : path.endsWith('/system/status') ? system : path.endsWith('/posts') ? { posts: [p], total: 1, page: 1, page_size: 20, has_more: false } : p }));
  mount(p, true); fireEvent.click(screen.getByRole('button', { name: 'History' }));
  await screen.findByText('1 history posts');
  expect(screen.getByText(/Historical Facebook.*cancelled/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /What does unsupported expenditure mean/ }));
  await screen.findByRole('region', { name: 'Delivery history' });
  expect(get.mock.calls.some(([path]) => path === `/admin/social/posts/${p.id}`)).toBe(false);
});
test('summary preserves the exact bounded historical identity', () => {
  const p = revised(); const summary = decodeSummary(p);
  expect(summary).toHaveProperty('historical_targets', p.historical_targets);
  expect(summary).toHaveProperty('historical_target_count', 1);
});
test.each([{ publication_id: 'bad' }, { revision_id: null }, { state: 'queued' }, { published_at: 'tomorrow' }, { access_token: 'untrusted' }])('historical receipt rejects malformed or private fields %j', change => {
  expect(() => decodeSummary({ ...revised(), historical_targets: [{ ...receipt(), ...change }] })).toThrow(SocialApiError);
});
test.each([true, -1, 0])('historical count is strict and consistent: %j', count => {
  expect(() => decodeSummary({ ...revised(), historical_target_count: count })).toThrow(SocialApiError);
});
test('history decoding rejects ambiguous counts, duplicate targets and foreign post/page receipts', async () => {
  const p = revised(), page = { post_id: p.id, targets: [receipt()], total: 1, page: 1, page_size: 20, has_more: false };
  expect(decodeHistory(page).targets).toEqual(p.historical_targets);
  for (const change of [{ total: true }, { targets: [receipt(), receipt()], total: 2 }, { total: 21 }, { has_more: true }, { page_size: 21 }, { page: 0 }]) expect(() => decodeHistory({ ...page, ...change })).toThrow(SocialApiError);
  get.mockResolvedValue({ data: { ...page, post_id: '00000000-0000-4000-8000-000000000099' } });
  await expect(socialApi.history(p.id, 1)).rejects.toThrow(SocialApiError);
  get.mockResolvedValue({ data: { ...page, page: 2, targets: [] } });
  await expect(socialApi.history(p.id, 1)).rejects.toThrow(SocialApiError);
});
