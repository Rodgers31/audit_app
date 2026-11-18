/**
 * Tests for InteractiveGlossary — the live-figure path (audit §2.7).
 *
 * The glossary's fiscal example magnitudes (GDP, budget, debt, equitable
 * share) are no longer hardcoded literals; they are fetched from
 * /learn/civic-figures and interpolated into each term's template. When the
 * API is unavailable, the dated last-known fallback is shown instead.
 *
 * Covers:
 *  - live figures resolve into the example text (trillion + billion paths)
 *  - the period (data year / fiscal year) is substituted in
 *  - a failed fetch degrades to the dated fallback, never a blank/zero
 */

import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ back: jest.fn() }),
}));

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href }: any) => <a href={href}>{children}</a>,
}));

jest.mock('@/lib/api/civic', () => ({ getCivicFigures: jest.fn() }));
import { getCivicFigures } from '@/lib/api/civic';
const mockGetCivicFigures = getCivicFigures as jest.MockedFunction<
  typeof getCivicFigures
>;

import InteractiveGlossary from '@/components/InteractiveGlossary';

function renderGlossary() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <InteractiveGlossary />
    </QueryClientProvider>
  );
}

const FIGURES = {
  status: 'success',
  data_source: 'database',
  figures: {
    nominal_gdp: {
      available: true,
      value: 16_224_478_000_000,
      unit: 'kes',
      period: '2024',
      source: 'World Bank / KNBS',
      as_of: '2024-12-31',
      data_quality: 'official',
    },
    equitable_share: {
      available: true,
      value: 405_000_000_000,
      unit: 'kes',
      period: 'FY2025/26',
      source: 'Division of Revenue Act / CRA',
      as_of: '2025-06-30',
      data_quality: 'official',
    },
  },
};

afterEach(() => {
  jest.clearAllMocks();
  window.history.replaceState(null, '', '/');
});

it('interpolates live GDP (trillion) and equitable share (billion) figures', async () => {
  mockGetCivicFigures.mockResolvedValue(FIGURES as any);
  renderGlossary();

  // Expand the GDP term, then assert the LIVE value + period appear.
  fireEvent.click(screen.getByText('Gross Domestic Product'));
  expect(
    await screen.findByText(
      /Kenya's nominal GDP was about KES 16\.22 trillion in 2024/
    )
  ).toBeInTheDocument();

  // Expand the Equitable Share term, assert the billion-path + fiscal year.
  fireEvent.click(screen.getByText('Equitable Share'));
  expect(
    await screen.findByText(
      /For FY2025\/26, counties were allocated about KES 405 billion/
    )
  ).toBeInTheDocument();
});

it('falls back to the dated example when the API fails', async () => {
  mockGetCivicFigures.mockRejectedValue(new Error('network down'));
  renderGlossary();

  fireEvent.click(screen.getByText('Gross Domestic Product'));

  // Dated last-known-good fallback — never a blank or fabricated current value.
  await waitFor(() =>
    expect(
      screen.getByText(
        /Kenya's nominal GDP was approximately KES 15\.0 trillion in 2023/
      )
    ).toBeInTheDocument()
  );
});


it('indexes the 15 actual terms, keeps search aliases and disables empty letters', () => {
  mockGetCivicFigures.mockResolvedValue({ status: 'success', data_source: 'empty', figures: {} });
  renderGlossary();
  expect(screen.getByText('15 terms across 6 themes')).toBeInTheDocument();
  const search = screen.getByRole('searchbox', { name: 'Search glossary' });
  expect(search).toHaveAttribute('placeholder', 'Search 15 terms');
  expect(screen.getByRole('button', { name: 'Z' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'A' }));
  expect(screen.getByRole('button', { name: 'Absorption rate' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Pending bills' })).not.toBeInTheDocument();

  fireEvent.change(search, { target: { value: 'buDget-execution-rate' } });
  expect(screen.getByRole('button', { name: 'Absorption rate' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'P' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Reset filters' }));
  expect(search).toHaveFocus();
  expect(screen.getByRole('button', { name: 'Pending bills' })).toBeInTheDocument();
});

it('keeps the projected basis and only links a supplied live-example receipt', async () => {
  mockGetCivicFigures.mockResolvedValue({
    ...FIGURES,
    figures: { ...FIGURES.figures, equitable_share: {
      ...FIGURES.figures.equitable_share, data_quality: 'projected',
      citation: { url: 'https://www.treasury.go.ke/source.pdf' },
    } },
  } as Awaited<ReturnType<typeof getCivicFigures>>);
  renderGlossary();
  fireEvent.click(screen.getByText('Equitable Share'));
  expect(await screen.findByText('FY2025/26 projection: about KES 405 billion.')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open source' })).toHaveAttribute('href', 'https://www.treasury.go.ke/source.pdf');
  expect(screen.queryByText(/counties were allocated about KES 405 billion/)).not.toBeInTheDocument();
});

it('keeps constitutional context separate from the definition source', () => {
  mockGetCivicFigures.mockResolvedValue({ status: 'success', data_source: 'empty', figures: {} });
  renderGlossary();
  expect(screen.getByRole('link', { name: /Constitutional context.*Article 229/ })).toHaveAttribute('href', '/learn?article=229');
  fireEvent.click(screen.getByRole('button', { name: 'Qualified opinion' }));
  expect(screen.getByRole('heading', { name: 'Definition source' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Office of the Auditor-General/ })).toHaveAttribute('href', expect.stringContaining('libraryir.parliament.go.ke'));
  expect(screen.getByRole('link', { name: 'Audit findings' })).toHaveAttribute('href', '/audits');
});
