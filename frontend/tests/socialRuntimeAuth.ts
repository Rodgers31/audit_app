/** Test-project-only alias. This module is never imported by the product app. */
declare global {
  interface Window { __SOCIAL_FIXTURE_ROLE__?: 'admin' | 'editor' | 'signed-out' }
}
export function useAuth() {
  const role = typeof window === 'undefined' ? 'admin' : window.__SOCIAL_FIXTURE_ROLE__ ?? 'admin';
  return { user: role === 'signed-out' ? null : { id: '00000000-0000-4000-8000-000000000001', roles: [role] }, isAuthenticated: role !== 'signed-out', isLoading: false };
}
export function createClient() { return { auth: { getSession: async () => ({ data: { session: null } }) } }; }
