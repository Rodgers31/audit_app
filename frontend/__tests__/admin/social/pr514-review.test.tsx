import SocialScheduleControls from '@/components/admin/social/SocialScheduleControls';
import SocialComposer from '@/components/admin/social/SocialComposer';
import SocialWorkspace from '@/components/admin/social/SocialWorkspace';
import api from '@/lib/api/axios';
import { decodeSummary, SocialApiError, SocialHistoricalTarget, SocialPost } from '@/lib/api/social';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { accounts, actorId, post, system, target } from '../../../tests/socialFixtures';
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));
const get = api.get as jest.Mock, send = api.post as jest.Mock;
function scheduled(): SocialPost { return post({ editorial_state: 'approved', delivery_status: 'scheduled', targets: [{ ...target('queued'), next_action_at: '2027-01-05T07:00:00Z' }], publication: { version: 2, scheduled_for: '2027-01-05T07:00:00Z', schedule_timezone: 'Africa/Nairobi', requested_local_time: '2027-01-05T10:00:00' } }); }
function historical(state: SocialHistoricalTarget['state'], id: string): SocialHistoricalTarget {
  return { ...target(state), id, publication_id: '00000000-0000-4000-8000-000000000061', revision_id: '00000000-0000-4000-8000-000000000041', approved_at: '2026-10-03T12:00:00Z', approved_by: actorId, scheduled_for: null, cancel_requested_at: null, revoked_at: '2026-10-04T12:00:00Z', updated_at: '2026-10-04T12:00:00Z' };
}
function client() { return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); }
beforeEach(() => { jest.clearAllMocks(); Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: () => '00000000-0000-4000-8000-000000000099' }); });

test('publication refresh updates civil inputs and clears an obsolete DST choice; same-version polling preserves edits', () => {
  const p = scheduled(), qc = client();
  const controls = (value: SocialPost) => <QueryClientProvider client={qc}><SocialScheduleControls post={value} system={system} disabled={false} onUpdated={jest.fn()} /></QueryClientProvider>;
  const mounted = render(controls(p));
  fireEvent.change(screen.getByLabelText('New local publish time'), { target: { value: '2027-11-07T01:30' } });
  fireEvent.change(screen.getByLabelText('Schedule timezone'), { target: { value: 'America/Chicago' } });
  fireEvent.change(screen.getByLabelText('New UTC offset'), { target: { value: '-06:00' } });
  fireEvent.change(screen.getByLabelText('Reason for schedule change'), { target: { value: 'Review civil intent' } });
  mounted.rerender(controls({ ...p, targets: [{ ...p.targets[0], safe_error_message: 'Polling update' }] }));
  expect(screen.getByLabelText('New local publish time')).toHaveValue('2027-11-07T01:30');
  expect(screen.getByLabelText('New UTC offset')).toHaveValue('-06:00');
  mounted.rerender(controls({ ...p, version: p.version + 1, publication: { ...p.publication!, version: 3, schedule_timezone: 'America/New_York', requested_local_time: '2027-11-07T01:30:00', scheduled_for: '2027-11-07T05:30:00Z' } }));
  expect(screen.getByLabelText('Schedule timezone')).toHaveValue('America/New_York');
  expect(screen.getByLabelText('New UTC offset')).toHaveValue('');
  expect(screen.getByRole('button', { name: 'Confirm reschedule' })).toBeDisabled();
  mounted.rerender(controls({ ...p, publication: { ...p.publication!, id: '00000000-0000-4000-8000-000000000065', schedule_timezone: 'UTC', requested_local_time: '2028-03-01T12:30:00', scheduled_for: '2028-03-01T12:30:00Z' } }));
  expect(screen.getByLabelText('Schedule timezone')).toHaveValue('UTC');
  expect(screen.getByLabelText('New local publish time')).toHaveValue('2028-03-01T12:30');
});

test('publish-now receipt resets old future inputs to the accepted UTC schedule', async () => {
  const p = scheduled(), qc = client(); let acceptedTime = '';
  function Harness() { const [current, update] = useState(p); return <SocialScheduleControls post={current} system={system} disabled={false} onUpdated={update} />; }
  send.mockImplementation(async () => {
    const due = new Date().toISOString(); acceptedTime = due.slice(0, 16);
    return { data: { ...p, version: 2, publication: { ...p.publication!, version: 3, scheduled_for: due, schedule_timezone: 'UTC', requested_local_time: due.slice(0, -1) }, targets: [{ ...p.targets[0], next_action_at: due }] } };
  });
  render(<QueryClientProvider client={qc}><Harness /></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText('Reason for schedule change'), { target: { value: 'Advance reviewed delivery' } });
  fireEvent.click(screen.getByRole('button', { name: 'Publish unsent now' }));
  await screen.findByText(/Publish-now accepted for unchanged unsent destinations/);
  expect(screen.getByLabelText('Schedule timezone')).toHaveValue('UTC');
  expect(screen.getByLabelText('New local publish time')).toHaveValue(acceptedTime);
  expect(screen.getByRole('button', { name: 'Confirm reschedule' })).toBeDisabled();
});

test('editing the draft preserves a same-version schedule edit while disabling submission', () => {
  const p = scheduled(), qc = client(); get.mockResolvedValue({ data: p }); qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={accounts} system={system} /></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText('New local publish time'), { target: { value: '2027-01-08T10:00' } });
  fireEvent.change(screen.getByLabelText('Schedule timezone'), { target: { value: 'Europe/London' } });
  fireEvent.change(screen.getByLabelText('Internal title'), { target: { value: 'Edited draft' } });
  expect(screen.getByLabelText('New local publish time')).toHaveValue('2027-01-08T10:00');
  expect(screen.getByLabelText('Schedule timezone')).toHaveValue('Europe/London');
  expect(screen.getByRole('button', { name: 'Confirm reschedule' })).toBeDisabled();
});

test.each(['failed', 'blocked', 'reconciling', 'outcome_unknown'] as const)('attention always shows current %s plus past attention, even behind a full preview', async state => {
  const p = scheduled(); p.targets[0].state = state;
  p.historical_targets = [historical('failed', '00000000-0000-4000-8000-000000000062'), ...Array.from({ length: 19 }, (_, index) => historical('cancelled', `00000000-0000-4000-8000-${String(100 + index).padStart(12, '0')}`))];
  p.historical_target_count = 21;
  get.mockImplementation(async path => ({ data: path.endsWith('/accounts') ? { accounts } : path.endsWith('/system/status') ? system : { posts: [p], total: 1, page: 1, page_size: 20, has_more: false } }));
  const { container } = render(<QueryClientProvider client={client()}><SocialWorkspace /></QueryClientProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Needs attention' }));
  await screen.findByText('1 posts needing attention');
  const row = within(screen.getByRole('complementary', { name: 'Post queue' }));
  expect(row.getByText(new RegExp(`Current Facebook.*${state.replaceAll('_', ' ')}`))).toBeInTheDocument();
  expect(row.getByText(/Historical Facebook.*failed/)).toBeInTheDocument();
  expect(row.queryByText(/Historical Facebook.*cancelled/)).not.toBeInTheDocument();
  if (state === 'failed' && process.env.SOCIAL_SCHEDULE_VISUAL_DIR) {
    const { mkdirSync, readFileSync, writeFileSync } = await import('fs');
    const { resolve } = await import('path');
    const dir = resolve(process.env.SOCIAL_SCHEDULE_VISUAL_DIR); mkdirSync(dir, { recursive: true });
    const css = readFileSync(resolve('components/admin/social/social.module.css'), 'utf8');
    writeFileSync(resolve(dir, 'attention.html'), `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Attention queue fixture</title><link rel="stylesheet" href="global.css"><style>${css}</style></head><body><div style="padding:8px;background:#fff6e5;text-align:center">TEST FIXTURES · NO LIVE ACCOUNTS OR PUBLICATION</div>${container.innerHTML}</body></html>`);
  }
});

test('attention prefers the current result and deduplicates its historical projection', async () => {
  const p = scheduled(); p.targets[0].state = 'blocked';
  p.historical_targets = [historical('failed', p.targets[0].id)]; p.historical_target_count = 1;
  get.mockImplementation(async path => ({ data: path.endsWith('/accounts') ? { accounts } : path.endsWith('/system/status') ? system : { posts: [p], total: 1, page: 1, page_size: 20, has_more: false } }));
  render(<QueryClientProvider client={client()}><SocialWorkspace /></QueryClientProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Needs attention' }));
  await screen.findByText('1 posts needing attention');
  expect(screen.getByText(/Current Facebook.*blocked/)).toBeInTheDocument();
  expect(screen.queryByText(/Historical Facebook.*failed/)).not.toBeInTheDocument();
});

test('attention keeps all unresolved past states when the current revision has no authorization', async () => {
  const p = post();
  p.historical_targets = (['failed', 'blocked', 'reconciling', 'outcome_unknown'] as const).map((state, index) => historical(state, `00000000-0000-4000-8000-${String(200 + index).padStart(12, '0')}`));
  p.historical_target_count = 4;
  get.mockImplementation(async path => ({ data: path.endsWith('/accounts') ? { accounts } : path.endsWith('/system/status') ? system : { posts: [p], total: 1, page: 1, page_size: 20, has_more: false } }));
  render(<QueryClientProvider client={client()}><SocialWorkspace /></QueryClientProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Needs attention' }));
  await screen.findByText('1 posts needing attention');
  for (const state of ['failed', 'blocked', 'reconciling', 'outcome unknown']) expect(screen.getByText(new RegExp(`Historical Facebook.*${state}`))).toBeInTheDocument();
  expect(screen.queryByText(/Current Facebook/)).not.toBeInTheDocument();
});

test.each(['2027-02-29T10:00:00', '2027-02-30T10:00:00', '2027-04-31T10:00:00', '2027-01-05T24:00:00', '0000-01-05T10:00:00', '1900-02-29T10:00:00', '2100-02-29T10:00:00', '2027-13-01T10:00:00', '2027-01-05T10:60:00', '2027-01-05T10:00:60'])('civil decoder rejects impossible calendar values: %s', requested_local_time => {
  const p = scheduled();
  expect(() => decodeSummary({ ...p, publication: { ...p.publication!, requested_local_time } })).toThrow(SocialApiError);
});
test.each(['approved_at', 'scheduled_for', 'cancel_requested_at'] as const)('schedule timestamp calendar validation also protects %s', field => {
  const p = scheduled(); expect(() => decodeSummary({ ...p, publication: { ...p.publication!, [field]: '2027-02-30T10:00:00Z' } })).toThrow(SocialApiError);
});
test.each(['2028-02-29T10:00:00', '2000-02-29T10:00:00.123456', '2027-04-30T23:59:59.999999', '2027-01-05T10:00'])('civil decoder retains valid leap, fractional and minute values: %s', requested_local_time => {
  const p = scheduled(); expect(decodeSummary({ ...p, publication: { ...p.publication!, requested_local_time } }).publication!.requested_local_time).toBe(requested_local_time);
});
test('schedule and historical timestamps accept exact valid calendar fields with microseconds and offsets', () => {
  const p = scheduled(), instant = '2028-02-29T10:00:00.123456+03:00';
  p.publication!.approved_at = instant;
  p.historical_targets = [{ ...historical('failed', '00000000-0000-4000-8000-000000000066'), approved_at: instant }]; p.historical_target_count = 1;
  const decoded = decodeSummary(p);
  expect(decoded.publication!.approved_at).toBe(instant);
  expect(decoded.historical_targets[0].approved_at).toBe(instant);
  expect(() => decodeSummary({ ...p, historical_targets: [{ ...p.historical_targets[0], published_at: '2027-02-30T10:00:00Z' }] })).toThrow(SocialApiError);
});
