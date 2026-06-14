'use client';

import {
  getAlerts,
  markAlertRead,
  markAllAlertsRead,
  updateProfile,
  type DataAlert,
} from '@/lib/api/auth';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useWatchlist } from '@/lib/auth/WatchlistProvider';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle,
  Bell,
  BellOff,
  Bookmark,
  CheckCheck,
  ExternalLink,
  KeyRound,
  Loader2,
  LogOut,
  Mail,
  MapPin,
  Settings,
  ShieldCheck,
  Trash2,
  User,
  UserX,
} from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

type Tab = 'profile' | 'watchlist' | 'alerts';

export default function AccountDashboard() {
  const { user, refreshUser, resetPassword, changeEmail, deleteAccount, logout } = useAuth();
  const { items: watchlist, isLoading: watchlistLoading, remove: removeWatch } = useWatchlist();
  const searchParams = useSearchParams();
  const router = useRouter();
  const initialTab = (searchParams.get('tab') as Tab) || 'profile';
  const [activeTab, setActiveTab] = useState<Tab>(initialTab);

  // Profile state
  const [displayName, setDisplayName] = useState(user?.display_name || '');
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  // Change email state
  const [newEmail, setNewEmail] = useState('');
  const [emailSending, setEmailSending] = useState(false);
  const [emailMsg, setEmailMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(
    null
  );

  // Reset password state
  const [resetSending, setResetSending] = useState(false);
  const [resetMsg, setResetMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(
    null
  );

  // Delete account state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteTyped, setDeleteTyped] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [showFarewell, setShowFarewell] = useState(false);

  // Alerts state
  const [alerts, setAlerts] = useState<DataAlert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);

  // Load alerts when tab changes
  useEffect(() => {
    if (activeTab === 'alerts') {
      setAlertsLoading(true);
      getAlerts()
        .then(setAlerts)
        .catch(() => {})
        .finally(() => setAlertsLoading(false));
    }
  }, [activeTab]);

  // Save profile
  const handleSaveProfile = useCallback(async () => {
    setSaving(true);
    setSaveMsg('');
    try {
      await updateProfile(displayName);
      await refreshUser();
      setSaveMsg('Saved!');
      setTimeout(() => setSaveMsg(''), 3000);
    } catch {
      setSaveMsg('Failed to save');
    } finally {
      setSaving(false);
    }
  }, [displayName, refreshUser]);

  // Change email
  const handleChangeEmail = useCallback(async () => {
    if (!newEmail || newEmail === user?.email) return;
    setEmailSending(true);
    setEmailMsg(null);
    try {
      await changeEmail(newEmail);
      setEmailMsg({
        type: 'success',
        text: `Confirmation link sent to ${newEmail}. Click it to complete the change.`,
      });
      setNewEmail('');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update email';
      setEmailMsg({ type: 'error', text: msg });
    } finally {
      setEmailSending(false);
    }
  }, [newEmail, user?.email, changeEmail]);

  // Reset password (sends link to current email)
  const handleResetPassword = useCallback(async () => {
    if (!user?.email) return;
    setResetSending(true);
    setResetMsg(null);
    try {
      await resetPassword(user.email);
      setResetMsg({
        type: 'success',
        text: `Password reset link sent to ${user.email}. Check your inbox.`,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to send reset email';
      setResetMsg({ type: 'error', text: msg });
    } finally {
      setResetSending(false);
    }
  }, [user?.email, resetPassword]);

  // Delete account
  const handleDeleteAccount = useCallback(async () => {
    setDeleting(true);
    try {
      await deleteAccount();
      setShowDeleteConfirm(false);
      setShowFarewell(true);
      // Show farewell for 4 seconds, then sign out and redirect
      setTimeout(async () => {
        await logout();
        router.push('/');
      }, 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete account';
      alert(msg);
      setDeleting(false);
    }
  }, [deleteAccount, logout, router]);

  // Remove watchlist item (via context)
  const handleRemoveWatch = useCallback(
    async (id: number) => {
      try {
        await removeWatch(id);
      } catch {}
    },
    [removeWatch]
  );

  // Mark alert read
  const handleMarkRead = useCallback(async (id: number) => {
    try {
      await markAlertRead(id);
      setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, read: true } : a)));
    } catch {}
  }, []);

  // Mark all alerts read
  const handleMarkAllRead = useCallback(async () => {
    try {
      await markAllAlertsRead();
      setAlerts((prev) => prev.map((a) => ({ ...a, read: true })));
    } catch {}
  }, []);

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'profile', label: 'Profile', icon: <User className='w-4 h-4' /> },
    { id: 'watchlist', label: 'Watchlist', icon: <Bookmark className='w-4 h-4' /> },
    { id: 'alerts', label: 'Alerts', icon: <Bell className='w-4 h-4' /> },
  ];

  const unreadCount = alerts.filter((a) => !a.read).length;

  return (
    <div className='max-w-4xl mx-auto px-4 py-8'>
      {/* Tab bar */}
      <div className='flex gap-1 bg-white/60 dark:bg-surface-elevated backdrop-blur-md border border-gov-sage/20 p-1 rounded-2xl mb-8 shadow-sm'>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 flex-1 justify-center py-3 px-4 rounded-xl text-sm font-semibold transition-all relative ${
              activeTab === tab.id
                ? 'bg-gov-forest text-white shadow-md'
                : 'text-gov-forest/70 dark:text-emerald-100/70 hover:bg-gov-sage/10'
            }`}>
            {tab.icon}
            {tab.label}
            {tab.id === 'alerts' && unreadCount > 0 && (
              <span className='absolute -top-1 -right-1 w-5 h-5 bg-gov-copper text-white text-[10px] font-bold rounded-full flex items-center justify-center'>
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <AnimatePresence mode='wait'>
        {/* ──── Profile ──── */}
        {activeTab === 'profile' && (
          <motion.div
            key='profile'
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className='space-y-6'>
            {/* ── Identity card ── */}
            <div className='bg-white/80 dark:bg-surface-elevated backdrop-blur-md border border-gov-sage/15 rounded-2xl p-6 shadow-sm'>
              <div className='flex items-center gap-4 mb-8'>
                <div className='w-16 h-16 rounded-2xl bg-gradient-to-br from-gov-sage to-gov-forest flex items-center justify-center text-white text-2xl font-bold shadow-lg'>
                  {(user?.display_name || user?.email || 'C')[0].toUpperCase()}
                </div>
                <div>
                  <h2 className='text-xl font-bold text-gov-dark dark:text-white'>
                    {user?.display_name || 'Citizen'}
                  </h2>
                  <p className='text-gov-forest/60 dark:text-emerald-100/60 text-sm'>{user?.email}</p>
                </div>
              </div>

              <div className='space-y-5'>
                <div>
                  <label className='block text-xs font-semibold uppercase tracking-wider text-gov-forest/50 dark:text-emerald-100/50 mb-1.5'>
                    Display Name
                  </label>
                  <input
                    type='text'
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    className='w-full px-4 py-3 rounded-xl bg-gov-sand/60 border border-gov-sage/20 text-gov-dark dark:text-white placeholder:text-gov-forest/30 dark:text-emerald-100/30 focus:outline-none focus:ring-2 focus:ring-gov-sage/40 transition-all'
                    placeholder='Your display name'
                  />
                </div>

                <div className='flex items-center gap-3'>
                  <button
                    onClick={handleSaveProfile}
                    disabled={saving}
                    className='flex items-center gap-2 px-6 py-3 rounded-xl bg-gov-sage text-white font-semibold hover:bg-gov-sage/90 active:scale-[0.98] transition-all disabled:opacity-60 shadow-md'>
                    {saving ? (
                      <Loader2 className='w-4 h-4 animate-spin' />
                    ) : (
                      <Settings className='w-4 h-4' />
                    )}
                    Save Changes
                  </button>
                  {saveMsg && (
                    <span
                      className={`text-sm font-medium ${
                        saveMsg === 'Saved!' ? 'text-green-600' : 'text-gov-copper'
                      }`}>
                      {saveMsg}
                    </span>
                  )}
                </div>
              </div>

              {/* Role badges */}
              <div className='mt-8 pt-6 border-t border-gov-sage/10'>
                <p className='text-xs font-semibold uppercase tracking-wider text-gov-forest/40 dark:text-emerald-100/40 mb-2'>
                  Roles
                </p>
                <div className='flex flex-wrap gap-2'>
                  {user?.roles.map((role) => (
                    <span
                      key={role}
                      className='px-3 py-1 bg-gov-sage/15 text-gov-forest dark:text-emerald-100 text-xs font-semibold rounded-full border border-gov-sage/20'>
                      {role}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* ── Change Email ── */}
            <div className='bg-white/80 dark:bg-surface-elevated backdrop-blur-md border border-gov-sage/15 rounded-2xl p-6 shadow-sm'>
              <div className='flex items-center gap-2 mb-4'>
                <Mail className='w-5 h-5 text-gov-sage' />
                <h3 className='font-bold text-gov-dark dark:text-white'>Change Email</h3>
              </div>
              <p className='text-sm text-gov-forest/60 dark:text-emerald-100/60 mb-4'>
                A confirmation link will be sent to the new email address. Your email won&apos;t
                change until you click that link.
              </p>
              <div className='flex flex-col sm:flex-row gap-3'>
                <input
                  type='email'
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder='new-email@example.com'
                  className='flex-1 px-4 py-3 rounded-xl bg-gov-sand/60 border border-gov-sage/20 text-gov-dark dark:text-white placeholder:text-gov-forest/30 dark:text-emerald-100/30 focus:outline-none focus:ring-2 focus:ring-gov-sage/40 transition-all'
                />
                <button
                  onClick={handleChangeEmail}
                  disabled={emailSending || !newEmail || newEmail === user?.email}
                  className='flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gov-sage text-white font-semibold hover:bg-gov-sage/90 active:scale-[0.98] transition-all disabled:opacity-60 shadow-md whitespace-nowrap'>
                  {emailSending ? (
                    <Loader2 className='w-4 h-4 animate-spin' />
                  ) : (
                    <Mail className='w-4 h-4' />
                  )}
                  Send Link
                </button>
              </div>
              {emailMsg && (
                <div
                  className={`mt-3 flex items-start gap-2 text-sm rounded-xl px-4 py-3 ${
                    emailMsg.type === 'success'
                      ? 'bg-green-50 text-green-700 border border-green-200'
                      : 'bg-red-50 text-gov-copper border border-red-200'
                  }`}>
                  {emailMsg.type === 'success' ? (
                    <ShieldCheck className='w-4 h-4 mt-0.5 shrink-0' />
                  ) : (
                    <AlertTriangle className='w-4 h-4 mt-0.5 shrink-0' />
                  )}
                  {emailMsg.text}
                </div>
              )}
            </div>

            {/* ── Reset Password ── */}
            <div className='bg-white/80 dark:bg-surface-elevated backdrop-blur-md border border-gov-sage/15 rounded-2xl p-6 shadow-sm'>
              <div className='flex items-center gap-2 mb-4'>
                <KeyRound className='w-5 h-5 text-gov-sage' />
                <h3 className='font-bold text-gov-dark dark:text-white'>Reset Password</h3>
              </div>
              <p className='text-sm text-gov-forest/60 dark:text-emerald-100/60 mb-4'>
                We&apos;ll send a secure reset link to{' '}
                <span className='font-medium text-gov-dark dark:text-white'>{user?.email}</span>. Follow the link to
                set a new password.
              </p>
              <button
                onClick={handleResetPassword}
                disabled={resetSending}
                className='flex items-center gap-2 px-6 py-3 rounded-xl bg-gov-forest text-white font-semibold hover:bg-gov-forest/90 active:scale-[0.98] transition-all disabled:opacity-60 shadow-md'>
                {resetSending ? (
                  <Loader2 className='w-4 h-4 animate-spin' />
                ) : (
                  <KeyRound className='w-4 h-4' />
                )}
                Send Reset Link
              </button>
              {resetMsg && (
                <div
                  className={`mt-3 flex items-start gap-2 text-sm rounded-xl px-4 py-3 ${
                    resetMsg.type === 'success'
                      ? 'bg-green-50 text-green-700 border border-green-200'
                      : 'bg-red-50 text-gov-copper border border-red-200'
                  }`}>
                  {resetMsg.type === 'success' ? (
                    <ShieldCheck className='w-4 h-4 mt-0.5 shrink-0' />
                  ) : (
                    <AlertTriangle className='w-4 h-4 mt-0.5 shrink-0' />
                  )}
                  {resetMsg.text}
                </div>
              )}
            </div>

            {/* ── Danger Zone: Delete Account ── */}
            <div className='bg-white/80 dark:bg-surface-elevated backdrop-blur-md border border-gov-copper/20 rounded-2xl p-6 shadow-sm'>
              <div className='flex items-center gap-2 mb-4'>
                <UserX className='w-5 h-5 text-gov-copper' />
                <h3 className='font-bold text-gov-copper'>Delete Account</h3>
              </div>
              <p className='text-sm text-gov-forest/60 dark:text-emerald-100/60 mb-4'>
                Permanently delete your account and all associated data including your watchlist,
                alerts, and preferences. This action{' '}
                <span className='font-semibold text-gov-copper'>cannot be undone</span>.
              </p>
              {!showDeleteConfirm ? (
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className='flex items-center gap-2 px-6 py-3 rounded-xl border-2 border-gov-copper/30 text-gov-copper font-semibold hover:bg-gov-copper/5 active:scale-[0.98] transition-all'>
                  <Trash2 className='w-4 h-4' />
                  Delete My Account
                </button>
              ) : (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  className='bg-red-50 border border-red-200 rounded-xl p-5 space-y-4'>
                  <div className='flex items-start gap-3'>
                    <AlertTriangle className='w-5 h-5 text-gov-copper mt-0.5 shrink-0' />
                    <div>
                      <p className='font-semibold text-gov-dark dark:text-white text-sm'>
                        Are you absolutely sure?
                      </p>
                      <p className='text-xs text-gov-forest/60 dark:text-emerald-100/60 mt-1'>
                        Type <span className='font-mono font-bold text-gov-copper'>DELETE</span>{' '}
                        below to confirm you want to permanently remove your account.
                      </p>
                    </div>
                  </div>
                  <input
                    type='text'
                    value={deleteTyped}
                    onChange={(e) => setDeleteTyped(e.target.value)}
                    placeholder='Type DELETE to confirm'
                    className='w-full px-4 py-3 rounded-xl bg-white dark:bg-surface-base border border-red-300 text-gov-dark dark:text-white placeholder:text-gov-forest/30 dark:text-emerald-100/30 focus:outline-none focus:ring-2 focus:ring-gov-copper/40 transition-all font-mono'
                  />
                  <div className='flex gap-3'>
                    <button
                      onClick={handleDeleteAccount}
                      disabled={deleteTyped !== 'DELETE' || deleting}
                      className='flex items-center gap-2 px-6 py-3 rounded-xl bg-gov-copper text-white font-semibold hover:bg-gov-copper/90 active:scale-[0.98] transition-all disabled:opacity-40 shadow-md'>
                      {deleting ? (
                        <Loader2 className='w-4 h-4 animate-spin' />
                      ) : (
                        <Trash2 className='w-4 h-4' />
                      )}
                      {deleting ? 'Deleting…' : 'Permanently Delete'}
                    </button>
                    <button
                      onClick={() => {
                        setShowDeleteConfirm(false);
                        setDeleteTyped('');
                      }}
                      className='px-6 py-3 rounded-xl border border-gov-sage/20 text-gov-forest/70 dark:text-emerald-100/70 font-semibold hover:bg-gov-sage/5 transition-all'>
                      Cancel
                    </button>
                  </div>
                </motion.div>
              )}
            </div>
          </motion.div>
        )}

        {/* ──── Watchlist ──── */}
        {activeTab === 'watchlist' && (
          <motion.div
            key='watchlist'
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}>
            {watchlistLoading ? (
              <div className='flex justify-center py-20'>
                <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
              </div>
            ) : watchlist.length === 0 ? (
              <div className='text-center py-20 bg-white/60 dark:bg-surface-elevated backdrop-blur-md rounded-2xl border border-gov-sage/15'>
                <Bookmark className='w-12 h-12 mx-auto text-gov-sage/30 mb-4' />
                <h3 className='text-lg font-bold text-gov-dark dark:text-white mb-2'>No items yet</h3>
                <p className='text-gov-forest/50 dark:text-emerald-100/50 text-sm max-w-md mx-auto'>
                  Browse County Explorer or Budget & Spending and tap the{' '}
                  <Bookmark className='inline w-4 h-4 align-text-bottom' /> button to start tracking
                  items.
                </p>
              </div>
            ) : (
              <div className='space-y-3'>
                {watchlist.map((item) => (
                  <motion.div
                    key={item.id}
                    layout
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: -40 }}
                    className='flex items-center justify-between p-4 bg-white/80 dark:bg-surface-elevated backdrop-blur-md border border-gov-sage/15 rounded-xl shadow-sm hover:shadow-md transition-shadow'>
                    <Link
                      href={item.item_type === 'county' ? `/counties/${item.item_id}` : '/budget'}
                      className='flex items-center gap-3 flex-1 min-w-0'>
                      <div
                        className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                          item.item_type === 'county'
                            ? 'bg-gov-sage/15 text-gov-sage'
                            : 'bg-gov-gold/15 text-gov-gold'
                        }`}>
                        <MapPin className='w-5 h-5' />
                      </div>
                      <div className='min-w-0'>
                        <p className='font-semibold text-gov-dark dark:text-white text-sm flex items-center gap-1.5'>
                          <span className='truncate'>{item.label}</span>
                          <ExternalLink className='w-3 h-3 text-gov-sage/40 shrink-0' />
                        </p>
                        <p className='text-xs text-gov-forest/50 dark:text-emerald-100/50 capitalize'>
                          {item.item_type.replace('_', ' ')}
                        </p>
                      </div>
                    </Link>
                    <button
                      onClick={(e) => {
                        e.preventDefault();
                        handleRemoveWatch(item.id);
                      }}
                      className='p-2 text-gov-copper/60 hover:text-gov-copper hover:bg-gov-copper/10 rounded-lg transition-colors'
                      title='Remove from watchlist'>
                      <Trash2 className='w-4 h-4' />
                    </button>
                  </motion.div>
                ))}
              </div>
            )}
          </motion.div>
        )}

        {/* ──── Alerts ──── */}
        {activeTab === 'alerts' && (
          <motion.div
            key='alerts'
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}>
            {alertsLoading ? (
              <div className='flex justify-center py-20'>
                <Loader2 className='w-6 h-6 animate-spin text-gov-sage' />
              </div>
            ) : alerts.length === 0 ? (
              <div className='text-center py-20 bg-white/60 dark:bg-surface-elevated backdrop-blur-md rounded-2xl border border-gov-sage/15'>
                <BellOff className='w-12 h-12 mx-auto text-gov-sage/30 mb-4' />
                <h3 className='text-lg font-bold text-gov-dark dark:text-white mb-2'>No alerts</h3>
                <p className='text-gov-forest/50 dark:text-emerald-100/50 text-sm max-w-md mx-auto'>
                  When data changes for your watchlist items, you&apos;ll see notifications here.
                </p>
              </div>
            ) : (
              <>
                {unreadCount > 0 && (
                  <div className='flex justify-end mb-4'>
                    <button
                      onClick={handleMarkAllRead}
                      className='flex items-center gap-1.5 text-xs font-semibold text-gov-sage hover:text-gov-forest dark:text-emerald-100 transition-colors'>
                      <CheckCheck className='w-4 h-4' />
                      Mark all read
                    </button>
                  </div>
                )}
                <div className='space-y-3'>
                  {alerts.map((alert) => (
                    <motion.div
                      key={alert.id}
                      layout
                      className={`p-4 rounded-xl border transition-all cursor-pointer ${
                        alert.read
                          ? 'bg-white/60 dark:bg-surface-elevated border-gov-sage/10 opacity-70'
                          : 'bg-white/90 dark:bg-surface-elevated border-gov-sage/20 shadow-sm'
                      }`}
                      onClick={() => !alert.read && handleMarkRead(alert.id)}>
                      <div className='flex items-start gap-3'>
                        {!alert.read && (
                          <div className='w-2.5 h-2.5 rounded-full bg-gov-sage mt-1.5 flex-shrink-0' />
                        )}
                        <div className='flex-1 min-w-0'>
                          <p className='font-semibold text-gov-dark dark:text-white text-sm'>{alert.title}</p>
                          {alert.body && (
                            <p className='text-gov-forest/60 dark:text-emerald-100/60 text-xs mt-1 line-clamp-2'>
                              {alert.body}
                            </p>
                          )}
                          <p className='text-gov-forest/40 dark:text-emerald-100/40 text-xs mt-2'>
                            {new Date(alert.created_at).toLocaleDateString('en-KE', {
                              day: 'numeric',
                              month: 'short',
                              year: 'numeric',
                            })}
                          </p>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ──── Farewell Modal (after account deletion) ──── */}
      <AnimatePresence>
        {showFarewell && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className='fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm px-4'>
            <motion.div
              initial={{ scale: 0.85, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.85, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
              className='bg-white dark:bg-surface-base rounded-3xl p-8 max-w-sm w-full text-center shadow-2xl'>
              <div className='w-16 h-16 mx-auto mb-5 rounded-full bg-gov-sage/10 flex items-center justify-center'>
                <LogOut className='w-8 h-8 text-gov-sage' />
              </div>
              <h2 className='text-xl font-bold text-gov-dark dark:text-white mb-2'>Sorry to see you go</h2>
              <p className='text-sm text-gov-forest/60 dark:text-emerald-100/60 mb-6'>
                Your account has been permanently deleted. Thank you for using Kenya Public Money
                Tracker.
              </p>
              <div className='h-1 bg-gov-sand rounded-full overflow-hidden'>
                <motion.div
                  initial={{ width: '100%' }}
                  animate={{ width: '0%' }}
                  transition={{ duration: 4, ease: 'linear' }}
                  className='h-full bg-gov-sage rounded-full'
                />
              </div>
              <p className='text-xs text-gov-forest/40 dark:text-emerald-100/40 mt-3'>Redirecting to home…</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
