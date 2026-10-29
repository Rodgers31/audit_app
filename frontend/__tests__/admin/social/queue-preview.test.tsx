import SocialWorkspace from '@/components/admin/social/SocialWorkspace';
import api from '@/lib/api/axios';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { accounts, post, system, facebookId, instagramId } from '../../../tests/socialFixtures';
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
let actor = 'first';
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: actor } }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));
const get = api.get as jest.Mock;
const p = post({ document: { ...post().document, master: { text: 'Nairobi County: about KSh 86.9 billion.', link: 'https://www.auditgava.com/counties/nairobi-county?tab=budget&as_at=2026-06-30#pending-bills', hashtags: [], media: [] }, targets: [{account_id: facebookId, format: 'text', overrides: {}}, {account_id: instagramId, format: 'image', overrides: { text: {mode: 'replace', value: 'Instagram wording'} }}] } });
let clients: QueryClient[] = [];
beforeEach(() => {
  actor = 'first'; jest.clearAllMocks(); window.history.replaceState({}, '', '/admin/social');
  get.mockImplementation(async (path: string) => ({ data: path.endsWith('/accounts') ? {accounts} : path.endsWith('/system/status') ? system : path.endsWith('/posts') ? {posts: [p], total: 1, page: 1, page_size: 20, has_more: false} : p }));
});
afterEach(() => { clients.forEach(c => c.clear()); clients = []; window.history.replaceState({}, '', '/'); });
function mount() { const client = new QueryClient({ defaultOptions: { queries: {retry: false} } }); clients.push(client); return render(<QueryClientProvider client={client}><SocialWorkspace /></QueryClientProvider>); }
test('preview loads the saved document on demand and resolves account overrides and the actual destination', async () => {
  mount(); const button = await screen.findByRole('button', {name: /Preview post:/});
  expect(get.mock.calls.some(([path]) => path.endsWith('/posts/' + p.id))).toBe(false);
  fireEvent.click(button);
  await screen.findByText('Nairobi County: about KSh 86.9 billion.');
  expect(screen.getByRole('link', {name: p.document.master.link!})).toHaveAttribute('href', p.document.master.link);
  expect(screen.getByText(/Approximate preview/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Preview account'), {target: {value: instagramId}});
  expect(screen.getByText('Instagram wording')).toBeInTheDocument();
  expect(screen.getByText(/may not be clickable on Instagram/)).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled(); expect(api.patch).not.toHaveBeenCalled();
});
test('late private preview cannot appear after actor switch', async () => {
  let release!: (value: unknown) => void;
  const original = get.getMockImplementation()!;
  get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/posts/' + p.id) ? new Promise(resolve => { release = resolve; }) : original(path, ...args));
  const tree = mount(); fireEvent.click(await screen.findByRole('button', {name: /Preview post:/}));
  await waitFor(() => expect(release).toBeDefined()); actor = 'second'; tree.rerender(<QueryClientProvider client={clients[0]}><SocialWorkspace /></QueryClientProvider>);
  await screen.findByRole('button', {name: /Preview post:/});
  await act(async () => release({data: p}));
  expect(screen.queryByText('Nairobi County: about KSh 86.9 billion.')).not.toBeInTheDocument();
});
test('a different revision is never shown as the listed saved revision', async () => {
  const original = get.getMockImplementation()!;
  get.mockImplementation((path: string, ...args: unknown[]) => path.endsWith('/posts/' + p.id) ? Promise.resolve({data: {...p, revision_id: '00000000-0000-4000-8000-000000000999'}}) : original(path, ...args));
  mount(); fireEvent.click(await screen.findByRole('button', {name: /Preview post:/}));
  await screen.findByText(/The saved revision changed/);
  expect(screen.queryByText('Nairobi County: about KSh 86.9 billion.')).not.toBeInTheDocument();
});
