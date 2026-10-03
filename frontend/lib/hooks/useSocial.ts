'use client';

import { useAdmin } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';
import { EditorialState, sendSocialCommand, SocialApiError, SocialPost, socialApi, SocialSummary } from '@/lib/api/social';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

export const socialKeys = {
  root: (actor: string | undefined) => ['admin', 'social', actor] as const,
  lists: (actor: string | undefined) => [...socialKeys.root(actor), 'posts'] as const,
  list: (actor: string | undefined, page: number, state?: EditorialState) => [...socialKeys.lists(actor), { page, editorial_state: state }] as const,
  detail: (actor: string | undefined, id: string) => [...socialKeys.root(actor), 'post', id] as const,
  status: (actor: string | undefined, id: string) => [...socialKeys.root(actor), 'status', id] as const,
};
function useSocialAccess() {
  const { isAdmin } = useAdmin();
  const { user } = useAuth();
  return { enabled: isAdmin, actor: user?.id };
}
export function useSocialPosts(page: number, state?: EditorialState, active = true) {
  const { enabled, actor } = useSocialAccess();
  return useQuery({ queryKey: socialKeys.list(actor, page, state), queryFn: ({ signal }) => socialApi.posts(page, state, signal), enabled: enabled && active, staleTime: 30_000, gcTime: 60_000, retry: false, refetchOnWindowFocus: false });
}
export function hasActiveDelivery(post: SocialSummary | undefined) {
  return !!post?.targets.some(t => ['queued', 'claimed', 'dispatching', 'processing', 'retry_wait', 'reconciling'].includes(t.state));
}
export function useSocialPost(id: string | undefined) {
  const { enabled, actor } = useSocialAccess();
  return useQuery({
    queryKey: socialKeys.detail(actor, id ?? ''), queryFn: ({ signal }) => socialApi.post(id!, signal),
    enabled: enabled && !!id, staleTime: 60_000, gcTime: 60_000, retry: false,
    refetchOnWindowFocus: false,
  });
}
export function useSocialDeliveryStatus(post: SocialPost | undefined) {
  const { enabled, actor } = useSocialAccess();
  const qc = useQueryClient();
  const requestedVersion = useRef<{ id: string; version: number } | undefined>(undefined);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== 'hidden');
    update(); document.addEventListener('visibilitychange', update);
    return () => document.removeEventListener('visibilitychange', update);
  }, []);
  const status = useQuery({
    queryKey: socialKeys.status(actor, post?.id ?? ''), queryFn: ({ signal }) => socialApi.postStatus(post!.id, signal),
    enabled: enabled && visible && hasActiveDelivery(post), staleTime: 15_000, gcTime: 60_000, retry: false,
    refetchOnWindowFocus: false, refetchIntervalInBackground: false,
    refetchInterval: query => {
      const compact = query.state.data;
      if (!visible || query.state.error || !post) return false;
      if (compact?.version === post.version && compact.revision_id !== post.revision_id) return false;
      return hasActiveDelivery(!compact || compact.version < post.version ? post : compact) ? 15_000 : false;
    },
  });
  useEffect(() => {
    const compact = status.data;
    if (!compact || !post || compact.id !== post.id) return;
    const key = socialKeys.detail(actor, compact.id);
    const detail = qc.getQueryData<SocialPost>(key);
    if (!detail) return;
    if (compact.version === detail.version && compact.revision_id === detail.revision_id) {
      // Only delivery fields change. Never replace a document/revision with a summary.
      qc.setQueryData(key, { ...detail, targets: compact.targets, delivery_status: compact.delivery_status, updated_at: compact.updated_at });
    } else if (compact.version > detail.version && (requestedVersion.current?.id !== compact.id || requestedVersion.current.version !== compact.version)) {
      requestedVersion.current = { id: compact.id, version: compact.version };
      void qc.invalidateQueries({ queryKey: key, exact: true });
    }
  }, [status.data, post?.id, actor, qc]);
  const inconsistent = status.data && post && status.data.version === post.version && status.data.revision_id !== post.revision_id;
  return { ...status, error: inconsistent ? new SocialApiError('INVALID_RESPONSE', 'Delivery status refers to a different revision at the same version. The current document and results were preserved; refresh the full revision.') : status.error };
}
export function useSocialAccounts() {
  const { enabled, actor } = useSocialAccess();
  return useQuery({ queryKey: [...socialKeys.root(actor), 'accounts'], queryFn: ({ signal }) => socialApi.accounts(signal), enabled, staleTime: 60_000, gcTime: 60_000, retry: false, refetchOnWindowFocus: false });
}
export function useSocialSystem() {
  const { enabled, actor } = useSocialAccess();
  return useQuery({ queryKey: [...socialKeys.root(actor), 'system'], queryFn: ({ signal }) => socialApi.status(signal), enabled, staleTime: 30_000, gcTime: 60_000, retry: false, refetchOnWindowFocus: false });
}
interface Command {
  path: string; body: object; method: 'post' | 'patch'; key: string;
  decode: (value: unknown) => unknown; postId?: string; actor?: string;
}
/** A rejected/ambiguous command keeps its key and exact body for explicit retries. */
export function useSocialMutation() {
  const { enabled, actor } = useSocialAccess();
  const qc = useQueryClient();
  const receipts = useRef(new Map<string, string>());
  const mutation = useMutation<unknown, SocialApiError, Command>({
    retry: false,
    mutationFn: c => {
      if (!enabled) throw new SocialApiError('ACCESS_DENIED', 'An authenticated admin session is required.');
      return sendSocialCommand(c.path, c.body, c.key, c.decode, c.method);
    },
    onSuccess: async (result, c) => {
      // Keep returned detail current without marking asynchronous publication successful.
      if (result && typeof result === 'object' && 'document' in result && 'id' in result) {
        const post = result as SocialPost;
        qc.setQueryData(socialKeys.detail(c.actor, post.id), post);
      } else if (c.postId) {
        await qc.invalidateQueries({ queryKey: socialKeys.detail(c.actor, c.postId), exact: true });
      }
      if (c.postId) await qc.invalidateQueries({ queryKey: socialKeys.status(c.actor, c.postId), exact: true });
      if (c.path !== '/controls') await qc.invalidateQueries({ queryKey: socialKeys.lists(c.actor) });
      if (c.path === '/controls' || /\/(publish|schedule|cancel|retry)$/.test(c.path)) {
        await qc.invalidateQueries({ queryKey: [...socialKeys.root(c.actor), 'system'], exact: true });
      }
    },
  });
  async function run<T>(path: string, body: object, decode: (value: unknown) => T, options: { method?: 'post' | 'patch'; postId?: string } = {}): Promise<T> {
    const method = options.method ?? 'post';
    const identity = JSON.stringify([actor, method, path, body]);
    let key = receipts.current.get(identity);
    if (!key) { key = crypto.randomUUID(); receipts.current.set(identity, key); }
    const result = await mutation.mutateAsync({ path, body, decode, method, key, postId: options.postId, actor }) as T;
    // Success confirms this intent. A later intentional duplicate/retry is a new
    // command; ambiguous transport or decoder failures keep the original key.
    receipts.current.delete(identity);
    return result;
  }
  return { ...mutation, run };
}
