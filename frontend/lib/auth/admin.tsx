/**
 * Admin utilities — role-checking hooks and guard component
 *
 * Usage:
 *   const { isAdmin, isLoading } = useAdmin();
 *
 *   <AdminGuard>
 *     <SecretAdminPanel />
 *   </AdminGuard>
 */
'use client';

import { useAuth } from '@/lib/auth/AuthProvider';
import { validRoles } from '@/lib/auth/roles';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

/* ───── Hook: useAdmin ───── */
export function useAdmin() {
  const { user, authUser, isAuthenticated, isLoading } = useAuth();

  const roles = validRoles(user?.roles) && (!authUser || user?.id === authUser.id) ? user.roles : [];
  const isAdmin = !isLoading && isAuthenticated && roles.includes('admin');

  return {
    isAdmin,
    isLoading,
    isAuthenticated,
    roles,
  };
}

/* ───── Hook: check any role ───── */
export function useHasRole(role: string) {
  const { user, authUser, isAuthenticated, isLoading } = useAuth();

  const roles = validRoles(user?.roles) && (!authUser || user?.id === authUser.id) ? user.roles : [];
  const hasRole = !isLoading && isAuthenticated && roles.includes(role);

  return { hasRole, isLoading, isAuthenticated };
}

/* ───── Guard component: redirects non-admins to home ───── */
export function AdminGuard({
  children,
  fallback,
}: {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}) {
  const { isAdmin, isLoading, isAuthenticated } = useAdmin();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && !isLoading && !isAdmin) {
      router.replace('/');
    }
  }, [mounted, isLoading, isAdmin, router]);

  // During SSR and initial hydration, render children to avoid mismatch.
  // The middleware already handles server-side admin route protection.
  if (!mounted) {
    return <>{children}</>;
  }

  // Still loading auth state
  if (isLoading) {
    return (
      fallback ?? (
        <div className='min-h-screen flex items-center justify-center bg-gov-cream'>
          <div className='flex flex-col items-center gap-3'>
            <div className='h-8 w-8 animate-spin rounded-full border-4 border-gov-gold border-t-transparent' />
            <p className='text-gov-dark/60 text-sm'>Verifying access…</p>
          </div>
        </div>
      )
    );
  }

  // Not authenticated or not admin — redirect is happening
  if (!isAuthenticated || !isAdmin) {
    return (
      <div className='min-h-screen flex items-center justify-center bg-gov-cream'>
        <div className='bg-gov-dark rounded-2xl p-8 text-center max-w-md shadow-xl'>
          <div className='text-gov-copper text-4xl mb-3'>🔒</div>
          <h2 className='text-xl font-bold text-white mb-2'>Access Restricted</h2>
          <p className='text-gov-sage/70 text-sm'>
            {!isAuthenticated
              ? 'You must be signed in to view this page.'
              : 'This page is restricted to administrators.'}
          </p>
          <p className='text-gov-sage/50 text-xs mt-3'>Redirecting…</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

/* ───── Guard component: requires any auth (not necessarily admin) ───── */
export function AuthGuard({
  children,
  fallback,
}: {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && !isLoading && !isAuthenticated) {
      router.replace('/');
    }
  }, [mounted, isLoading, isAuthenticated, router]);

  if (!mounted) {
    return <>{children}</>;
  }

  if (isLoading) {
    return (
      fallback ?? (
        <div className='min-h-screen flex items-center justify-center bg-gov-cream'>
          <div className='h-8 w-8 animate-spin rounded-full border-4 border-gov-gold border-t-transparent' />
        </div>
      )
    );
  }

  if (!isAuthenticated) return null;

  return <>{children}</>;
}
