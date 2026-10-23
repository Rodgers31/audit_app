import { render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server.node';
import { AdminGuard } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';

jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: jest.fn() }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn() }) }));
const actor = '00000000-0000-4000-8000-000000000001';
const mounted = jest.fn();
function PrivatePage() { mounted(); return <h1>Private admin page</h1>; }
function auth(isLoading: boolean) {
  (useAuth as jest.Mock).mockReturnValue({
    isLoading, isAuthenticated: true, authUser: { id: actor }, user: { id: actor, roles: ['admin'] },
  });
}
beforeEach(() => { mounted.mockClear(); auth(true); });

test('SSR uses the same auth placeholder rather than a page that hydration removes', () => {
  const html = renderToString(<AdminGuard><PrivatePage /></AdminGuard>);
  expect(html).toContain('Verifying access');
  expect(html).not.toContain('Private admin page');
  expect(mounted).not.toHaveBeenCalled();
});

test('pending authentication never mounts the private page, then verified access mounts it once', () => {
  const view = render(<AdminGuard><PrivatePage /></AdminGuard>);
  expect(screen.getByText('Verifying access…')).toBeInTheDocument();
  expect(mounted).not.toHaveBeenCalled();
  auth(false);
  view.rerender(<AdminGuard><PrivatePage /></AdminGuard>);
  expect(screen.getByRole('heading', { name: 'Private admin page' })).toBeInTheDocument();
  expect(mounted).toHaveBeenCalledTimes(1);
});
