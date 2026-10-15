import { forgetConnectionRecovery, readConnectionRecovery, saveConnectionRecovery } from '@/components/admin/social/connections/connectionRecovery';

const key = 'auditgava.meta.connection-recovery.v1';
const flow = '4aadebe9-11ce-4207-afce-836cd86cc9da';
const expires = '2026-10-15T12:10:00.000Z';
const reference = { version: 1, actor: 'actor-a', flow, expires };
beforeEach(() => { jest.restoreAllMocks(); window.sessionStorage.clear(); jest.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-15T12:00:00Z')); });
afterEach(() => { jest.restoreAllMocks(); });

test('another actor cannot recover or erase a valid reference, even after returning to the original actor', () => {
  expect(saveConnectionRecovery('actor-a', flow, expires)).toBe(true);
  expect(readConnectionRecovery('actor-b')).toEqual({ flow: undefined, available: true });
  expect(readConnectionRecovery('actor-a')).toEqual({ flow, available: true });
  expect(forgetConnectionRecovery('actor-b', flow)).toBe(true);
  expect(readConnectionRecovery('actor-a').flow).toBe(flow);
  expect(forgetConnectionRecovery('actor-a', flow)).toBe(true);
  expect(readConnectionRecovery('actor-a').flow).toBeUndefined();
});

test.each([
  null, [], {}, { ...reference, version: true }, { ...reference, flow: '../../other' },
  { ...reference, expires: false }, { ...reference, expires: 'not-a-date' },
  { ...reference, expires: '2026-10-15T11:59:59Z' },
  { ...reference, expires: '2026-10-15T12:16:00Z' },
  { ...reference, code: 'must-not-be-restored' },
])('invalid or expired reference cannot become a recovery request: %p', value => {
  window.sessionStorage.setItem(key, JSON.stringify(value));
  expect(readConnectionRecovery('actor-a').flow).toBeUndefined();
});

test('blocked storage is explicitly unavailable and never a successful recovery', () => {
  jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('blocked', 'SecurityError'); });
  expect(readConnectionRecovery('actor-a')).toEqual({ flow: undefined, available: false });
});

test.each([true, 1, Infinity, [], {}, ' ', 'x'.repeat(129)])('an invalid actor cannot create a reference: %p', actor => {
  expect(saveConnectionRecovery(actor as unknown as string, flow, expires)).toBe(false);
  expect(window.sessionStorage.getItem(key)).toBeNull();
});
