import AdminLayout from '@/app/admin/layout';
import SocialWorkspace from '@/components/admin/social/SocialWorkspace';
import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import { socialKeys } from '@/lib/hooks/useSocial';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { AppRouterContext } from 'next/dist/shared/lib/app-router-context.shared-runtime';
import { RouterContext } from 'next/dist/shared/lib/router-context.shared-runtime';
import type { NextRouter } from 'next/router';
import { accounts, actorId, post, system } from '../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }), AdminGuard: ({children}: {children: React.ReactNode}) => children }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));

jest.mock('next/navigation', () => ({ ...jest.requireActual('next/navigation'), usePathname: () => '/admin/social' }));

const get = api.get as jest.Mock;
let clients: QueryClient[];
const router = { push: jest.fn(), replace: jest.fn(), refresh: jest.fn(), back: jest.fn(), forward: jest.fn(), prefetch: jest.fn().mockResolvedValue(undefined) };

function mount(empty = false, composer = false) {
  const p = post({ editorial_state: 'pending_review', ...(empty ? { document: { ...post().document, targets: [] } } : {}) });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  clients.push(qc); qc.setQueryData(socialKeys.detail(actorId, p.id), p);
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/accounts') ? { accounts: empty ? [] : accounts } : path.endsWith('/system/status') ? system : path.endsWith('/posts') ? { posts: [p], total: 1, page: 1, page_size: 20, has_more: false } : p }));
  render(<AppRouterContext.Provider value={router}><RouterContext.Provider value={router as unknown as NextRouter}><QueryClientProvider client={qc}><AdminLayout>{composer ? <SocialComposer initialPost={p} accounts={[]} system={system} /> : <SocialWorkspace />}</AdminLayout></QueryClientProvider></RouterContext.Provider></AppRouterContext.Provider>);
  return p;
}
function accountsNavigation() {
  const summary = screen.getByText('Manage social'); if (!summary.closest('details')?.open) fireEvent.click(summary);
  return within(screen.getByRole('navigation', { name: 'Social workspace' })).getByRole('link', { name: 'Connected accounts' });
}
beforeEach(() => { jest.clearAllMocks(); clients = []; });
afterEach(() => { clients.forEach(qc => qc.clear()); jest.restoreAllMocks(); });

test('the existing Accounts navigation opens the connected-account route once', () => {
  mount(); fireEvent.click(accountsNavigation());
  expect(router.push).toHaveBeenCalledTimes(1);
  expect(router.push.mock.calls[0][0]).toBe('/admin/social/accounts');
  expect(accountsNavigation()).toHaveAttribute('href', '/admin/social/accounts');
  expect(screen.queryByText(/Account connection and OAuth are unavailable in this batch/)).not.toBeInTheDocument();
  expect(within(screen.getByRole('navigation', { name: 'Social workspace' })).getAllByRole('link', { name: /^(Connected accounts|Accounts)$/ })).toHaveLength(1);
});

test('Accounts navigation preserves the existing unsaved-draft decision', async () => {
  mount(false, true);
  await screen.findByRole('article', { name: 'Social post composer' });
  fireEvent.change(screen.getByLabelText('Post text'), { target: { value: 'Unsaved evidence review' } });
  const confirm = jest.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
  fireEvent.click(accountsNavigation());
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(confirm).toHaveBeenCalledWith('This draft has unsaved edits. Leave without saving?');
  expect(router.push).not.toHaveBeenCalled();
  expect(screen.getByLabelText('Post text')).toHaveValue('Unsaved evidence review');
  fireEvent.click(accountsNavigation());
  expect(confirm).toHaveBeenCalledTimes(2);
  expect(router.push).toHaveBeenCalledTimes(1);
  expect(router.push.mock.calls[0][0]).toBe('/admin/social/accounts');
});

test('an empty composer reports missing identities without inventing unavailable OAuth', () => {
  mount(true, true);
  expect(screen.getByText(/No connected accounts\. You can save a manual draft\./)).toBeInTheDocument();
  expect(screen.queryByText(/Account connection is unavailable in this batch/)).not.toBeInTheDocument();
});

beforeEach(() => { window.history.replaceState({}, "", "/admin/social"); });
