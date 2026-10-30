/**
 * /admin – shared shell for the admin section.
 *
 * Wraps every admin route in <AdminGuard> (third defence layer behind
 * Next.js middleware and backend ``require_admin``) and renders a
 * task navigation and compact private-page headers. Public pages keep
 * their own shell; authorization and actor-scoped cache eviction are shared.
 */
'use client';

import { AdminGuard, useAdmin } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import AdminNav from '@/components/admin/AdminNav';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAdmin();
  const { user } = useAuth();
  const actorId = user?.id ?? null;
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!isAdmin || !actorId) {
      void queryClient.cancelQueries({ queryKey: ['admin'] });
      queryClient.removeQueries({ queryKey: ['admin'] });
    }
    return () => {
      // Other admin lanes use the same actor position. Do not cancel a newly
      // mounted next actor while removing the departing actor's private data.
      const previousActor = { queryKey: ['admin'], predicate: (query: { queryKey: readonly unknown[] }) => query.queryKey[2] === actorId };
      void queryClient.cancelQueries(previousActor);
      queryClient.removeQueries(previousActor);
    };
  }, [actorId, isAdmin, queryClient]);
  return (
    <AdminGuard>
      <AdminNav />
      {children}
    </AdminGuard>
  );
}
