import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import UsersList from '@/app/admin/users/page';
import UserDetail from '@/app/admin/users/[userId]/page';

const id = '11111111-1111-4111-8111-111111111111';
let mockActor = '22222222-2222-4222-8222-222222222222';
let mockAuthorized = true;
let mockRoleOverride: unknown = undefined;
let mockProfileId: string | null = null;
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
  useAuth: () => ({ authUser: { id: mockActor }, user: { id: mockProfileId ?? mockActor, roles: mockRoleOverride === undefined ? (mockAuthorized ? ['admin'] : []) : mockRoleOverride }, isAuthenticated: true, isLoading: false }),
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
  mockRoleOverride = undefined;
  mockProfileId = null;
  mockParams = new URLSearchParams();
  mockGet.mockResolvedValue({ data: detail });
});

for (const transition of ['actor', 'revocation']) {
 test(`adversarial late accepted delete after ${transition} cannot redirect`, async () => {
  let finish:any; mockDelete.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const params=Promise.resolve({userId:id}); const qc=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  const tree=()=> <QueryClientProvider client={qc}><UserDetail params={params}/></QueryClientProvider>;
  let view:any; await act(async()=>{view=render(tree());}); await screen.findByText('Roles');
  fireEvent.click(screen.getByRole('button',{name:'Delete…'}));fireEvent.change(screen.getByLabelText('Confirm deletion'),{target:{value:detail.email}});
  fireEvent.click(screen.getByRole('button',{name:'Delete permanently'}));await waitFor(()=>expect(mockDelete).toHaveBeenCalledTimes(1));
  if(transition==='actor') mockActor='33333333-3333-4333-8333-333333333333';else mockAuthorized=false;
  view.rerender(tree());mockReplace.mockClear();
  await act(async()=>{finish({data:{ok:true,audit_recorded:true}});});
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,30));});
  if(mockReplace.mock.calls.length!==0)throw new Error('Late navigation: '+JSON.stringify(mockReplace.mock.calls));
 });
 test(`adversarial late accepted roles after ${transition} cannot repopulate cache`, async () => {
  let finish:any; mockPatch.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  const params=Promise.resolve({userId:id});const qc=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
  const tree=()=> <QueryClientProvider client={qc}><UserDetail params={params}/></QueryClientProvider>;let view:any;
  await act(async()=>{view=render(tree());});await screen.findByText('Roles');
  fireEvent.click(screen.getByRole('button',{name:'admin'}));fireEvent.click(screen.getByRole('button',{name:'Save changes'}));await waitFor(()=>expect(mockPatch).toHaveBeenCalledTimes(1));
  if(transition==='actor')mockActor='33333333-3333-4333-8333-333333333333';else mockAuthorized=false;
  view.rerender(tree());const write=jest.spyOn(qc,'setQueryData');
  await act(async()=>{finish({data:{...detail,roles:['citizen','admin'],ok:true,audit_recorded:true}});});
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,30));});if(write.mock.calls.length!==0)throw new Error('Late cache writes: '+JSON.stringify(write.mock.calls));
 });
}

test.each(['admin', 'not-admin', {admin: false}, ['admin', NaN], ['admin', Infinity], ['admin', true], ['admin', null], ['admin', []], ['admin', {}], ['admin', ''], ['admin', '\t\n'], null, []])('adversarial users page rejects malformed roles %p without fetching', async roles => {
  mockRoleOverride=roles;show(<UsersList/>);
  await screen.findByText('Administrator access required.');
  expect(mockGet.mock.calls.length).toBe(0);
});
test('adversarial stale profile identity cannot fetch users',async()=>{
 mockProfileId='33333333-3333-4333-8333-333333333333';show(<UsersList/>);
 await screen.findByText('Administrator access required.');expect(mockGet.mock.calls.length).toBe(0);
});
test('adversarial legitimate unknown roles remain allowed alongside admin',async()=>{
 mockRoleOverride=['citizen','admin','legacy-auditor'];mockGet.mockResolvedValue({data:{users:[],total:0,page:1,page_size:20,has_more:false}});
 show(<UsersList/>);await screen.findByText('No users match.');expect(mockGet.mock.calls.length).toBe(1);
});
