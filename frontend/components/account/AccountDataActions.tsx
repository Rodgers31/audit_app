'use client';

import { useAuth } from '@/lib/auth/AuthProvider';
import { useLang } from '@/lib/i18n/LangProvider';
import { ACCOUNT_MESSAGES as copy } from '@/lib/i18n/messages/account';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { downloadAccountData } from './downloadAccountData';

export default function AccountDataActions({ accountId }: { accountId: string }) {
  const { lang } = useLang();
  const { deleteAccount, logout } = useAuth();
  const router = useRouter();
  const download = useRef<AbortController | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const deleteInput = useRef<HTMLInputElement>(null);
  const [downloadState, setDownloadState] = useState<'pending' | 'error' | null>(null);
  const [typed, setTyped] = useState('');
  const [deleteState, setDeleteState] = useState<'pending' | 'error' | 'deleted' | null>(null);

  useEffect(() => () => download.current?.abort(), []);
  useEffect(() => {
    if (deleteState !== 'deleted') return;
    const timer = window.setTimeout(() => {
      void logout().finally(() => router.replace('/'));
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [deleteState, logout, router]);

  async function handleDownload() {
    if (download.current) return;
    const request = new AbortController();
    download.current = request;
    setDownloadState('pending');
    try {
      await downloadAccountData(accountId, request.signal);
      setDownloadState(null);
    } catch {
      if (!request.signal.aborted) setDownloadState('error');
    } finally {
      download.current = null;
    }
  }

  async function handleDelete() {
    if (typed !== 'DELETE' || deleteState === 'pending' || deleteState === 'deleted') return;
    setDeleteState('pending');
    try {
      await deleteAccount();
      download.current?.abort();
      dialog.current?.close();
      setDeleteState('deleted');
    } catch {
      setDeleteState('error');
    }
  }

  return (
    <section aria-labelledby='account-data' className='audit-panel space-y-3 p-4 sm:p-5'>
      <h2 id='account-data' className='font-display text-audit-heading font-semibold'>{copy.data[lang]}</h2>
      <div className='flex flex-col gap-2 sm:flex-row sm:flex-wrap'>
        <button type='button' className='audit-control border-neutral-text bg-surface-elevated' onClick={handleDownload}
          disabled={downloadState === 'pending' || deleteState === 'deleted'}>
          {downloadState === 'pending' ? copy.downloading[lang] : copy.download[lang]}
        </button>
        <button type='button' className='audit-control border-signal-alarm text-signal-alarm'
          aria-haspopup='dialog' aria-controls='account-delete-dialog' aria-describedby='account-delete-scope'
          disabled={deleteState === 'deleted'} onClick={(event) => {
            event.currentTarget.focus();
            dialog.current?.showModal();
            deleteInput.current?.focus();
          }}>
          {copy.delete[lang]}
        </button>
      </div>
      {downloadState === 'error' && <p role='alert' className='text-sm text-signal-alarm'>{copy.downloadError[lang]}</p>}
      <p id='account-delete-scope' className='text-sm text-neutral-muted'>{copy.deleteScope[lang]}</p>
      <p role='status' className={deleteState === 'deleted' ? 'text-sm' : 'sr-only'}>
        {deleteState === 'deleted' && copy.deleted[lang]}
      </p>
      <dialog ref={dialog} id='account-delete-dialog' aria-labelledby='account-delete-title'
        aria-describedby='account-delete-dialog-scope'
        className='audit-panel fixed inset-0 m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-md overflow-y-auto p-4 text-neutral-text sm:p-5 backdrop:bg-gov-dark/55'
        onCancel={(event) => {
          if (deleteState === 'pending') event.preventDefault();
        }}
        onClose={() => {
          setTyped('');
          setDeleteState(state => state === 'error' ? null : state);
        }}>
        <form className='space-y-3' onSubmit={(event) => {
          event.preventDefault();
          void handleDelete();
        }}>
          <h2 id='account-delete-title' className='font-display text-audit-heading font-semibold'>{copy.delete[lang]}</h2>
          <p id='account-delete-dialog-scope' className='text-sm text-neutral-muted'>{copy.deleteScope[lang]}</p>
          <label className='block text-sm font-semibold'>
            {copy.confirmDelete[lang]}
            <input ref={deleteInput} value={typed} onChange={event => setTyped(event.target.value)}
              type='text' autoComplete='off' autoCapitalize='characters' spellCheck={false}
              className='mt-1 min-h-11 w-full rounded border border-neutral-text bg-surface-elevated px-3 text-base text-neutral-text'
              disabled={deleteState === 'pending'} />
          </label>
          {deleteState === 'error' && <p role='alert' className='text-sm text-signal-alarm'>{copy.deleteError[lang]}</p>}
          <div className='flex flex-wrap gap-2'>
            <button type='submit' className='audit-control border-signal-alarm text-signal-alarm'
              disabled={typed !== 'DELETE' || deleteState === 'pending'}>
              {deleteState === 'pending' ? copy.deletePending[lang] : copy.delete[lang]}
            </button>
            <button type='button' className='audit-control' disabled={deleteState === 'pending'}
              onClick={() => dialog.current?.close()}>{copy.cancel[lang]}</button>
          </div>
        </form>
      </dialog>
    </section>
  );
}
