import GovernmentExplorer from '@/components/learn/GovernmentExplorer';
import { fireEvent, render, screen, within } from '@testing-library/react';

jest.mock('@/lib/i18n/LangProvider', () => ({ useLang: () => ({ lang: 'en' }) }));

test('shows full branch descriptions and operates one disclosure at a time', () => {
  render(<GovernmentExplorer />);
  const executive = screen.getByRole('button', { name: 'Executive Implements laws and runs the country' });
  const judiciary = screen.getByRole('button', { name: 'Judiciary Interprets the Constitution and settles disputes' });
  const president = screen.getByText('President', { exact: true });
  const supremeCourt = screen.getByText('Supreme Court', { exact: true });
  expect(executive).toHaveAttribute('aria-expanded', 'false');
  expect(president).not.toBeVisible();

  fireEvent.click(executive);
  expect(executive).toHaveAttribute('aria-expanded', 'true');
  expect(president).toBeVisible();

  fireEvent.click(judiciary);
  expect(executive).toHaveAttribute('aria-expanded', 'false');
  expect(president).not.toBeVisible();
  expect(judiciary).toHaveAttribute('aria-expanded', 'true');
  expect(supremeCourt).toBeVisible();
});

test('provides the confirmed Parliament destinations and lists county functions without a scoped spending source', () => {
  render(<GovernmentExplorer />);
  const budget = screen.getByRole('link', { name: 'Parliament’s budget line · FY 2026/27' });
  const href = new URL(budget.getAttribute('href')!);
  expect(href.hostname).toBe('newsite.treasury.go.ke');
  expect(decodeURIComponent(href.pathname)).toMatch(/FY 2026 2027 Programme Based Budget Book_Approved\.pdf$/);
  expect(href.hash).toBe('#page=10');
  expect(screen.getByRole('link', { name: 'Art. 95' })).toHaveAttribute('href', '/learn?article=95');

  const county = within(screen.getByRole('region', { name: 'County governments do' }));
  expect(county.getByText('Health services and ambulances')).toBeVisible();
  expect(county.getByText('Pre-primary education and childcare')).toBeVisible();
  expect(county.getByText('County roads and public transport')).toBeVisible();
  expect(county.queryByRole('link')).not.toBeInTheDocument();
});
