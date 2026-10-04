'use client';
import { useAdmin } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';
import { connectionApi } from '@/lib/api/socialConnections';
import { useQuery } from '@tanstack/react-query';

export function useMetaConnectionStatus() {
  const { isAdmin } = useAdmin(), { user } = useAuth();
  return useQuery({ queryKey: ['admin','social',user?.id,'meta-connection-status'], queryFn: ({ signal }) => connectionApi.status(signal), enabled: isAdmin, retry: false, staleTime: 60_000, refetchOnWindowFocus: false });
}
export function useMetaAccountHealth(accountId: string, active = true) {
  const { isAdmin } = useAdmin(), { user } = useAuth();
  return useQuery({ queryKey: ['admin','social',user?.id,'account-health',accountId], queryFn: ({ signal }) => connectionApi.health(accountId, signal), enabled: isAdmin && active, retry: false, staleTime: 60_000, refetchOnWindowFocus: false });
}
