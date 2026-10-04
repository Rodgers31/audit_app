'use client';
import { useAdmin } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';
import { socialMediaApi } from '@/lib/api/socialMedia';
import { useQuery } from '@tanstack/react-query';

export function useMediaAccess() { const { isAdmin } = useAdmin(); const { user } = useAuth(); return { actor: user?.id, enabled: isAdmin && !!user?.id }; }
export const mediaKeys = { root: (actor?: string) => ['admin', 'social-media', actor] as const };
export function useMediaCapabilities() {
  const { actor, enabled } = useMediaAccess();
  return useQuery({ queryKey: [...mediaKeys.root(actor), 'capabilities'], queryFn: ({ signal }) => socialMediaApi.capabilities(signal), enabled, retry: false, staleTime: 60000, gcTime: 60000, refetchOnWindowFocus: false });
}
export function useMediaLibrary(page: number, q: string, kind: '' | 'image' | 'video', active: boolean) {
  const { actor, enabled } = useMediaAccess();
  return useQuery({ queryKey: [...mediaKeys.root(actor), 'library', { page, q, kind }], queryFn: ({ signal }) => socialMediaApi.library(page, q, kind, signal), enabled: enabled && active, retry: false, staleTime: 30000, gcTime: 60000, refetchOnWindowFocus: false });
}
export function useMediaPreview(id: string, active: boolean) {
  const { actor, enabled } = useMediaAccess();
  return useQuery({ queryKey: [...mediaKeys.root(actor), 'preview', id], queryFn: ({ signal }) => socialMediaApi.preview(id, signal), enabled: enabled && active, retry: false, staleTime: 0, gcTime: 0, refetchOnWindowFocus: false });
}
