/** Runtime contracts for the users endpoints; TypeScript types alone are not validation. */
export interface UserSummary {
  id: string;
  email: string | null;
  display_name: string | null;
  roles: string[];
  created_at: string | null;
  last_sign_in_at: string | null;
  email_confirmed: boolean;
  banned_until: string | null;
}
export interface UserDetail extends UserSummary {
  app_metadata: Record<string, unknown>;
  user_metadata: Record<string, unknown>;
  updated_at: string | null;
}
export interface UserList {
  users: UserSummary[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}
export interface UserAck {
  ok: true;
  audit_recorded: boolean;
  email?: string | null;
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const validUserId = (id: string) => UUID.test(id);
const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);
const nullableString = (value: unknown) => value === null || typeof value === 'string';
/** Require a real ISO calendar date and clock time, including provider timezone offsets. */
const isUserTimestamp = (value: unknown) => {
  if (value === null) return true;
  if (
    typeof value !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
  )
    return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  const calendar = new Date(0);
  calendar.setUTCFullYear(year, month, 0);
  return (
    year >= 1 &&
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    day <= calendar.getUTCDate() &&
    Number(value.slice(11, 13)) <= 23 &&
    Number(value.slice(14, 16)) <= 59 &&
    Number(value.slice(17, 19)) <= 59 &&
    Number.isFinite(Date.parse(value))
  );
};
const sensitiveKeys = [
  'token',
  'secret',
  'password',
  'credential',
  'apikey',
  'authorization',
  'actionlink',
  'emailotp',
  'privatekey',
];
/** Reject credential fields or invalid JSON recursively; bound nesting to 25 levels. */
function isSafeMetadata(value: unknown, depth = 0): boolean {
  if (depth > 25) return false;
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (Array.isArray(value)) return value.every((item) => isSafeMetadata(item, depth + 1));
  if (!record(value)) return false;
  return Object.entries(value).every(([key, item]) => {
    const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, '');
    return (
      !sensitiveKeys.some((marker) => normalized.includes(marker)) &&
      isSafeMetadata(item, depth + 1)
    );
  });
}
const failed = (value: Record<string, unknown>) =>
  ['error', 'errors', 'error_code'].some((key) => key in value) ||
  ['ok', 'success'].some((key) => key in value && value[key] !== true);
const roles = (value: unknown): value is string[] =>
  Array.isArray(value) &&
  value.every((r) => typeof r === 'string' && r.trim().length > 0) &&
  new Set(value).size === value.length;
function invalid(): never {
  throw new Error('Invalid users response. Refresh to verify the current state.');
}
export function parseUser(value: unknown): UserSummary {
  if (
    !record(value) ||
    typeof value.id !== 'string' ||
    !validUserId(value.id) ||
    failed(value) ||
    !nullableString(value.email) ||
    !nullableString(value.display_name) ||
    !roles(value.roles) ||
    !isUserTimestamp(value.created_at) ||
    !isUserTimestamp(value.last_sign_in_at) ||
    !isUserTimestamp(value.banned_until) ||
    typeof value.email_confirmed !== 'boolean'
  )
    invalid();
  return value as unknown as UserSummary;
}
export function parseUserDetail(value: unknown, expectedId: string): UserDetail {
  const user = parseUser(value);
  if (
    user.id.toLowerCase() !== expectedId.toLowerCase() ||
    !record(value) ||
    !record(value.app_metadata) ||
    !record(value.user_metadata) ||
    !isUserTimestamp(value.updated_at) ||
    !isSafeMetadata(value.app_metadata) ||
    !isSafeMetadata(value.user_metadata)
  )
    invalid();
  return value as unknown as UserDetail;
}
/**
 * Require a complete page drawn from an exact matching total. Empty pages beyond
 * that total remain navigable; partial rows, phantom next pages and malformed
 * payloads throw before rendering a count or user identity.
 */
export function parseUserList(value: unknown, expectedPage: number, pageSize: number): UserList {
  if (
    !Number.isSafeInteger(expectedPage) ||
    expectedPage < 1 ||
    !Number.isSafeInteger(pageSize) ||
    pageSize < 1 ||
    pageSize > 100 ||
    !record(value) ||
    failed(value) ||
    !Array.isArray(value.users) ||
    !Number.isSafeInteger(value.total) ||
    (value.total as number) < 0 ||
    value.page !== expectedPage ||
    value.page_size !== pageSize ||
    typeof value.has_more !== 'boolean'
  )
    invalid();
  const users = value.users.map(parseUser);
  const start = (expectedPage - 1) * pageSize;
  if (
    users.length !== Math.max(0, Math.min(pageSize, (value.total as number) - start)) ||
    value.has_more !== start + pageSize < (value.total as number) ||
    new Set(users.map((u) => u.id.toLowerCase())).size !== users.length
  )
    invalid();
  return {
    users,
    total: value.total as number,
    page: expectedPage,
    page_size: pageSize,
    has_more: value.has_more,
  };
}
/** Accept provider success with either persisted or failed audit status. */
export function parseUserAck(value: unknown, email?: string): UserAck {
  if (
    !record(value) ||
    value.ok !== true ||
    failed(value) ||
    typeof value.audit_recorded !== 'boolean' ||
    (email !== undefined && value.email !== email)
  )
    invalid();
  return value as unknown as UserAck;
}
export function parseRoleAck(
  value: unknown,
  id: string,
  expectedRoles: string[]
): UserDetail & UserAck {
  const detail = parseUserDetail(value, id);
  const ack = parseUserAck(value);
  if (
    detail.roles.length !== expectedRoles.length ||
    detail.roles.some((role) => !expectedRoles.includes(role))
  )
    invalid();
  return { ...detail, ...ack };
}
export function userPage(value: string | null): number {
  const page = Number(value ?? '1');
  return Number.isSafeInteger(page) && page > 0 ? page : 1;
}
export function userError(error: unknown, fallback: string): string {
  if (record(error) && record(error.response) && record(error.response.data)) {
    const detail = error.response.data.detail;
    if (typeof detail === 'string') return detail;
  }
  return fallback;
}
