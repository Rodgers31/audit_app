import { downloadAccountData } from '@/components/account/downloadAccountData';
import { createClient } from '@/lib/supabase/client';

jest.mock('@/lib/supabase/client', () => ({ createClient: jest.fn() }));
jest.mock('@/lib/api/base', () => ({ getApiBase: () => 'https://account-fixture.example.test' }));

const accountId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const otherAccount = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const previousFetch = globalThis.fetch;
const previousCreate = URL.createObjectURL;
const previousRevoke = URL.revokeObjectURL;
const request = jest.fn();
const createBlobUrl = jest.fn(() => 'blob:local-account-fixture');

function sessionFor(id: string) {
  jest.mocked(createClient).mockReturnValue({
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'inert-token', user: { id } } } }),
    },
  } as unknown as ReturnType<typeof createClient>);
}

function responseFor(id: string) {
  return {
    ok: true,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({ profile: { id }, watchlist: [], alerts: [] }),
  };
}

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(new Date('2026-04-19T03:45:00Z'));
  globalThis.fetch = request;
  URL.createObjectURL = createBlobUrl;
  URL.revokeObjectURL = jest.fn();
  sessionFor(accountId);
});

afterEach(() => {
  globalThis.fetch = previousFetch;
  URL.createObjectURL = previousCreate;
  URL.revokeObjectURL = previousRevoke;
  jest.clearAllMocks();
  jest.restoreAllMocks();
  jest.useRealTimers();
});

test('downloads JSON only for the current account and releases its temporary URL', async () => {
  request.mockResolvedValue(responseFor(accountId));
  let filename: string | undefined;
  jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    filename = this.download;
  });
  await downloadAccountData(accountId, new AbortController().signal);

  expect(filename).toBe('auditgava-data-2026-04-19.json');
  expect(request).toHaveBeenCalledWith('https://account-fixture.example.test/api/v1/user/export',
    expect.objectContaining({ headers: { Authorization: 'Bearer inert-token' }, cache: 'no-store' }));
  expect(createBlobUrl).toHaveBeenCalledWith(expect.objectContaining({ type: 'application/json' }));
  expect(document.querySelector('a[download]')).toBeNull();
  jest.runOnlyPendingTimers();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:local-account-fixture');
});

test('refuses a changed local session before sending a request', async () => {
  sessionFor(otherAccount);
  await expect(downloadAccountData(accountId, new AbortController().signal)).rejects.toThrow();
  expect(request).not.toHaveBeenCalled();
  expect(createBlobUrl).not.toHaveBeenCalled();
});

test('refuses a response associated with another account', async () => {
  request.mockResolvedValue(responseFor(otherAccount));
  await expect(downloadAccountData(accountId, new AbortController().signal)).rejects.toThrow();
  expect(createBlobUrl).not.toHaveBeenCalled();
});

test('does not share the completed export after the page aborts its request', async () => {
  const controller = new AbortController();
  request.mockImplementation(async () => {
    controller.abort();
    return responseFor(accountId);
  });
  await expect(downloadAccountData(accountId, controller.signal)).rejects.toThrow();
  expect(createBlobUrl).not.toHaveBeenCalled();
});
