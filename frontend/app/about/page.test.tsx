import { render, screen, within } from '@testing-library/react';
import AboutPage from './page';

let mockLanguage = 'en';
let mockFreshness: unknown;

jest.mock('@/lib/i18n/LangProvider', () => ({
  useLang: () => ({ lang: mockLanguage, t: (key: string) => key }),
}));
jest.mock('@/components/DataFreshnessBadge', () => ({
  useDataFreshness: () => mockFreshness,
}));

beforeEach(() => {
  mockLanguage = 'en';
  mockFreshness = { data: undefined };
});

it('presents supported practices, publishers and existing contact and policy destinations', () => {
  render(<AboutPage />);

  expect(screen.getByRole('heading', { level: 1, name: 'About AuditGava' })).toBeInTheDocument();
  expect(screen.getByText(/AuditGava operates independently of government/)).toBeInTheDocument();
  const practices = screen.getByRole('region', { name: 'How we work' });
  expect(within(practices).getAllByRole('listitem')).toHaveLength(3);
  expect(within(practices).getByText('Modelled figures say so')).toBeInTheDocument();

  const sources = screen.getByRole('region', { name: 'Sources' });
  expect(within(sources).getAllByRole('term').map((term) => term.textContent)).toEqual([
    'Central Bank of Kenya',
    'National Treasury',
    'Office of the Auditor-General',
    'Controller of Budget',
  ]);
  expect(within(sources).getByRole('link', { name: 'View all sources' })).toHaveAttribute('href', '/sources');

  expect(screen.getByRole('link', { name: 'auditgava@gmail.com' })).toHaveAttribute('href', 'mailto:auditgava@gmail.com');
  expect(screen.getByRole('link', { name: 'Privacy policy' })).toHaveAttribute('href', '/privacy');
  expect(screen.getByRole('link', { name: 'Terms of use' })).toHaveAttribute('href', '/terms');
});

it('renders uniquely matched periods in use and leaves out missing or ambiguous publisher periods', () => {
  mockFreshness = {
    data: {
      sources: [
        { source: 'CBK', covers_through: ' June 2026 ', last_checked: '2026-11-21' },
        { source: 'OAG', covers_through: 'FY 2025/26' },
        { source: 'OAG', covers_through: 'FY 2024/25' },
        { source: 'COB', covers_through: ' ' },
        { source: 'Treasury', last_checked: '2026-11-21' },
      ],
    },
  };

  render(<AboutPage />);

  const sources = screen.getByRole('region', { name: 'Sources' });
  expect(within(sources).getByText('Data in use covers through June 2026')).toBeInTheDocument();
  expect(within(sources).getAllByText(/Data in use covers through/)).toHaveLength(1);
  expect(within(sources).queryByText(/2026-11-21/)).toBeNull();
});

it('renders the About copy in Kiswahili', () => {
  mockLanguage = 'sw';

  render(<AboutPage />);

  expect(screen.getByRole('heading', { level: 1, name: 'Kuhusu AuditGava' })).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Jinsi tunavyofanya kazi' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Tazama vyanzo vyote' })).toHaveAttribute('href', '/sources');
});
