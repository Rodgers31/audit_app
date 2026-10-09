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
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

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
  // Suppress onAuthStateChange profile fetch while register() is handling it
  const [registering, setRegistering] = useState(false);

  // On mount, restore session + subscribe to auth changes
  useEffect(() => {
    // 1. Get initial session
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (session?.user) {
        setAuthUser(session.user);
        const profile = await fetchProfile(session.user.id);
        setUser(profile);
      }
      setIsLoading(false);
    });

    // 2. Listen for future auth events (sign-in, sign-out, token refresh)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (session?.user) {
        setAuthUser(session.user);
        // Skip profile fetch during registration — register() handles it
        if (!registering) {
          const profile = await fetchProfile(session.user.id);
          setUser(profile);
        }
      } else {
        setAuthUser(null);
        setUser(null);
      }
    });

    return () => subscription.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<UserProfile> => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    const profile = await fetchProfile(data.user.id);
    if (!profile) throw new Error('Profile not found');
    return profile;
  }, []);

  const register = useCallback(
    async (email: string, password: string, displayName?: string): Promise<UserProfile> => {
      // Prevent onAuthStateChange from racing with our profile creation
      setRegistering(true);

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

        // Wait for the DB trigger to create the profile
        // Short initial delay then quick retries — the trigger usually completes within 200-500ms
        let profile: UserProfile | null = null;
        const delays = [300, 500, 800];

        for (const ms of delays) {
          await new Promise((r) => setTimeout(r, ms));
          profile = await fetchProfile(data.user.id);
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
            profile = await fetchProfile(data.user.id);
          }
        }

        // Build a guaranteed profile object
        const finalProfile: UserProfile = profile ?? {
          id: data.user.id,
          email: data.user.email ?? email,
          display_name: displayName || null,
          roles: ['citizen'],
        };

        // Set auth state so the rest of the app (WatchlistProvider etc.) sees a signed-in user
        setAuthUser(data.user);
        setUser(finalProfile);

        return finalProfile;
      } finally {
        setRegistering(false);
      }
    },
    []
  );

  const logout = useCallback(async () => {
    await supabase.auth.signOut();
    setAuthUser(null);
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const {
      data: { user: currentUser },
    } = await supabase.auth.getUser();
    if (currentUser) {
      setAuthUser(currentUser);
      const profile = await fetchProfile(currentUser.id);
      setUser(profile);
    } else {
      setAuthUser(null);
      setUser(null);
    }
  }, []);

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
