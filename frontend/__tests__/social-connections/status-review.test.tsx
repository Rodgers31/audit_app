import MetaAccounts from '@/components/admin/social/connections/MetaAccounts';
import { decodeConnectionStatus, MetaConnectionStatus } from '@/lib/api/socialConnections';
import api from '@/lib/api/axios';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { accounts } from '../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));

const status: MetaConnectionStatus = { provider: 'meta', available: false, blockers: ['CONNECTIONS_DISABLED'], access_mode: 'unverified', scopes: ['pages_show_list'], publishing_adapter_available: false };
const combinations = (['unverified','owned_standard','advanced'] as const).flatMap(access_mode => [false,true].flatMap(available => [[], ['CONNECTIONS_DISABLED']].map(blockers => ({ access_mode, available, blockers }))));
beforeEach(() => { jest.clearAllMocks(); });

test.each(combinations)('status consistency: $access_mode / available=$available / blockers=$blockers', combination => {
  const value = { ...status, ...combination };
  const coherent = combination.available === (combination.blockers.length === 0) && !(combination.available && combination.access_mode === 'unverified');
  if (coherent) expect(decodeConnectionStatus(value)).toEqual(value);
  else expect(() => decodeConnectionStatus(value)).toThrow(expect.objectContaining({ code: 'INVALID_RESPONSE' }));
});

test('an unverified available response cannot enable the real account-management UI', async () => {
  (api.get as jest.Mock).mockImplementation(async (path: string) => ({ data: path.endsWith('/connections/meta/status') ? { ...status, available: true, blockers: [] } : { accounts: [] } }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  try {
    render(<QueryClientProvider client={qc}><MetaAccounts /></QueryClientProvider>);
    expect(await screen.findByRole('alert')).toHaveTextContent('INVALID_RESPONSE');
    expect(screen.queryByRole('button', { name: 'Connect owned Meta accounts' })).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  } finally { qc.clear(); }
});

test.each(['owned_standard','advanced'] as const)('configured %s remains available without claiming empty accounts mean unavailable OAuth', async access_mode => {
  (api.get as jest.Mock).mockImplementation(async (path: string) => ({ data: path.endsWith('/connections/meta/status') ? { ...status, access_mode, available: true, blockers: [] } : { accounts: [] } }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  try {
    render(<QueryClientProvider client={qc}><MetaAccounts /></QueryClientProvider>);
    expect(await screen.findByRole('button', { name: 'Connect owned Meta accounts' })).toBeEnabled();
    expect(await screen.findByText(/No Meta accounts are connected/)).toBeInTheDocument();
    expect(screen.queryByText(/while account configuration is unavailable/)).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  } finally { qc.clear(); }
});

test.each(['Connect owned Meta accounts','Reconnect identity'])('a failed status refresh cannot keep previously available %s actionable', async action => {
  let malformed = false;
  (api.get as jest.Mock).mockImplementation(async (path: string) => ({ data: path.endsWith('/connections/meta/status') ? { ...status, access_mode: malformed ? 'unverified' : 'owned_standard', available: true, blockers: [] } : { accounts } }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  try {
    render(<QueryClientProvider client={qc}><MetaAccounts /></QueryClientProvider>);
    expect(await screen.findByRole('button', { name: 'Connect owned Meta accounts' })).toBeEnabled();
    (await screen.findAllByRole('button', { name: action })).forEach(button => expect(button).toBeEnabled());
    malformed = true; fireEvent.click(screen.getByRole('button', { name: 'Refresh accounts' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('INVALID_RESPONSE');
    screen.getAllByRole('button', { name: action }).forEach(button => { expect(button).toBeDisabled(); fireEvent.click(button); });
    expect(api.post).not.toHaveBeenCalled();
  } finally { qc.clear(); }
});
