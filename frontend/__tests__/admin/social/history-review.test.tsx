import SocialComposer from '@/components/admin/social/SocialComposer';
import NavTrailTracker from '@/lib/navigation/NavTrailTracker';
import api from '@/lib/api/axios';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, post, system } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }), usePathname: () => window.location.pathname, useSearchParams: () => new URLSearchParams(window.location.search) }));

beforeEach(() => { (api.get as jest.Mock).mockResolvedValue({ data: post() }); });
afterEach(() => { jest.restoreAllMocks(); window.history.replaceState({}, '', '/'); });

test.each([-1, 1])('dirty browser traversal %s can be cancelled without losing the editor or its history', async direction => {
  render(<NavTrailTracker />);
  window.history.pushState({}, '', '/admin/social?page=2');
  window.history.pushState({}, '', '/admin/social/review');
  if (direction === 1) {
    window.history.pushState({}, '', '/admin/social/accounts');
    await act(async () => { window.history.back(); await new Promise(resolve => setTimeout(resolve, 30)); });
    await waitFor(() => expect(window.location.pathname).toBe('/admin/social/review'));
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // A manual draft stays dirty until explicitly saved. Generated drafts
  // autosave after 750ms and cannot establish an unsaved-navigation fixture.
  render(<QueryClientProvider client={queryClient}><SocialComposer accounts={accounts} system={system} /></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText('Post text'), { target: { value: 'Unsaved review wording' } });
  const confirm = jest.spyOn(window, 'confirm').mockReturnValue(false);
  const reached = jest.fn(); window.addEventListener('popstate', reached);
  try {
    await act(async () => { window.history.go(direction); await new Promise(resolve => setTimeout(resolve, 50)); });
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(window.location.pathname).toBe('/admin/social/review'));
    expect(screen.getByLabelText('Post text')).toHaveValue('Unsaved review wording');
    expect(reached).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    await act(async () => { window.history.go(direction); await new Promise(resolve => setTimeout(resolve, 40)); });
    expect(window.location.pathname + window.location.search).toBe(direction < 0 ? '/admin/social?page=2' : '/admin/social/accounts');
    expect(reached).toHaveBeenCalledTimes(1);
  } finally { window.removeEventListener('popstate', reached); queryClient.clear(); }
});
