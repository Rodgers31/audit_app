/** Runtime role validation shared by browser guards and server middleware. */
export function validRoles(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(role => typeof role === 'string' && role.trim().length > 0);
}

export function profileMatchesIdentity(profile: unknown, id: string): profile is { id: string; roles: string[] } {
  if (!profile || typeof profile !== 'object' || Array.isArray(profile)) return false;
  const row = profile as Record<string, unknown>;
  return row.id === id && validRoles(row.roles);
}
