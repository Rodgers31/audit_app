'use client';
import { createContext, useContext, useEffect, useState } from 'react';

const actor = { id: '00000000-0000-4000-8000-000000000001' };
const verified = { authUser: actor, user: { ...actor, roles: ['admin'] }, isAuthenticated: true, isLoading: false };
const pending = { ...verified, user: null, isLoading: true };
const Context = createContext<typeof verified | typeof pending>(pending);
export function FixtureAuth({ children }: { children: React.ReactNode }) {
  const [value, setValue] = useState<typeof verified | typeof pending>(pending);
  useEffect(() => {
    const scenario = new URLSearchParams(location.search).get('auth');
    if (scenario === 'restoring') return;
    const timer = setTimeout(() => setValue(scenario === 'citizen'
      ? { ...verified, user: { ...actor, roles: ['citizen'] } }
      : scenario === 'expired' ? { ...verified, user: null, isAuthenticated: false } : verified), 200);
    return () => clearTimeout(timer);
  }, []);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export const useAuth = () => useContext(Context);
