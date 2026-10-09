import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import UsersList from '@/app/admin/users/page';
import UserDetail from '@/app/admin/users/[userId]/page';

const id = '11111111-1111-4111-8111-111111111111';
let mockActor = '22222222-2222-4222-8222-222222222222';
let mockAuthorized = true;
const self = '22222222-2222-4222-8222-222222222222';
const detail = {
  id,
  email: 'fixture@example.invalid',
  display_name: null,
  roles: ['citizen'],
  created_at: null,
  last_sign_in_at: null,
  email_confirmed: true,
  banned_until: null,
  app_metadata: {},
  user_metadata: {},
  updated_at: null,
};
let mockParams = new URLSearchParams();
const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockGet = jest.fn();
const mockPatch = jest.fn();
const mockPost = jest.fn();
const mockDelete = jest.fn();
jest.mock('next/navigation', () => ({
  useSearchParams: () => mockParams,
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));
jest.mock('@/lib/api/axios', () => ({
  __esModule: true,
  default: {
    get: (...a: unknown[]) => mockGet(...a),
    patch: (...a: unknown[]) => mockPatch(...a),
    post: (...a: unknown[]) => mockPost(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
}));
jest.mock('@/lib/auth/AuthProvider', () => ({
  useAuth: () => ({ authUser: { id: mockActor }, user: { id: mockActor, roles: mockAuthorized ? ['admin'] : [] }, isAuthenticated: true, isLoading: false }),
}));
jest.mock('@/components/layout/PageShell', () => ({
  __esModule: true,
  default: ({ title, children }: any) => (
    <main>
      <h1>{title}</h1>
      {children}
    </main>
  ),
}));
jest.mock('framer-motion', () => {
  const React = require('react');
  return {
    motion: new Proxy(
      {},
      {
        get: (_, tag) => {
          const Component = React.forwardRef(
            ({ variants, initial, animate, custom, ...props }: any, ref: any) =>
              React.createElement(tag, { ...props, ref })
          );
          Component.displayName = 'MockMotion';
          return Component;
        },
      }
    ),
  };
});
function show(node: React.ReactNode) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      {node}
    </QueryClientProvider>
  );
}
async function showDetail() {
  const params = Promise.resolve({ userId: id });
  await act(async () => {
    show(<UserDetail params={params} />);
  });
  await screen.findByText('Roles');
}
beforeEach(() => {
  jest.clearAllMocks();
  mockActor = self;
  mockAuthorized = true;
  mockParams = new URLSearchParams();
  mockGet.mockResolvedValue({ data: detail });
});

test('invalid URL page never reaches provider as NaN', async () => {
  mockParams = new URLSearchParams('page=nope');
  mockGet.mockResolvedValue({
    data: { users: [], total: 0, page: 1, page_size: 20, has_more: false },
  });
  show(<UsersList />);
  await waitFor(() => expect(mockGet).toHaveBeenCalled());
  expect(mockGet.mock.calls[0][1].params.page).toBe(1);
});
test('malformed list recovers through refresh without a render crash', async () => {
  mockGet
    .mockResolvedValueOnce({
      data: {
        users: [],
        total: 'broken',
        page: 1,
        page_size: 20,
        has_more: false,
      },
    })
    .mockResolvedValue({
      data: { users: [], total: 0, page: 1, page_size: 20, has_more: false },
    });
  show(<UsersList />);
  await screen.findByText('Could not load users.');
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await screen.findByText('No users match.');
});
test('empty later page retains previous navigation', async () => {
  mockParams = new URLSearchParams('page=2');
  mockGet.mockResolvedValue({
    data: { users: [], total: 0, page: 2, page_size: 20, has_more: false },
  });
  show(<UsersList />);
  await screen.findByText('No users match.');
  expect(screen.getByRole('button', { name: 'Prev' })).toBeEnabled();
});
test('expired ban does not label an active user as banned', async () => {
  mockGet.mockResolvedValue({
    data: {
      users: [{ ...detail, banned_until: '2000-01-01T00:00:00Z' }],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
    },
  });
  show(<UsersList />);
  await screen.findAllByText(detail.email);
  expect(screen.queryByText('banned')).not.toBeInTheDocument();
});
test('browser URL changes synchronize search input', async () => {
  mockGet.mockResolvedValue({
    data: { users: [], total: 0, page: 1, page_size: 20, has_more: false },
  });
  const view = show(<UsersList />);
  await screen.findByPlaceholderText('Search by email…');
  mockParams = new URLSearchParams('q=history');
  view.rerender(
    <QueryClientProvider client={new QueryClient()}>
      <UsersList />
    </QueryClientProvider>
  );
  await waitFor(() =>
    expect(screen.getByPlaceholderText('Search by email…')).toHaveValue('history')
  );
});
test('reset semantically failed response never announces success', async () => {
  mockPost.mockResolvedValue({
    data: { ok: false, audit_recorded: true, email: detail.email },
  });
  await showDetail();
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await screen.findByText(/Failed to send/);
  expect(screen.queryByText('Email queued.')).not.toBeInTheDocument();
});
test('role false acknowledgment retains pending edits', async () => {
  mockPatch.mockResolvedValue({
    data: { ...detail, roles: ['admin'], ok: false, audit_recorded: true },
  });
  await showDetail();
  fireEvent.click(screen.getByRole('button', { name: 'admin' }));
  fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  await screen.findByText('Failed to update roles.');
  expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument();
});
test('audit failure after accepted reset is visible and blocks accidental repeat', async () => {
  mockPost.mockResolvedValue({
    data: { ok: true, audit_recorded: false, email: detail.email },
  });
  await showDetail();
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await screen.findByText(/audit record could not be saved/i);
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
});
test('detail provider failure offers retry', async () => {
  mockGet.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ data: detail });
  const params = Promise.resolve({ userId: id });
  await act(async () => {
    show(<UserDetail params={params} />);
  });
  fireEvent.click(await screen.findByRole('button', { name: 'Retry' }));
  await screen.findByText('Roles');
});


test('private user list is fetched again when the administrator identity changes', async () => {
  mockGet.mockResolvedValue({data:{users:[detail],total:1,page:1,page_size:20,has_more:false}});
  const qc = new QueryClient({defaultOptions:{queries:{retry:false}}});
  const view = render(<QueryClientProvider client={qc}><UsersList/></QueryClientProvider>);
  await screen.findAllByText('fixture@example.invalid');
  mockActor = '33333333-3333-4333-8333-333333333333';
  mockGet.mockResolvedValue({data:{users:[],total:0,page:1,page_size:20,has_more:false}});
  view.rerender(<QueryClientProvider client={qc}><UsersList/></QueryClientProvider>);
  await screen.findByText('No users match.');
  expect(screen.queryAllByText('fixture@example.invalid')).toHaveLength(0);
  expect(mockGet).toHaveBeenCalledTimes(2);
});

test('private users are removed immediately when admin access is revoked', async () => {
  mockGet.mockResolvedValue({data:{users:[detail],total:1,page:1,page_size:20,has_more:false}});
  const qc=new QueryClient({defaultOptions:{queries:{retry:false}}});
  const view=render(<QueryClientProvider client={qc}><UsersList/></QueryClientProvider>);
  await screen.findAllByText('fixture@example.invalid');
  mockAuthorized=false;
  view.rerender(<QueryClientProvider client={qc}><UsersList/></QueryClientProvider>);
  expect(screen.queryAllByText('fixture@example.invalid')).toHaveLength(0);
  expect(mockGet).toHaveBeenCalledTimes(1);
});
