/**
 * AuthProvider – React context for authentication state (Supabase)
 *
 * Wraps the app and provides `useAuth()` hook to any component:
 *   - user / profile / isAuthenticated / isLoading
 *   - login / register / logout helpers
 *
 * All auth state is managed by Supabase. The session is persisted
 * automatically in cookies (via @supabase/ssr) — no manual
 * localStorage token management is needed.
 */
'use client';

import { createClient } from '@/lib/supabase/client';
import { getBaseUrl } from '@/lib/utils/getBaseUrl';
import { profileMatchesIdentity } from '@/lib/auth/roles';
import type { User } from '@supabase/supabase-js';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

/* ───── Public profile shape (from profiles table) ───── */
export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  roles: string[];
}

/* ───── Context shape ───── */
interface AuthContextValue {
  /** Raw Supabase auth user (null when signed out) */
  authUser: User | null;
  /** Public profile from profiles table */
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<UserProfile>;
  register: (email: string, password: string, displayName?: string) => Promise<UserProfile>;
  logout: () => Promise<void>;
  /** Re-fetch the profile from the profiles table */
  refreshUser: () => Promise<void>;
  /** Send a password-reset email to the given address */
  resetPassword: (email: string) => Promise<void>;
  /** Set a new password for the currently authenticated user (after reset link) */
  updatePassword: (newPassword: string) => Promise<void>;
  /** Send a confirmation link to the new email; email changes once user clicks it */
  changeEmail: (newEmail: string) => Promise<void>;
  /** Permanently delete the authenticated user's account */
  deleteAccount: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/* ───── Helpers ───── */
const supabase = createClient();

async function fetchProfile(userId: string): Promise<UserProfile | null> {
  const { data, error } = await supabase
    .from('profiles')
    .select('id, email, display_name, roles')
    .eq('id', userId)
    .maybeSingle();
  if (error || !profileMatchesIdentity(data, userId)) return null;
  return data as UserProfile;
}

/* ───── Provider ───── */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const mounted = useRef(false);
  const generation = useRef(0);
  const identity = useRef<string | null>(null);
  const identityLifetime = useRef(0);

  const isCurrent = useCallback((ticket: number, id: string) =>
    mounted.current && generation.current === ticket && identity.current === id, []);

  const changeSession = useCallback((next: User | null) => {
    const ticket = ++generation.current;
    if (identity.current !== (next?.id ?? null)) ++identityLifetime.current;
    identity.current = next?.id ?? null;
    if (mounted.current) {
      setAuthUser(next);
      setUser(null);
      setIsLoading(!!next);
    }
    return ticket;
  }, []);

  const loadSessionProfile = useCallback(async (next: User, ticket: number) => {
    let profile: UserProfile | null = null;
    try {
      profile = await fetchProfile(next.id);
    } catch {
      // Failed profile evidence never retains a previous privileged profile.
    }
    if (isCurrent(ticket, next.id)) {
      setUser(profile);
      setIsLoading(false);
    }
  }, [isCurrent]);

  // On mount, restore session + subscribe to auth changes
  useEffect(() => {
    mounted.current = true;
    setUser(null);
    setIsLoading(true);
    const initialGeneration = ++generation.current;
    const timers = new Set<ReturnType<typeof setTimeout>>();

    // GoTrue awaits subscribers while holding its auth lock. Profile requests
    // obtain a token through getSession(), so start them after this callback
    // returns and the SDK releases that lock.
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!mounted.current) return;
      const next = session?.user ?? null;
      const ticket = changeSession(next);
      if (next) {
        const timer = setTimeout(() => {
          timers.delete(timer);
          if (isCurrent(ticket, next.id)) void loadSessionProfile(next, ticket);
        }, 0);
        timers.add(timer);
      }
    });

    // A newer auth event owns state even if the initial read finishes later.
    void supabase.auth.getSession().then(({ data, error }) => {
      if (!mounted.current || generation.current !== initialGeneration) return;
      const next = error ? null : data.session?.user ?? null;
      const ticket = changeSession(next);
      if (next) void loadSessionProfile(next, ticket);
    }).catch(() => {
      if (mounted.current && generation.current === initialGeneration) changeSession(null);
    });

    return () => {
      mounted.current = false;
      ++generation.current;
      ++identityLifetime.current;
      timers.forEach(timer => clearTimeout(timer));
      subscription.unsubscribe();
    };
  }, [changeSession, isCurrent, loadSessionProfile]);

  const login = useCallback(async (email: string, password: string): Promise<UserProfile> => {
    const started = generation.current;
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    const ticket = generation.current === started || identity.current === data.user.id
      ? changeSession(data.user) : null;
    try {
      const profile = await fetchProfile(data.user.id);
      if (ticket !== null && isCurrent(ticket, data.user.id)) setUser(profile);
      if (!profile) throw new Error('Profile not found');
      return profile;
    } finally {
      if (ticket !== null && isCurrent(ticket, data.user.id)) setIsLoading(false);
    }
  }, [changeSession, isCurrent]);

  const register = useCallback(
    async (email: string, password: string, displayName?: string): Promise<UserProfile> => {
      const started = generation.current;
      let ticket: number | null = null;
      let registeringId: string | null = null;

      try {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            data: { display_name: displayName || null },
            emailRedirectTo: `${getBaseUrl()}/auth/callback`,
          },
        });
        if (error) throw error;
        if (!data.user) throw new Error('Registration failed');
        const registeredUser = data.user;
        registeringId = data.user.id;
        ticket = generation.current === started || identity.current === data.user.id
          ? changeSession(data.user) : null;
        const lifetime = identityLifetime.current;
        const readRegistrationProfile = () => {
          // A retry after a same-identity refresh is a fresh observation, but
          // cannot rejoin a session that signed out or changed actors meanwhile.
          if (ticket !== null && mounted.current && identity.current === registeredUser.id && identityLifetime.current === lifetime) {
            ticket = ++generation.current;
            setUser(null);
            setIsLoading(true);
          } else {
            ticket = null;
          }
          return fetchProfile(registeredUser.id);
        };

        // Wait for the DB trigger to create the profile
        // Short initial delay then quick retries — the trigger usually completes within 200-500ms
        let profile: UserProfile | null = null;
        const delays = [300, 500, 800];

        for (const ms of delays) {
          await new Promise((r) => setTimeout(r, ms));
          profile = await readRegistrationProfile();
          if (profile) break;
        }

        // Fallback: create the profile client-side if the trigger was too slow
        if (!profile) {
          const { error: insertErr } = await supabase.from('profiles').insert({
            id: data.user.id,
            email: data.user.email ?? email,
            display_name: displayName || null,
            roles: ['citizen'],
          });
          if (!insertErr) {
            profile = await readRegistrationProfile();
          }
        }

        // Build a guaranteed profile object
        const finalProfile: UserProfile = profile ?? {
          id: data.user.id,
          email: data.user.email ?? email,
          display_name: displayName || null,
          roles: ['citizen'],
        };

        // Registration completion cannot resurrect an identity after a newer
        // sign-out/sign-in event, or overwrite a newer profile observation.
        if (ticket !== null && isCurrent(ticket, data.user.id)) setUser(finalProfile);

        return finalProfile;
      } finally {
        if (ticket !== null && registeringId !== null && isCurrent(ticket, registeringId)) setIsLoading(false);
      }
    },
    [changeSession, isCurrent]
  );

  const logout = useCallback(async () => {
    changeSession(null);
    await supabase.auth.signOut();
  }, [changeSession]);

  const refreshUser = useCallback(async () => {
    let ticket = ++generation.current;
    if (mounted.current) {
      setUser(null);
      setIsLoading(true);
    }
    try {
      const { data, error } = await supabase.auth.getUser();
      if (error) throw error;
      if (!mounted.current || generation.current !== ticket) return;
      const next = data.user ?? null;
      ticket = changeSession(next);
      if (next) {
        const profile = await fetchProfile(next.id);
        if (isCurrent(ticket, next.id)) setUser(profile);
      }
    } finally {
      if (mounted.current && generation.current === ticket) setIsLoading(false);
    }
  }, [changeSession, isCurrent]);

  const resetPassword = useCallback(async (email: string) => {
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${getBaseUrl()}/auth/callback?next=/reset-password`,
    });
    if (error) throw error;
  }, []);

  const updatePassword = useCallback(async (newPassword: string) => {
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw error;
  }, []);

  const changeEmail = useCallback(async (newEmail: string) => {
    const { error } = await supabase.auth.updateUser(
      { email: newEmail },
      { emailRedirectTo: `${getBaseUrl()}/auth/callback` }
    );
    if (error) throw error;
  }, []);

  const deleteAccount = useCallback(async () => {
    const res = await fetch('/api/account/delete', { method: 'DELETE' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || 'Failed to delete account');
    }
    // Don't signOut here — let the caller show a farewell UI first,
    // then call logout() when ready to clear the session.
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      authUser,
      user,
      isAuthenticated: !!authUser,
      isLoading,
      login,
      register,
      logout,
      refreshUser,
      resetPassword,
      updatePassword,
      changeEmail,
      deleteAccount,
    }),
    [
      authUser,
      user,
      isLoading,
      login,
      register,
      logout,
      refreshUser,
      resetPassword,
      updatePassword,
      changeEmail,
      deleteAccount,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/* ───── Hook ───── */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}
