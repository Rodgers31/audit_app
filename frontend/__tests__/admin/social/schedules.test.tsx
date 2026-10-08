import SocialWorkspace from '@/components/admin/social/SocialWorkspace';
import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import { SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, actorId, post, system, target } from '../../../tests/socialFixtures';
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));
const get = api.get as jest.Mock, send = api.post as jest.Mock;
function scheduled(): SocialPost {
  const p = post({ editorial_state: 'approved', delivery_status: 'scheduled', targets: [{ ...target('queued'), next_action_at: '2027-01-05T07:00:00Z' }] });
  return { ...p, publication: { id: '00000000-0000-4000-8000-000000000060', revision_id: p.revision_id, version: 2, approved_at: '2026-10-03T12:00:00Z', approved_by: actorId, scheduled_for: '2027-01-05T07:00:00Z', schedule_timezone: 'Africa/Nairobi', requested_local_time: '2027-01-05T10:00:00', cancel_requested_at: null } };
}
function mount(p?: SocialPost) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  if (p) qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  return render(<QueryClientProvider client={qc}>{p ? <SocialComposer initialPost={p} accounts={accounts} system={system} /> : <SocialWorkspace />}</QueryClientProvider>);
}
beforeEach(() => { jest.clearAllMocks(); Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => '00000000-0000-4000-8000-000000000099' }); });
test('scheduled and history request global filters and paginate mixed results', async () => {
  const p = scheduled(); p.delivery_status = 'partially_published';
  get.mockImplementation(async (path, options) => ({ data: path.endsWith('/accounts') ? { accounts } : path.endsWith('/system/status') ? system : path.endsWith('/posts') ? { posts: [p], total: 21, page: options.params.page, page_size: 20, has_more: options.params.page === 1 } : p }));
  mount(); fireEvent.click(screen.getByRole('button', { name: 'Scheduled' }));
  await screen.findByText('21 scheduled posts');
  expect(get).toHaveBeenCalledWith('/admin/social/posts', expect.objectContaining({ params: expect.objectContaining({ page: 1, delivery_filter: 'scheduled' }) }));
  expect(screen.getByRole('button', { name: /What does unsupported expenditure mean/ })).toBeInTheDocument();
  expect(screen.getByText(/2027-01-05T10:00:00 · Africa\/Nairobi/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next page' })); await screen.findByText('Page 2');
  expect(get).toHaveBeenLastCalledWith('/admin/social/posts', expect.objectContaining({ params: expect.objectContaining({ page: 2, delivery_filter: 'scheduled' }) }));
  fireEvent.click(screen.getByRole('button', { name: 'History' })); await screen.findByText('21 history posts');
  expect(get).toHaveBeenCalledWith('/admin/social/posts', expect.objectContaining({ params: expect.objectContaining({ page: 1, delivery_filter: 'history' }) }));
});
test('rescheduling keeps the reviewed revision and explicit version guards', async () => {
  const p = scheduled(); get.mockResolvedValue({ data: p });
  send.mockImplementation(async (_path, body) => ({ data: { ...p, version: 2, publication: { ...p.publication, version: 3, scheduled_for: '2027-01-06T07:00:00.000Z', requested_local_time: body.schedule.local_time }, targets: p.targets.map(t => ({ ...t, next_action_at: '2027-01-06T07:00:00.000Z' })) } }));
  mount(p);
  fireEvent.change(screen.getByLabelText('Reason for schedule change'), { target: { value: 'Move the unchanged announcement' } });
  fireEvent.change(screen.getByLabelText('New local publish time'), { target: { value: '2027-01-06T10:00' } });
  fireEvent.click(screen.getByRole('button', { name: 'Confirm reschedule' })); await screen.findByText(/Schedule updated for unchanged unsent destinations/);
  expect(send).toHaveBeenCalledWith(`/admin/social/posts/${p.id}/reschedule`, { expected_version: 1, publication_id: p.publication!.id, expected_publication_version: 2, reason: 'Move the unchanged announcement', acknowledged_warning_codes: [], schedule: { local_time: '2027-01-06T10:00:00', timezone: 'Africa/Nairobi', utc_offset: '+03:00' } }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }));
});
test('ambiguous receipt keeps the original intent and never claims success', async () => {
  const p = scheduled(); get.mockResolvedValue({ data: p });
  send.mockResolvedValue({ data: { ...p, version: 2, publication: { ...p.publication, version: 3, id: '00000000-0000-4000-8000-000000000061' } } });
  mount(p); fireEvent.change(screen.getByLabelText('Reason for schedule change'), { target: { value: 'Move unchanged delivery' } });
  fireEvent.click(screen.getByRole('button', { name: 'Publish unsent now' })); await screen.findByText(/schedule response did not confirm/);
  expect(screen.queryByText(/Publish-now accepted/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Publish unsent now' })); await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
  expect(send.mock.calls[0]).toEqual(send.mock.calls[1]);
});
test('worker claim disables due-time controls while cancellation remains explicit', async () => {
  const p = scheduled(); p.targets[0].state = 'claimed'; get.mockResolvedValue({ data: p }); mount(p);
  fireEvent.change(screen.getByLabelText('Reason for schedule change'), { target: { value: 'Review claim' } });
  expect(screen.getByRole('button', { name: 'Publish unsent now' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Cancel unsent deliveries' })).toBeEnabled();
});

test('publish-now preserves a successful account result and schedules only the other destination', async () => {
  const p = scheduled();
  p.document.targets.push({ account_id: accounts[1].id, format: 'image', overrides: {} });
  const published = { ...target('published', 'instagram'), published_at: '2026-10-03T12:05:00Z', remote_url: 'https://example.org/confirmed' };
  p.targets.push(published);
  get.mockResolvedValue({ data: p });
  send.mockImplementation(async () => {
    const due = new Date().toISOString();
    return { data: { ...p, version: 2, publication: { ...p.publication, version: 3, scheduled_for: due, schedule_timezone: 'UTC', requested_local_time: due.slice(0, -1) }, targets: [{ ...p.targets[0], next_action_at: due }, published] } };
  });
  mount(p);
  fireEvent.change(screen.getByLabelText('Reason for schedule change'), { target: { value: 'Advance only the unsent destination' } });
  fireEvent.click(screen.getByRole('button', { name: 'Publish unsent now' }));
  await screen.findByText(/Publish-now accepted for unchanged unsent destinations/);
  expect(screen.getByRole('link', { name: 'View Instagram post' })).toHaveAttribute('href', published.remote_url);
  expect(screen.getByText(/Confirmed publication: 2026-10-03T12:05:00Z/)).toBeInTheDocument();
});

test('a DST overlap needs an explicit offset and a gap cannot be rescheduled', async () => {
  const p = scheduled(); get.mockResolvedValue({ data: p }); mount(p);
  fireEvent.change(screen.getByLabelText('Reason for schedule change'), { target: { value: 'Select intended civil time' } });
  fireEvent.change(screen.getByLabelText('Schedule timezone'), { target: { value: 'America/Chicago' } });
  fireEvent.change(screen.getByLabelText('New local publish time'), { target: { value: '2027-11-07T01:30' } });
  expect(screen.getByRole('button', { name: 'Confirm reschedule' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('New UTC offset'), { target: { value: '-06:00' } });
  expect(screen.getByRole('button', { name: 'Confirm reschedule' })).toBeEnabled();
  fireEvent.change(screen.getByLabelText('New local publish time'), { target: { value: '2027-03-14T02:30' } });
  expect(screen.getByRole('button', { name: 'Confirm reschedule' })).toBeDisabled();
  expect(screen.getByText(/does not exist/)).toBeInTheDocument();
});

test('optional actual queue and schedule fixture export preserves the existing desktop/mobile styling', async () => {
  if (!process.env.SOCIAL_SCHEDULE_VISUAL_DIR) return;
  const { mkdirSync, readFileSync, writeFileSync } = await import('fs');
  const { resolve } = await import('path');
  const p = scheduled();
  p.targets.push({ ...target('published', 'instagram'), published_at: '2026-10-03T12:05:00Z', remote_url: 'https://example.org/confirmed' });
  p.document.targets.push({ account_id: accounts[1].id, format: 'image', overrides: {} });
  p.delivery_status = 'partially_published';
  get.mockImplementation(async path => ({ data: path.endsWith('/accounts') ? { accounts } : path.endsWith('/system/status') ? system : path.endsWith('/posts') ? { posts: [p], total: 1, page: 1, page_size: 20, has_more: false } : p }));
  const { container } = mount();
  fireEvent.click(screen.getByRole('button', { name: 'Scheduled' }));
  await screen.findByText('1 scheduled posts');
  fireEvent.click(screen.getByRole('button', { name: /What does unsupported expenditure mean/ }));
  await screen.findByRole('region', { name: 'Schedule management' });
  const dir = resolve(process.env.SOCIAL_SCHEDULE_VISUAL_DIR!); mkdirSync(dir, { recursive: true });
  const css = readFileSync(resolve('components/admin/social/social.module.css'), 'utf8');
  writeFileSync(resolve(dir, 'schedules.html'), `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Schedule management fixture</title><link rel="stylesheet" href="global.css"><style>${css}</style></head><body><div style="padding:8px;background:#fff6e5;text-align:center">TEST FIXTURES · NO LIVE ACCOUNTS OR PUBLICATION</div>${container.innerHTML}</body></html>`);
});

test('history shows independent confirmed timestamps and only verified HTTPS publication links', async () => {
  const p = scheduled();
  p.targets = [{ ...target('published'), published_at: '2026-10-03T12:05:00Z', remote_url: 'https://example.org/confirmed' }, { ...target('outcome_unknown', 'instagram'), remote_url: 'https://example.org/unconfirmed' }];
  get.mockImplementation(async path => ({ data: path.endsWith('/accounts') ? { accounts } : path.endsWith('/system/status') ? system : { posts: [p], total: 1, page: 1, page_size: 20, has_more: false } }));
  mount(); fireEvent.click(screen.getByRole('button', { name: 'History' }));
  expect(await screen.findByRole('link', { name: 'View Facebook published post' })).toHaveAttribute('href', 'https://example.org/confirmed');
  expect(screen.getByText(/confirmed 2026-10-03T12:05:00Z/)).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'View Instagram published post' })).not.toBeInTheDocument();
});
