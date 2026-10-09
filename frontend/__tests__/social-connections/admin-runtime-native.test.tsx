import { decodeSelectedAccounts } from '@/lib/api/socialConnections';
import { accounts, actorId } from '../../tests/socialFixtures';

const selected = () => ({ flow_id: actorId, accounts: [{ ...accounts[0], publishing_enabled: false, profile_url: 'https://www.facebook.com/901' }] });
test('explicitly registered native capability survives selection while account publishing stays disabled', () => {
  const result = decodeSelectedAccounts(selected());
  expect(result.accounts[0].publishing_enabled).toBe(false);
  expect(result.accounts[0].capabilities.adapter_available).toBe(true);
});
test.each([true, 'false', null])('selection never accepts account publishing activation: %p', publishing_enabled => {
  expect(() => decodeSelectedAccounts({ ...selected(), accounts: [{ ...selected().accounts[0], publishing_enabled }] })).toThrow();
});
test.each(['true', 1, null])('selection refuses malformed adapter flag: %p', adapter_available => {
  const response = selected();
  expect(() => decodeSelectedAccounts({ ...response, accounts: [{ ...response.accounts[0], capabilities: { ...response.accounts[0].capabilities, adapter_available } }] })).toThrow();
});

jest.mock('@/lib/hooks/useSocial', () => ({ useSocialAccounts: jest.fn() }));
jest.mock('@/lib/hooks/useSocialConnections', () => ({ useMetaAccountHealth: () => ({}), useMetaConnectionStatus: () => ({ data: { available: false, access_mode: 'unverified', scopes: [], blockers: ['CONNECTIONS_DISABLED'] } }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: actorId } }) }));
import { render, screen } from '@testing-library/react';
import MetaAccounts from '@/components/admin/social/connections/MetaAccounts';
const { useSocialAccounts } = jest.requireMock('@/lib/hooks/useSocial');

test.each([true, false])('accounts reports adapter metadata without activating account publishing: %p', available => {
  useSocialAccounts.mockReturnValue({ data: [{ ...selected().accounts[0], capabilities: { ...selected().accounts[0].capabilities, adapter_available: available } }] });
  render(<MetaAccounts />);
  expect(screen.getByText(available ? 'Publishing disabled. Publishing adapter registered; delivery gates still apply.' : 'Publishing disabled. Publishing adapter unavailable.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Connect owned Meta accounts' })).toBeDisabled();
});
