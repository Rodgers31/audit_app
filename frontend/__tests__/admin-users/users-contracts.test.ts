import {
  parseRoleAck,
  parseUser,
  parseUserAck,
  parseUserDetail,
  parseUserList,
  userPage,
} from '@/lib/admin/users';

const id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const summary = {
  id,
  email: 'fixture@example.invalid',
  display_name: null,
  roles: ['citizen'],
  created_at: null,
  last_sign_in_at: null,
  email_confirmed: false,
  banned_until: null,
};
const detail = {
  ...summary,
  app_metadata: {},
  user_metadata: {},
  updated_at: null,
};

test('accepts legitimate empty roles and acknowledged audit failure', () => {
  expect(parseUser({ ...summary, roles: [] }).roles).toEqual([]);
  expect(parseUserAck({ ok: true, audit_recorded: false }).audit_recorded).toBe(false);
});

test.each([
  null,
  undefined,
  [],
  true,
  0,
  NaN,
  Infinity,
  {},
  { ok: 1, audit_recorded: true },
  { ok: true, audit_recorded: 'false' },
  { ok: false, audit_recorded: true },
])('rejects malformed mutation verdict %#', (value) => expect(() => parseUserAck(value)).toThrow());

test.each([{ success: false }, { error: 'provider failed' }, { error_code: 'rejected' }])(
  'rejects internally contradictory mutation verdict %#',
  (extra) => {
    expect(() => parseUserAck({ ok: true, audit_recorded: true, ...extra })).toThrow();
  }
);

test('rejects wrong returned role state', () => {
  expect(() =>
    parseRoleAck({ ...detail, ok: true, audit_recorded: true }, id, ['admin'])
  ).toThrow();
});

test('rejects duplicate identities despite UUID case variation', () => {
  expect(() =>
    parseUserList(
      {
        users: [summary, { ...summary, id: id.toUpperCase() }],
        total: 2,
        page: 1,
        page_size: 2,
        has_more: false,
      },
      1,
      2
    )
  ).toThrow();
});

test.each([0, -1, false, true])('direct parser rejects invalid page argument %p', (page) => {
  const users = Array.from({ length: Number(page) <= 0 ? 2 : 0 }, (_, index) => ({
    ...summary,
    id: `00000000-0000-4000-8000-${String(index + 10).padStart(12, '0')}`,
  }));
  expect(() =>
    parseUserList(
      { users, total: 0, page, page_size: 2, has_more: Number(page) < 0 },
      page as number,
      2
    )
  ).toThrow();
});

test.each([0, -1, false, true])(
  'direct parser rejects invalid page size argument %p',
  (pageSize) => {
    expect(() =>
      parseUserList(
        {
          users: [],
          total: 0,
          page: 1,
          page_size: pageSize,
          has_more: Number(pageSize) < 0,
        },
        1,
        pageSize as number
      )
    ).toThrow();
  }
);

test.each(['2026-02-31T00:00:00Z', '2026-10-08T24:00:00Z', '123', '1'])(
  'rejects malformed ISO timestamp %p',
  (created) => {
    expect(() => parseUser({ ...summary, created_at: created })).toThrow();
  }
);

test.each([
  '2026-10-08T12:30:00Z',
  '2026-10-08T12:30:00.123456+00:00',
  '2026-10-08T15:30:00+03:00',
])('accepts supported provider ISO timestamp %p', (created) => {
  expect(parseUser({ ...summary, created_at: created }).created_at).toBe(created);
});

test('preserves ordinary JSON metadata', () => {
  const metadata = {
    display: 'Fixture name',
    preferences: [{ nested: [null, true, false, 12.5] }],
  };
  expect(parseUserDetail({ ...detail, user_metadata: metadata }, id).user_metadata).toEqual(
    metadata
  );
});

test.each(['apiKey', 'api-key', 'authorization', 'action_link', 'email_otp', 'private_key'])(
  'detail rejects credential metadata key %p',
  (key) => {
    expect(() =>
      parseUserDetail(
        {
          ...detail,
          user_metadata: { nested: [{ [key]: 'inert-credential-marker' }] },
        },
        id
      )
    ).toThrow();
  }
);

test.each([NaN, Infinity, -Infinity])('detail rejects non-JSON metadata numbers %p', (value) => {
  expect(() => parseUserDetail({ ...detail, app_metadata: { nested: [{ value }] } }, id)).toThrow();
});

test.each(['nope', '0', '-1', 'NaN', 'Infinity'])(
  'invalid URL page recovers to page one %p',
  (page) => {
    expect(userPage(page)).toBe(1);
  }
);

test('rejects ISO year zero which the provider datetime contract cannot represent', () => {
  expect(() => parseUser({...summary,created_at:'0000-01-01T00:00:00Z'})).toThrow();
});
