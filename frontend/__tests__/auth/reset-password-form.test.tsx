import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ResetPassword from '@/app/reset-password/page';
const mockRefresh = jest.fn();
const mockReplace = jest.fn();
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ refreshUser: mockRefresh, isAuthenticated: false, isLoading: false }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: mockReplace }), useSearchParams: () => new URLSearchParams() }));
beforeEach(() => {
  jest.clearAllMocks();
  window.scrollTo = jest.fn();
});
test('form sends only password and synchronous double submit performs one request', async () => {
  let finish!: (value: unknown) => void;
  const fetchMock = jest.fn((_url: string, _init: RequestInit) => new Promise(resolve => {
    finish = resolve;
  }));
  global.fetch = fetchMock as any;
  render(<ResetPassword />);
  fireEvent.change(screen.getByPlaceholderText('Enter new password'), { target: { value: 'InertPass123!' } });
  fireEvent.change(screen.getByPlaceholderText('Re-enter new password'), { target: { value: 'InertPass123!' } });
  const form = screen.getByPlaceholderText('Enter new password').closest('form')!;
  fireEvent.submit(form);
  fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({ password: 'InertPass123!' });
  finish({ ok: false, json: async () => ({ error: 'Synthetic reset refusal' }) });
  await waitFor(() => expect(screen.getByText('Synthetic reset refusal')).toBeTruthy());
  expect(mockRefresh).not.toHaveBeenCalled();
});
