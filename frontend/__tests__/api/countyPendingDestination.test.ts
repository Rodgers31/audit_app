import { apiClient } from '@/lib/api/axios';
import { getCountyPendingBills } from '@/lib/api/debt';
jest.mock('@/lib/api/axios', () => ({apiClient: {get: jest.fn()}}));
const get = apiClient.get as jest.Mock;
const receipt = {county_id: '71', total_pending: 86899380000, pending_bills_as_at: '2026-06-30', selection: {as_at: '2026-06-30'}, pending_bills_notes: [{code: 'chapter_table_differs', table: 'Table 2.10', chapter_table: 'Table 4.3', chapter_total: '86000000000'}]};
beforeEach(() => jest.clearAllMocks());
test('real response notes survive and date is passed to the HTTP adapter', async () => {
  get.mockResolvedValue({data: receipt});
  expect(await getCountyPendingBills('71', undefined, '2026-06-30')).toEqual(receipt);
  expect(get.mock.calls[0][0]).toBe('/pending-bills/counties/71?as_at=2026-06-30');
});
test.each([
  {county_id:'72'}, {pending_bills_as_at:'2025-06-30'}, {selection:{as_at:'2025-06-30'}},
  {total_pending:'86899380000'}, {total_pending:-1}, {total_pending:Number.POSITIVE_INFINITY},
  {total_pending:null,selection:{as_at:'2025-06-30'}},
  {pending_bills_notes: ['reader note']}, {pending_bills_notes: [null]}, {pending_bills_notes: [{code:'constructor'}]},
])('wrong receipt or invalid amount is refused: %j', async change => {
  get.mockResolvedValue({data:{...receipt,...change}});
  await expect(getCountyPendingBills('71', undefined, '2026-06-30')).rejects.toThrow(/does not match/);
});
test('a dated absence remains absent without a date for an invented figure', async () => {
  const absent = {...receipt,total_pending:null,pending_bills_as_at:null}; get.mockResolvedValue({data:absent});
  expect(await getCountyPendingBills('71', undefined, '2026-06-30')).toEqual(absent);
});
test.each([null, true, false, '', [], {}, ' ', '1e3', '-1', '100\n', '9'.repeat(400)])('chapter amount %j cannot be coerced into a public figure', async chapter_total => {
  get.mockResolvedValue({data:{...receipt,pending_bills_notes:[{code:'chapter_table_differs',chapter_total}]}});
  await expect(getCountyPendingBills('71', undefined, '2026-06-30')).rejects.toThrow(/does not match/);
});
test.each(['0', '0.00', '86000000000', '86000000000.00'])('explicit chapter decimal %s is retained', async chapter_total => {
  const value = {...receipt,pending_bills_notes:[{code:'chapter_table_differs',chapter_total}]}; get.mockResolvedValue({data:value});
  expect(await getCountyPendingBills('71', undefined, '2026-06-30')).toEqual(value);
});
