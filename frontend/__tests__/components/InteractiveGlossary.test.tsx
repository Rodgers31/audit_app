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

// framer-motion → plain elements (jsdom can't animate)
jest.mock('framer-motion', () => ({
  motion: new Proxy(
    {},
    {
      get:
        () =>
        ({ children, ...props }: any) => {
          // drop framer-only props so React doesn't warn on the DOM node
          const { animate, initial, exit, transition, ...rest } = props;
          return <div {...rest}>{children}</div>;
        },
    }
  ),
  AnimatePresence: ({ children }: any) => <>{children}</>,
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

afterEach(() => jest.clearAllMocks());

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
