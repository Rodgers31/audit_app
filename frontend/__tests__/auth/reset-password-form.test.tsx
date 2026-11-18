import { act, fireEvent, render, screen } from '@testing-library/react';
import ResetPassword from '@/app/reset-password/page';

const mockRefresh = jest.fn();
const mockReplace = jest.fn();
const mockAuthState = { isAuthenticated: false, isLoading: false };
let mockSearchParams: URLSearchParams;

jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ refreshUser: mockRefresh, ...mockAuthState }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: mockReplace }), useSearchParams: () => mockSearchParams }));

const password = 'InertPass123!';
const selector = 'a'.repeat(32);
const originalFetch = global.fetch;

function fillMatchingPasswords() {
  const field = screen.getByLabelText('New password', { exact: true });
  fireEvent.change(field, { target: { value: password } });
  fireEvent.change(screen.getByLabelText('Type it again'), { target: { value: password } });
  return (field as HTMLInputElement).form!;
}

beforeEach(() => {
  jest.resetAllMocks();
  mockAuthState.isAuthenticated = false;
  mockAuthState.isLoading = false;
  mockSearchParams = new URLSearchParams();
  window.history.replaceState({}, '', '/reset-password#recovery-flow=' + selector);
});

afterEach(() => {
  global.fetch = originalFetch;
  jest.useRealTimers();
});

test('shows the implemented rules before the form and keeps the password controls accessible', () => {
  render(<ResetPassword />);
  expect(screen.getByText(/up to five minutes to save after opening a valid reset link/)).toBeVisible();
  const newPassword = screen.getByLabelText('New password', { exact: true });
  expect(newPassword).toHaveAccessibleDescription(/at least 8 characters.*uppercase.*lowercase.*number/);
  expect(newPassword).toHaveAttribute('minlength', '8');
  expect(newPassword).toHaveAttribute('maxlength', '1024');
  expect(newPassword).toHaveAttribute('autocomplete', 'new-password');
  expect(screen.getByRole('button', { name: 'Save password' })).toBeDisabled();

  const show = screen.getByRole('button', { name: 'Show new password' });
  show.focus();
  fireEvent.click(show);
  expect(screen.getByRole('button', { name: 'Hide new password' })).toHaveFocus();
  expect(newPassword).toHaveAttribute('type', 'text');
  fireEvent.click(show);
  expect(newPassword).toHaveAttribute('type', 'password');

  fireEvent.change(newPassword, { target: { value: 'weak1234' } });
  const confirm = screen.getByLabelText('Type it again');
  fireEvent.change(confirm, { target: { value: 'weak1234' } });
  expect(screen.getByRole('button', { name: 'Save password' })).toBeDisabled();

  fireEvent.change(newPassword, { target: { value: password } });
  expect(confirm).toHaveAttribute('aria-invalid', 'true');
  expect(confirm).toHaveAccessibleDescription('Passwords do not match.');
  fireEvent.change(confirm, { target: { value: password } });
  expect(confirm).not.toHaveAttribute('aria-invalid');
  expect(screen.getByRole('button', { name: 'Save password' })).toBeEnabled();
});

test('form sends password and its own selector and synchronous double submit performs one request', async () => {
  let finish!: (value: unknown) => void;
  const fetchMock = jest.fn((_url: string, _init: RequestInit) => new Promise(resolve => { finish = resolve; }));
  global.fetch = fetchMock as typeof fetch;
  render(<ResetPassword />);
  const form = fillMatchingPasswords();

  fireEvent.submit(form);
  fireEvent.submit(form);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith('/api/auth/reset-password', expect.objectContaining({ method: 'POST' }));
  expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({ password, flow: selector });
  expect(form).toHaveAttribute('aria-busy', 'true');
  expect(screen.getByRole('button', { name: 'Saving password…' })).toBeDisabled();

  await act(async () => { finish({ ok: false, json: async () => ({ error: 'Synthetic reset refusal' }) }); });
  expect(screen.getByRole('alert')).toHaveTextContent('Synthetic reset refusal');
  expect(screen.getByRole('button', { name: 'Save password' })).toBeEnabled();
  expect(mockRefresh).not.toHaveBeenCalled();
});

test('auth readiness and link errors keep their original precedence over the form', async () => {
  mockAuthState.isLoading = true;
  mockSearchParams.set('error', 'Invalid reset link. Please request a new one.');
  const { rerender } = render(<ResetPassword />);
  expect(screen.getByRole('status')).toHaveTextContent('Loading the reset form');
  expect(screen.queryByLabelText('New password')).toBeNull();

  mockAuthState.isLoading = false;
  rerender(<ResetPassword />);
  expect(screen.getByRole('alert')).toHaveTextContent('Invalid reset link');
  expect(screen.getByRole('link', { name: 'Back to homepage' })).toHaveAttribute('href', '/');

  mockAuthState.isAuthenticated = true;
  global.fetch = jest.fn().mockResolvedValue({ ok: false, json: async () => ({ error: 'Synthetic form refusal' }) });
  rerender(<ResetPassword />);
  expect(screen.queryByRole('alert')).toBeNull();
  await act(async () => { fireEvent.submit(fillMatchingPasswords()); });
  expect(screen.getByRole('alert')).toHaveTextContent('Synthetic form refusal');
});

test('an ambiguous selector is sent as null and success refreshes the session before scheduling the redirect', async () => {
  jest.useFakeTimers();
  window.history.replaceState({}, '', `/reset-password#recovery-flow=${selector}&recovery-flow=${selector}`);
  global.fetch = jest.fn().mockResolvedValue({ ok: true });
  let refresh!: () => void;
  mockRefresh.mockReturnValue(new Promise<void>(resolve => { refresh = resolve; }));
  render(<ResetPassword />);
  await act(async () => { fireEvent.submit(fillMatchingPasswords()); });
  expect(global.fetch).toHaveBeenCalledWith('/api/auth/reset-password',
    expect.objectContaining({ body: JSON.stringify({ password, flow: null }) }));
  expect(mockRefresh).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('heading', { name: 'Password updated' })).toHaveFocus();
  expect(screen.getByRole('status')).toHaveTextContent('Taking you to the homepage');

  act(() => { jest.advanceTimersByTime(1200); });
  expect(mockReplace).not.toHaveBeenCalled();
  await act(async () => { refresh(); });
  act(() => { jest.advanceTimersByTime(1199); });
  expect(mockReplace).not.toHaveBeenCalled();
  act(() => { jest.advanceTimersByTime(1); });
  expect(mockReplace).toHaveBeenCalledWith('/');
});
