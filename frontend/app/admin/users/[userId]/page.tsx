/**
 * /admin/users/[userId] — single-user detail with mutation actions.
 *
 * Reads /admin/users/{id}; exposes role toggles, send-reset, and a
 * type-the-email-to-confirm delete. Self-targeting destructive
 * actions are disabled (the backend also enforces this).
 */
'use client';

import PageShell from '@/components/layout/PageShell';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useAdmin } from '@/lib/auth/admin';
import api from '@/lib/api/axios';
import {
  parseUserDetail,
  parseUserAck,
  parseRoleAck,
  userError,
  validUserId,
  type UserDetail,
} from '@/lib/admin/users';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Mail,
  Shield,
  Trash2,
  User as UserIcon,
  XCircle,
} from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { use, useState, useRef, useEffect } from 'react';

const KNOWN_ROLES = ['citizen', 'admin'];

const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function UserDetailPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = use(params);
  const { authUser } = useAuth();
  return (
    <div className='[&_h1]:[overflow-wrap:anywhere] [&_header_p]:[overflow-wrap:anywhere]'>
      <UserDetailInner key={`${authUser?.id}:${userId}`} userId={userId} />
    </div>
  );
}

function UserDetailInner({ userId }: { userId: string }) {
  const { authUser } = useAuth();
  const { isAdmin: allowed } = useAdmin();
  const actorId = authUser?.id;
  const active = useRef(true);
  useEffect(() => { active.current = allowed; return () => { active.current = false; }; }, [allowed]);
  const router = useRouter();
  const qc = useQueryClient();
  const isSelf = authUser?.id?.toLowerCase() === userId.toLowerCase();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get('returnTo');
  const backHref = returnTo && /^\/admin\/users(?:\?|$)/.test(returnTo) ? returnTo : '/admin/users';
  const mutationLock = useRef(false);
  const runMutation = (mutate: () => void) => {
    if (!allowed || !active.current || mutationLock.current) return;
    mutationLock.current = true;
    mutate();
  };

  const { data, isLoading, error, refetch } = useQuery<UserDetail>({
    queryKey: ['admin', 'user', actorId, userId],
    enabled: allowed,
    gcTime: 0,
    retry: false,
    queryFn: async ({ signal }) => {
      if (!validUserId(userId)) throw new Error('Invalid user ID.');
      return parseUserDetail((await api.get(`/admin/users/${userId}`, { signal, headers: { 'Cache-Control': 'no-store' } })).data, userId);
    },
    staleTime: 15_000,
  });

  const [pendingRoles, setPendingRoles] = useState<string[] | null>(null);
  const effectiveRoles = pendingRoles ?? data?.roles ?? [];
  const dirty =
    pendingRoles !== null && JSON.stringify(pendingRoles) !== JSON.stringify(data?.roles ?? []);

  const saveRoles = useMutation<
    UserDetail & { ok: true; audit_recorded: boolean },
    unknown,
    string[]
  >({
    mutationFn: async (roles) =>
      parseRoleAck(
        (await api.patch(`/admin/users/${userId}/roles`, { roles })).data,
        userId,
        roles
      ),
    onSettled: () => {
      mutationLock.current = false;
    },
    onSuccess: (updated) => {
      if (!active.current) return;
      qc.setQueryData(['admin', 'user', actorId, userId], updated);
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
      qc.invalidateQueries({ queryKey: ['admin', 'audit-log'] });
      qc.invalidateQueries({ queryKey: ['admin', 'user-stats'] });
      setPendingRoles(null);
    },
  });

  const sendReset = useMutation({
    mutationFn: async () =>
      parseUserAck(
        (await api.post(`/admin/users/${userId}/send-reset`, {})).data,
        data?.email ?? undefined
      ),
    onSettled: () => {
      mutationLock.current = false;
    },
    onSuccess: () => { if (active.current) qc.invalidateQueries({ queryKey: ['admin', 'audit-log'] }); },
  });

  const deleteUser = useMutation({
    mutationFn: async () => parseUserAck((await api.delete(`/admin/users/${userId}`)).data),
    onSettled: () => {
      mutationLock.current = false;
    },
    onSuccess: (result) => {
      if (!active.current) return;
      qc.invalidateQueries({ queryKey: ['admin', 'users'] });
      qc.invalidateQueries({ queryKey: ['admin', 'audit-log'] });
      qc.invalidateQueries({ queryKey: ['admin', 'user-stats'] });
      if (result.audit_recorded) router.replace(backHref);
    },
  });

  if (!allowed) return <PageShell title='Users'><p>Administrator access required.</p></PageShell>;

  const busy =
    saveRoles.isPending || sendReset.isPending || deleteUser.isPending || deleteUser.isSuccess;
  if (deleteUser.isSuccess) {
    return (
      <PageShell title='User deleted' back={{ href: backHref, label: 'Back to users' }}>
        <p role='status'>
          {deleteUser.data.audit_recorded
            ? 'User deleted.'
            : 'User deleted. The audit record could not be saved. Do not repeat the deletion.'}
        </p>
      </PageShell>
    );
  }

  if (isLoading) {
    return (
      <PageShell title='Loading user…' back={{ href: backHref, label: 'Back to users' }}>
        <div className='py-16 flex justify-center'>
          <Loader2 className='w-6 h-6 text-gov-sage animate-spin' />
        </div>
      </PageShell>
    );
  }

  if (error || !data) {
    return (
      <PageShell title='Could not load user' back={{ href: backHref, label: 'Back to users' }}>
        <div className='py-16 flex flex-col items-center gap-3'>
          <XCircle className='w-10 h-10 text-gov-copper dark:text-red-400' />
          <p className='text-gov-copper dark:text-red-400 text-sm'>
            This user could not be loaded.
          </p>
          <button
            onClick={() => { if (allowed) refetch(); }}
            className='px-4 py-2 rounded-xl border border-neutral-border'
          >
            Retry
          </button>
        </div>
      </PageShell>
    );
  }

  const isAdmin = data.roles.includes('admin');

  return (
    <PageShell
      title={data.display_name ?? data.email ?? 'Unknown user'}
      subtitle={data.email ?? 'No email on record'}
      back={{ href: backHref, label: 'Back to users' }}
    >
      <div className='space-y-6'>
        {/* ── Identity card ── */}
        <motion.section
          variants={fadeUp}
          initial='hidden'
          animate='show'
          custom={0}
          className='bg-white dark:bg-surface-base rounded-2xl p-6 border border-neutral-border shadow-surface'
        >
          <div className='flex items-start gap-4'>
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 border ${
                isAdmin ? 'bg-gov-gold/15 border-gov-gold/30' : 'bg-gov-sage/10 border-gov-sage/20'
              }`}
            >
              {isAdmin ? (
                <Shield className='w-7 h-7 text-gov-gold' />
              ) : (
                <UserIcon className='w-7 h-7 text-gov-sage' />
              )}
            </div>
            <div className='flex-1 min-w-0'>
              <p className='text-[11px] uppercase tracking-wider text-neutral-muted font-semibold'>
                User ID
              </p>
              <p className='text-xs font-mono text-neutral-text break-all mt-0.5'>{data.id}</p>
              {isSelf && (
                <span className='inline-flex items-center gap-1 mt-3 text-[11px] uppercase tracking-wider font-semibold bg-gov-gold/20 text-gov-forest dark:text-emerald-200 ring-1 ring-inset ring-gov-gold/40 px-2 py-0.5 rounded-full'>
                  This is you
                </span>
              )}
            </div>
          </div>

          <div className='grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-neutral-border'>
            <Field label='Account created' value={formatDate(data.created_at)} />
            <Field label='Last sign-in' value={formatDate(data.last_sign_in_at)} />
            <Field
              label='Email verified'
              value={data.email_confirmed ? 'Yes' : 'No'}
              tone={data.email_confirmed ? 'ok' : 'warn'}
            />
            <Field
              label='Banned until'
              value={data.banned_until ? formatDate(data.banned_until) : '—'}
              tone={data.banned_until ? 'bad' : 'muted'}
            />
          </div>
        </motion.section>

        {/* ── Roles ── */}
        <motion.section
          variants={fadeUp}
          initial='hidden'
          animate='show'
          custom={1}
          className='bg-white dark:bg-surface-base rounded-2xl p-6 border border-neutral-border shadow-surface'
        >
          <header className='flex flex-wrap gap-3 items-center justify-between mb-4'>
            <div className='flex items-center gap-2'>
              <Shield className='w-4 h-4 text-gov-sage' />
              <h2 className='font-display text-lg text-neutral-text'>Roles</h2>
            </div>
            {dirty && (
              <div className='flex items-center gap-2'>
                <button
                  disabled={busy}
                  onClick={() => {
                    setPendingRoles(null);
                    saveRoles.reset();
                  }}
                  className='text-xs text-neutral-muted hover:text-neutral-text px-2 py-1'
                >
                  Cancel
                </button>
                <button
                  onClick={() => runMutation(() => saveRoles.mutate(pendingRoles!))}
                  disabled={busy}
                  className='inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-full bg-gov-sage text-white hover:bg-gov-sage/90 disabled:opacity-50 shadow-surface'
                >
                  {saveRoles.isPending ? (
                    <Loader2 className='w-3 h-3 animate-spin' />
                  ) : (
                    <CheckCircle2 className='w-3 h-3' />
                  )}
                  Save changes
                </button>
              </div>
            )}
          </header>
          <div className='flex flex-wrap gap-2'>
            {KNOWN_ROLES.map((role) => {
              const has = effectiveRoles.includes(role);
              return (
                <button
                  key={role}
                  disabled={busy || (isSelf && role === 'admin')}
                  aria-pressed={has}
                  onClick={() => {
                    saveRoles.reset();
                    const base = pendingRoles ?? data.roles;
                    setPendingRoles(has ? base.filter((r) => r !== role) : [...base, role]);
                  }}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition-all ${
                    has
                      ? 'bg-gov-gold/20 text-gov-forest dark:text-emerald-200 ring-1 ring-inset ring-gov-gold/40 shadow-sm'
                      : 'bg-white dark:bg-surface-base text-neutral-muted ring-1 ring-inset ring-neutral-border hover:ring-gov-sage/40 hover:text-neutral-text'
                  }`}
                >
                  {has && <CheckCircle2 className='w-3 h-3' />}
                  {role}
                </button>
              );
            })}
          </div>
          {data.roles
            .filter((role) => !KNOWN_ROLES.includes(role))
            .map((role) => (
              <p key={role} className='mt-2 text-xs text-neutral-muted'>
                Existing role: {role} (preserved)
              </p>
            ))}
          {saveRoles.isSuccess && (
            <p role='status' className='mt-3 text-sm'>
              {saveRoles.data.audit_recorded
                ? 'Roles updated.'
                : 'Roles updated; the audit record could not be saved. Do not repeat this change.'}
            </p>
          )}
          {saveRoles.isError && (
            <p role='alert' className='text-xs text-gov-copper dark:text-red-400 mt-3'>
              {userError(saveRoles.error, 'Failed to update roles.')}
            </p>
          )}
        </motion.section>

        {/* ── Actions ── */}
        <motion.section
          variants={fadeUp}
          initial='hidden'
          animate='show'
          custom={2}
          className='bg-white dark:bg-surface-base rounded-2xl p-6 border border-neutral-border shadow-surface space-y-4'
        >
          <div className='flex items-center gap-2'>
            <AlertTriangle className='w-4 h-4 text-gov-warning dark:text-amber-300' />
            <h2 className='font-display text-lg text-neutral-text'>Account actions</h2>
          </div>

          <ActionRow
            icon={Mail}
            title='Send password-reset email'
            description="Triggers Supabase's recovery email so the user can set a new password themselves."
            button={
              <button
                onClick={() => runMutation(() => sendReset.mutate())}
                disabled={busy || sendReset.isSuccess || !data.email}
                className='inline-flex items-center gap-1 px-3.5 py-1.5 text-xs font-semibold rounded-full bg-white dark:bg-surface-base border border-neutral-border hover:border-gov-sage/40 text-neutral-text disabled:opacity-50 transition-all shadow-surface'
              >
                {sendReset.isPending ? <Loader2 className='w-3 h-3 animate-spin' /> : 'Send'}
              </button>
            }
            status={
              sendReset.isSuccess ? (
                <p
                  role='status'
                  className='text-xs text-emerald-700 dark:text-emerald-300 inline-flex items-center gap-1'
                >
                  <CheckCircle2 className='w-3 h-3' />
                  {sendReset.data.audit_recorded
                    ? 'Reset request accepted. Email delivery is unconfirmed.'
                    : 'Reset request accepted; the audit record could not be saved. Do not send again.'}
                </p>
              ) : sendReset.isError ? (
                <p className='text-xs text-gov-copper dark:text-red-400 inline-flex items-center gap-1'>
                  <AlertTriangle className='w-3 h-3' />
                  {userError(
                    sendReset.error,
                    'Failed to send. Refresh to verify before trying again.'
                  )}
                </p>
              ) : null
            }
          />

          <DeleteAction
            email={data.email ?? data.id}
            isSelf={isSelf}
            isPending={busy}
            isError={deleteUser.isError}
            errorMessage={userError(
              deleteUser.error,
              'Delete failed. Refresh to verify before trying again.'
            )}
            onConfirm={() => runMutation(() => deleteUser.mutate())}
          />
        </motion.section>

        {/* ── Raw metadata (collapsed) ── */}
        <motion.details
          variants={fadeUp}
          initial='hidden'
          animate='show'
          custom={3}
          className='bg-white dark:bg-surface-base rounded-2xl border border-neutral-border shadow-surface group'
        >
          <summary className='cursor-pointer px-6 py-4 text-sm font-semibold text-neutral-text flex items-center justify-between'>
            Raw Supabase metadata
            <span className='text-xs text-neutral-muted group-open:rotate-180 transition-transform'>
              ▾
            </span>
          </summary>
          <div className='px-6 pb-5 grid grid-cols-1 md:grid-cols-2 gap-4'>
            <div>
              <p className='text-[11px] uppercase tracking-wider text-neutral-muted font-semibold mb-1'>
                app_metadata
              </p>
              <pre className='text-xs font-mono bg-gov-cream dark:bg-surface-sunken border border-neutral-border rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all text-neutral-text'>
                {JSON.stringify(data.app_metadata, null, 2)}
              </pre>
            </div>
            <div>
              <p className='text-[11px] uppercase tracking-wider text-neutral-muted font-semibold mb-1'>
                user_metadata
              </p>
              <pre className='text-xs font-mono bg-gov-cream dark:bg-surface-sunken border border-neutral-border rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-all text-neutral-text'>
                {JSON.stringify(data.user_metadata, null, 2)}
              </pre>
            </div>
          </div>
        </motion.details>
      </div>
    </PageShell>
  );
}

function Field({
  label,
  value,
  tone = 'default',
}: {
  label: string;
  value: string;
  tone?: 'ok' | 'bad' | 'warn' | 'muted' | 'default';
}) {
  const colour = {
    ok: 'text-emerald-600 dark:text-emerald-400',
    bad: 'text-gov-copper dark:text-red-400',
    warn: 'text-gov-warning dark:text-amber-300',
    muted: 'text-neutral-muted',
    default: 'text-neutral-text',
  }[tone];
  return (
    <div>
      <p className='text-[11px] uppercase tracking-wider text-neutral-muted font-semibold'>
        {label}
      </p>
      <p className={`text-sm font-medium mt-0.5 ${colour}`}>{value}</p>
    </div>
  );
}

function ActionRow({
  icon: Icon,
  title,
  description,
  button,
  status,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  button: React.ReactNode;
  status?: React.ReactNode;
}) {
  return (
    <div className='flex flex-wrap items-start gap-3'>
      <div className='w-9 h-9 rounded-xl bg-gov-sage/10 border border-gov-sage/20 flex items-center justify-center shrink-0'>
        <Icon className='w-4 h-4 text-gov-sage' />
      </div>
      <div className='flex-1 min-w-0'>
        <p className='text-sm font-semibold text-neutral-text'>{title}</p>
        <p className='text-xs text-neutral-muted mt-0.5'>{description}</p>
        {status && <div className='mt-1.5'>{status}</div>}
      </div>
      <div className='shrink-0'>{button}</div>
    </div>
  );
}

function DeleteAction({
  email,
  isSelf,
  isPending,
  isError,
  errorMessage,
  onConfirm,
}: {
  email: string;
  isSelf: boolean;
  isPending: boolean;
  isError: boolean;
  errorMessage?: string;
  onConfirm: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState('');
  const canConfirm = !isSelf && typed === email && email.length > 0;

  return (
    <div className='border-t border-neutral-border pt-4'>
      <div className='flex flex-wrap items-start gap-3'>
        <div className='w-9 h-9 rounded-xl bg-gov-copper/15 border border-gov-copper/25 flex items-center justify-center shrink-0'>
          <Trash2 className='w-4 h-4 text-gov-copper dark:text-red-400' />
        </div>
        <div className='flex-1 min-w-0'>
          <p className='text-sm font-semibold text-neutral-text'>Delete user</p>
          <p className='text-xs text-neutral-muted mt-0.5'>
            Permanently removes the user from Supabase and cascades their profile row. This cannot
            be undone.
          </p>
          {isSelf && (
            <p className='text-xs text-gov-warning dark:text-amber-300 mt-1.5 inline-flex items-center gap-1'>
              <AlertTriangle className='w-3 h-3' />
              You can&apos;t delete your own account.
            </p>
          )}
          {open && !isSelf && (
            <div className='mt-3 space-y-2'>
              <p className='text-xs text-neutral-muted'>
                Type <span className='font-mono font-semibold text-neutral-text'>{email}</span> to
                confirm:
              </p>
              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                aria-label='Confirm deletion'
                disabled={isPending}
                placeholder={email}
                className='w-full max-w-sm px-3 py-2 text-sm rounded-lg border border-gov-copper/40 focus:outline-none focus:ring-2 focus:ring-gov-copper/40 bg-gov-copper/5 font-mono'
                autoFocus
              />
              <div className='flex items-center gap-2'>
                <button
                  disabled={isPending}
                  onClick={() => {
                    setOpen(false);
                    setTyped('');
                  }}
                  className='text-xs text-neutral-muted hover:text-neutral-text px-2 py-1'
                >
                  Cancel
                </button>
                <button
                  onClick={onConfirm}
                  disabled={!canConfirm || isPending}
                  className='inline-flex items-center gap-1 px-3.5 py-1.5 text-xs font-semibold rounded-full bg-gov-copper text-white hover:bg-gov-copper/90 disabled:opacity-50 disabled:cursor-not-allowed shadow-surface'
                >
                  {isPending ? (
                    <Loader2 className='w-3 h-3 animate-spin' />
                  ) : (
                    <Trash2 className='w-3 h-3' />
                  )}
                  Delete permanently
                </button>
              </div>
              {isError && (
                <p className='text-xs text-gov-copper dark:text-red-400 inline-flex items-center gap-1'>
                  <AlertTriangle className='w-3 h-3' />
                  {errorMessage || 'Delete failed.'}
                </p>
              )}
            </div>
          )}
        </div>
        {!open && !isSelf && (
          <button
            disabled={isPending}
            onClick={() => setOpen(true)}
            className='shrink-0 inline-flex items-center gap-1 px-3.5 py-1.5 text-xs font-semibold rounded-full border border-gov-copper/40 text-gov-copper dark:text-red-400 hover:bg-gov-copper/5 transition-all'
          >
            <Trash2 className='w-3 h-3' />
            Delete…
          </button>
        )}
      </div>
    </div>
  );
}

function formatDate(iso: string | null): string {
  if (!iso) return 'never';
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
