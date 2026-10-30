import AdminPageShell from '@/components/admin/AdminPageShell';
import StatusPage from '@/app/status/page';
import api from '@/lib/api/axios';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';

const back = jest.fn();
jest.mock('next/navigation', () => ({ useRouter: () => ({ back }), usePathname: () => '/status' }));
jest.mock('@/lib/auth/admin', () => ({ AdminGuard: ({ children }: { children: React.ReactNode }) => children }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn() } }));
afterEach(() => { sessionStorage.clear(); jest.clearAllMocks(); });

test('shared admin back link restores the previous list query and scroll through browser history', () => {
  window.history.pushState({}, '', '/admin/users');
  sessionStorage.setItem('auditgava-nav-trail', JSON.stringify([{ pathname: '/admin/users', search: '?page=4', ts: 1 }, { pathname: '/admin/users/123', search: '', ts: 2 }]));
  render(<AdminPageShell title='Person' back={{ href: '/admin/users', label: 'All people' }}>Details</AdminPageShell>);
  fireEvent.click(screen.getByRole('link', { name: /All people/ }));
  expect(back).toHaveBeenCalledTimes(1);
});

test('the separately guarded status route includes shared admin navigation while loading', () => {
  (api.get as jest.Mock).mockImplementation(() => new Promise(() => {}));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = render(<QueryClientProvider client={queryClient}><StatusPage /></QueryClientProvider>);
  expect(screen.getByRole('navigation', { name: 'Admin navigation' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'System status' })).toHaveAttribute('aria-current', 'page');
  tree.unmount(); queryClient.clear();
});
