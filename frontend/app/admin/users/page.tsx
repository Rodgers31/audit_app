/**
 * /admin/users — list + search users.
 *
 * Reads /admin/users (server-side combines Supabase auth.users with
 * the profiles table). Search is a substring match on email; the
 * input syncs to the URL ``?q=`` so the page is shareable.
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  ArrowLeft,
  ArrowRight,
  ChevronRight,
  Loader2,
  Pause,
  RefreshCcw,
  Search,
  Shield,
  User,
  XCircle,
} from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useState } from 'react';

interface UserSummary {
  id: string;
  email: string | null;
  display_name: string | null;
  roles: string[];
  created_at: string | null;
  last_sign_in_at: string | null;
  email_confirmed: boolean;
  banned_until: string | null;
}

interface UserList {
  users: UserSummary[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

const PAGE_SIZE = 20;

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay: i * 0.04, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function UsersListPage() {
  return (
    <Suspense
      fallback={
        <PageShell title='Users' subtitle='Loading…'>
          <div className='py-16 flex justify-center'>
            <Loader2 className='w-6 h-6 text-gov-sage animate-spin' />
          </div>
        </PageShell>
      }>
      <UsersListInner />
    </Suspense>
  );
}

function UsersListInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const q = searchParams.get('q') ?? '';
  const page = Number(searchParams.get('page') ?? '1');

  const [searchInput, setSearchInput] = useState(q);
  useEffect(() => {
    const t = setTimeout(() => {
      if (searchInput !== q) {
        const next = new URLSearchParams(searchParams);
        if (searchInput) next.set('q', searchInput);
        else next.delete('q');
        next.delete('page');
        router.replace(`/admin/users${next.size ? '?' + next.toString() : ''}`);
      }
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  const setPage = useCallback(
    (p: number) => {
      const next = new URLSearchParams(searchParams);
      next.set('page', String(p));
      router.replace(`/admin/users?${next.toString()}`);
    },
    [router, searchParams]
  );

  const { data, isLoading, error, refetch, isFetching } = useQuery<UserList>({
    queryKey: ['admin', 'users', { q, page }],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, page_size: PAGE_SIZE };
      if (q) params.q = q;
      return (await api.get('/admin/users', { params })).data;
    },
    staleTime: 15_000,
  });

  return (
    <PageShell
      title='Users'
      subtitle='Manage roles, send password resets, and remove accounts.'
      back={{ href: '/admin', label: 'Back to overview' }}>
      <div className='space-y-5'>
        {/* Search + refresh */}
        <div className='flex flex-wrap items-center gap-3'>
          <div className='relative flex-1 min-w-[16rem]'>
            <Search className='absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-muted/60' />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder='Search by email…'
              className='w-full pl-10 pr-3 py-2.5 text-sm rounded-xl border border-neutral-border bg-white dark:bg-surface-base focus:outline-none focus:ring-2 focus:ring-gov-sage/40 focus:border-gov-sage/40 transition-all shadow-surface'
            />
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className='inline-flex items-center gap-2 px-3.5 py-2.5 bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text rounded-xl text-sm transition-all shadow-surface disabled:opacity-50'>
            <RefreshCcw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        <p className='text-xs text-neutral-muted -mt-2'>
          {data
            ? `${data.users.length} on this page · ~${data.total.toLocaleString()} total matching`
            : ''}
        </p>

        {isLoading ? (
          <BodyState>
            <Loader2 className='w-6 h-6 text-gov-sage animate-spin' />
            <p className='text-neutral-muted text-sm'>Loading users…</p>
          </BodyState>
        ) : error ? (
          <BodyState>
            <XCircle className='w-8 h-8 text-gov-copper dark:text-red-400' />
            <p className='text-gov-copper dark:text-red-400 text-sm'>Could not load users.</p>
          </BodyState>
        ) : !data || data.users.length === 0 ? (
          <BodyState>
            <Pause className='w-8 h-8 text-neutral-muted/40' />
            <p className='text-neutral-muted text-sm'>No users match.</p>
          </BodyState>
        ) : (
          <>
            <ul className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl divide-y divide-neutral-border/60 shadow-surface overflow-hidden'>
              {data.users.map((u, i) => (
                <motion.li
                  key={u.id}
                  variants={fadeUp}
                  initial='hidden'
                  animate='show'
                  custom={i}>
                  <Link
                    href={`/admin/users/${u.id}`}
                    className='flex items-center gap-4 px-5 py-4 hover:bg-gov-cream/60 dark:hover:bg-surface-elevated transition-colors group'>
                    <div
                      className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 border ${
                        u.roles.includes('admin')
                          ? 'bg-gov-gold/15 border-gov-gold/30'
                          : 'bg-gov-sage/10 border-gov-sage/20'
                      }`}>
                      {u.roles.includes('admin') ? (
                        <Shield className='w-5 h-5 text-gov-gold' />
                      ) : (
                        <User className='w-5 h-5 text-gov-sage' />
                      )}
                    </div>
                    <div className='flex-1 min-w-0'>
                      <div className='flex items-center gap-2 flex-wrap'>
                        <span className='font-semibold text-neutral-text text-sm truncate'>
                          {u.display_name ?? u.email ?? u.id.slice(0, 8) + '…'}
                        </span>
                        {u.roles.map((role) => (
                          <RolePill key={role} role={role} />
                        ))}
                        {u.banned_until && (
                          <span className='inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] uppercase tracking-wider font-semibold bg-gov-copper/15 text-gov-copper dark:text-red-400 border border-gov-copper/20'>
                            banned
                          </span>
                        )}
                      </div>
                      <p className='text-xs text-neutral-muted truncate mt-0.5'>
                        {u.email ?? '—'}
                      </p>
                    </div>
                    <div className='hidden sm:block text-right text-xs text-neutral-muted'>
                      <p>Created {formatShort(u.created_at)}</p>
                      <p className='mt-0.5'>Last sign-in {formatShort(u.last_sign_in_at)}</p>
                    </div>
                    <ChevronRight className='w-4 h-4 text-neutral-muted/40 shrink-0 group-hover:text-gov-sage group-hover:translate-x-0.5 transition-all' />
                  </Link>
                </motion.li>
              ))}
            </ul>

            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data.total}
              hasMore={data.has_more}
              onChange={setPage}
            />
          </>
        )}
      </div>
    </PageShell>
  );
}

function RolePill({ role }: { role: string }) {
  const isAdmin = role === 'admin';
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider font-semibold ${
        isAdmin
          ? 'bg-gov-gold/20 text-gov-forest dark:text-emerald-200 ring-1 ring-inset ring-gov-gold/40'
          : 'bg-gov-cream dark:bg-surface-sunken text-neutral-muted ring-1 ring-inset ring-neutral-border'
      }`}>
      {role}
    </span>
  );
}

function Pagination({
  page,
  pageSize,
  total,
  hasMore,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  hasMore: boolean;
  onChange: (page: number) => void;
}) {
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return (
    <div className='flex items-center justify-between text-sm flex-wrap gap-3 pt-2'>
      <span className='text-neutral-muted'>
        Showing <span className='font-medium text-neutral-text'>{start.toLocaleString()}</span>–
        <span className='font-medium text-neutral-text'>{end.toLocaleString()}</span> of{' '}
        <span className='font-medium text-neutral-text'>~{total.toLocaleString()}</span>
      </span>
      <div className='flex items-center gap-2'>
        <button
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className='inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text disabled:opacity-40 transition-all shadow-surface'>
          <ArrowLeft className='w-3.5 h-3.5' />
          Prev
        </button>
        <span className='text-neutral-muted text-xs'>Page {page}</span>
        <button
          onClick={() => onChange(page + 1)}
          disabled={!hasMore}
          className='inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text disabled:opacity-40 transition-all shadow-surface'>
          Next
          <ArrowRight className='w-3.5 h-3.5' />
        </button>
      </div>
    </div>
  );
}

function BodyState({ children }: { children: React.ReactNode }) {
  return (
    <div className='bg-white dark:bg-surface-base border border-neutral-border rounded-2xl py-16 flex flex-col items-center justify-center gap-3 shadow-surface'>
      {children}
    </div>
  );
}

function formatShort(iso: string | null): string {
  if (!iso) return 'never';
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}
