import { decodeSummary, SocialApiError, socialApi } from '@/lib/api/social';
import api from '@/lib/api/axios';
import { actorId, post } from '../../../tests/socialFixtures';
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn() } }));
function schedule() { return { id: '00000000-0000-4000-8000-000000000060', revision_id: post().revision_id, version: 2, approved_at: '2026-10-03T12:00:00Z', approved_by: actorId, scheduled_for: '2027-01-05T07:00:00Z', schedule_timezone: 'Africa/Nairobi', requested_local_time: '2027-01-05T10:00:00', cancel_requested_at: null }; }
test('summary preserves compact exact schedule fields without a document', () => {
  const { document: _document, references: _references, ...p } = post({ publication: schedule() });
  expect(decodeSummary(p).publication).toEqual(schedule());
  expect(decodeSummary(p)).not.toHaveProperty('document');
});
test.each([
  { version: true }, { version: 0 }, { approved_by: 'bad' }, { approved_at: null },
  { scheduled_for: 'tomorrow' }, { cancel_requested_at: true }, { schedule_timezone: 'No/Such_Zone' },
  { requested_local_time: '2027-01-05T10:00:00+03:00' }, { credential: 'untrusted' },
])('malformed compact schedule fails closed: %j', fields => {
  expect(() => decodeSummary({ ...post(), publication: { ...schedule(), ...fields } })).toThrow(SocialApiError);
});
test('partial or missing publication metadata fails closed', () => {
  expect(() => decodeSummary({ ...post(), publication: { id: schedule().id } })).toThrow(SocialApiError);
  const { publication: _publication, ...missing } = post();
  expect(() => decodeSummary(missing)).toThrow(SocialApiError);
});
test('delivery filter goes to the server while only compact posts are requested', async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: { posts: [], total: 0, page: 1, page_size: 20, has_more: false } });
  await socialApi.posts(1, undefined, undefined, 'needs_attention');
  expect(api.get).toHaveBeenCalledWith('/admin/social/posts', expect.objectContaining({ params: { page: 1, page_size: 20, delivery_filter: 'needs_attention' } }));
});
