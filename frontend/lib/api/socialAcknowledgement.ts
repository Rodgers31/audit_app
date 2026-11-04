/** Compare the complete JSON contract without depending on object-key order.
 * Arrays retain order: reordered scenes, media or facts are a changed request.
 */
export function sameJson(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (left === null || right === null || typeof left !== 'object' || typeof right !== 'object') return false;
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((value, index) => sameJson(value, right[index]));
  const a = left as Record<string, unknown>, b = right as Record<string, unknown>;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(key => Object.hasOwn(b, key) && sameJson(a[key], b[key]));
}

/** UUID fields are serialized canonically by the existing Pydantic models.
 * This projection is only for checking an acknowledgement; callers retain the
 * original wire body and durable retry identity exactly as submitted.
 */
export function acknowledgedUuid(value: string): string | undefined {
  let hex: string;
  if (/^[0-9a-f]{32}$/i.test(value)) hex = value;
  else if (/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value)) hex = value.replaceAll('-', '');
  else if (/^\{[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}$/i.test(value)) hex = value.slice(1, -1).replaceAll('-', '');
  else if (value.startsWith('urn:uuid:') && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value.slice(9))) hex = value.slice(9).replaceAll('-', '');
  else return undefined;
  hex = hex.toLowerCase();
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** StringConstraints(strip_whitespace=True) uses Unicode White_Space. Do not
 * trim evidence, URLs, identifiers or the request itself with this helper.
 */
export function acknowledgedStudioText(value: string): string {
  return value.replace(/^[\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g, '');
}
