/**
 * The homepage must not ship 813 national audit findings to render four.
 *
 * #221 finding #4. `/` prefetched the whole `/api/v1/audits/federal` response
 * (885,732 bytes; 813 findings averaging ~1.1KB each) and dehydrated it into
 * the document, which is why the homepage is a 1.31MB HTML file. Its only
 * reader, `AuditReportsSection`, renders from the findings list exactly two
 * things: the four largest findings that state an amount, and whether the
 * list is empty. Everything else it shows comes from the response's summary
 * fields (`by_severity`, `top_ministries`, `total_findings`, …).
 *
 * These tests drive the real server component — `await HomePage()` — and read
 * the dehydrated state it hands to `HydrationBoundary`, which is what Next
 * serialises into the document. Three properties:
 *
 *   1. THE DEFECT — the audits entry in that state carries the full list.
 *   2. GUARD — the section hydrates from that entry with no loading state and
 *      no network call (the #222/#224 key-drift failure).
 *   3. GUARD — the section renders byte-identical markup from the homepage's
 *      entry and from the untrimmed response, across the shapes that matter
 *      (ties, unstated amounts, "KES 0", nothing stated, empty, short list).
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import {
  DehydratedState,
  HydrationBoundary,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import React from 'react';
import { renderToString } from 'react-dom/server';

import type { FederalAuditFinding, FederalAuditResponse } from '@/lib/api/audits';

/* ── fixtures ───────────────────────────────────────────────────────── */

const LONG_TEXT =
  'The Ministry did not provide supporting documents for expenditure recorded under ' +
  'compensation of employees and use of goods and services. '.repeat(10);

function finding(i: number, amount: number | null, label?: string): FederalAuditFinding {
  return {
    id: i,
    entity_name: `Ministry of Test ${i % 23}`,
    finding: `Finding ${i}: ${LONG_TEXT}`,
    severity: ['critical', 'significant', 'minor'][i % 3],
    amount_involved: label ?? (amount == null ? 'Not stated' : `KES ${amount.toLocaleString()}`),
    amount_numeric: amount,
    recommended_action: `Recommendation ${i}: reconcile and disclose.`,
    page_ref: `p. ${100 + i}`,
    source_url: 'https://www.oagkenya.go.ke/wp-content/uploads/2026/06/national-report.pdf',
  } as FederalAuditFinding;
}

function response(findings: FederalAuditFinding[]): FederalAuditResponse {
  return {
    report_title: 'Report of the Auditor-General on the National Government',
    auditor_general: 'Nancy Gathungu',
    fiscal_year: '2024/25',
    report_date: '2026-06-30',
    total_findings: findings.length,
    total_amount_questioned: null,
    withheld_findings: 3,
    total_amount_in_findings: 1_234_567_890,
    findings_with_amount: findings.filter((f) => f.amount_numeric != null).length,
    by_severity: { critical: 11, significant: 22, minor: 33 },
    // #233: the opinion now lives in the derived headline (null: none read).
    headline: null,
    findings,
    top_ministries: [
      { ministry: 'Ministry of Health', finding_count: 40 },
      { ministry: 'Ministry of Roads and Transport', finding_count: 31 },
    ],
    findings_reason: findings.length ? null : 'no_findings_recorded',
    next_expected: null,
    last_updated: '2026-09-20',
  };
}

/**
 * The production shape: 813 findings. Most state no amount, some say
 * "KES 0", and the largest amounts include a three-way tie so the fixture
 * pins the order a stable sort gives, not just the set.
 */
const FULL = response(
  Array.from({ length: 813 }, (_, i) => {
    if (i % 4 === 0) return finding(i, null);
    if (i % 4 === 1) return finding(i, 0, 'KES 0');
    if (i === 402 || i === 406 || i === 410) return finding(i, 9_000_000_000); // tie at the top
    return finding(i, (i * 7919) % 5_000_000_000);
  })
);

const SHAPES: Record<string, FederalAuditResponse> = {
  'production shape (813 findings, ties, nulls, KES 0)': FULL,
  'findings exist but none states an amount': response(
    Array.from({ length: 40 }, (_, i) => finding(i, i % 2 ? null : 0, i % 2 ? undefined : 'KES 0'))
  ),
  'no findings at all': response([]),
  'fewer stated findings than the section shows': response([
    finding(1, 5e6),
    finding(2, null),
    finding(3, 7e6),
  ]),
};

// jsdom ships no IntersectionObserver, and the section's `whileInView`
// animation constructs one on mount.
(global as unknown as { IntersectionObserver: unknown }).IntersectionObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
};

/** jsdom has no structuredClone; the fixtures are plain JSON. */
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

/* ── harness ────────────────────────────────────────────────────────── */

const mockGetFederalAudits = jest.fn();

jest.mock('@/lib/api/audits', () => ({
  ...jest.requireActual('@/lib/api/audits'),
  getFederalAudits: () => mockGetFederalAudits(),
}));
// The homepage's other six prefetches are not under test; failing them fast
// keeps them out of the dehydrated state (only successful queries are).
jest.mock('@/lib/api/budget', () => ({
  ...jest.requireActual('@/lib/api/budget'),
  getNationalBudgetSummary: () => Promise.reject(new Error('not under test')),
}));
jest.mock('@/lib/api/counties', () => ({
  ...jest.requireActual('@/lib/api/counties'),
  getCounties: () => Promise.reject(new Error('not under test')),
}));
jest.mock('@/lib/api/debt', () => ({
  ...jest.requireActual('@/lib/api/debt'),
  getDebtTimeline: () => Promise.reject(new Error('not under test')),
  getNationalDebtOverview: () => Promise.reject(new Error('not under test')),
  getNationalLoans: () => Promise.reject(new Error('not under test')),
}));
jest.mock('@/lib/api/fiscal', () => ({
  ...jest.requireActual('@/lib/api/fiscal'),
  getFiscalSummary: () => Promise.reject(new Error('not under test')),
}));
// A fresh client per server render, as on a real server. Under jsdom the real
// factory would hand back the browser singleton.
jest.mock('@/lib/react-query/getQueryClient', () => {
  const { QueryClient: QC } = jest.requireActual('@tanstack/react-query');
  return { getQueryClient: () => new QC({ defaultOptions: { queries: { retry: false } } }) };
});

// The page's client tree is not under test — only the state the server hands
// it — and it pulls in the Supabase client at import time.
jest.mock('@/app/HomeDashboardClient', () => ({ __esModule: true, default: () => null }));

// eslint-disable-next-line import/first
import HomePage from '@/app/page';
// eslint-disable-next-line import/first
import AuditReportsSection from '@/components/dashboard/AuditReportsSection';

/** Run the real server component and return the state it dehydrates. */
async function homepageState(data: FederalAuditResponse): Promise<DehydratedState> {
  mockGetFederalAudits.mockResolvedValue(clone(data));
  const element = (await HomePage()) as React.ReactElement<{ state: DehydratedState }>;
  mockGetFederalAudits.mockClear();
  return element.props.state;
}

/** The dehydrated entry the audits prefetch produced. */
function auditsEntry(state: DehydratedState) {
  const entries = state.queries.filter((q) => q.queryKey[0] === 'audits');
  expect(entries).toHaveLength(1);
  return entries[0];
}

function clientFrom() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 15 * 60 * 1000 } },
  });
}

function Section({ client, state }: { client: QueryClient; state?: DehydratedState }) {
  return (
    <QueryClientProvider client={client}>
      <HydrationBoundary state={state}>
        <AuditReportsSection />
      </HydrationBoundary>
    </QueryClientProvider>
  );
}

/* ── 1. the defect ──────────────────────────────────────────────────── */

describe('homepage audits prefetch — what goes into the document', () => {
  it('carries only the findings the section can render, not all 813', async () => {
    const entry = auditsEntry(await homepageState(FULL));
    const data = entry.state.data as FederalAuditResponse;
    expect(data.findings.length).toBeLessThanOrEqual(4);
  });

  it('serialises to a few KB rather than ~1MB', async () => {
    const entry = auditsEntry(await homepageState(FULL));
    const bytes = JSON.stringify(entry.state.data).length;
    expect(JSON.stringify(FULL).length).toBeGreaterThan(750_000); // production-sized (live: 885,732 B)
    expect(bytes).toBeLessThan(20_000);
  });

  it('keeps every summary field the section reads, untouched', async () => {
    const data = auditsEntry(await homepageState(FULL)).state.data as FederalAuditResponse;
    const { findings: _f, ...summary } = data;
    const { findings: _g, ...fullSummary } = FULL;
    expect(summary).toEqual(fullSummary);
  });
});

/* ── 2. guard: the section reads what the homepage wrote ────────────── */

describe('AuditReportsSection hydrates from the homepage prefetch', () => {
  it('renders with no loading state and no network call', async () => {
    const state = await homepageState(FULL);
    render(<Section client={clientFrom()} state={state} />);
    expect(screen.getByText(/Report of the Auditor-General|National Government/i)).toBeInTheDocument();
    expect(mockGetFederalAudits).not.toHaveBeenCalled();
  });
});

/* ── 3. guard: nothing the reader sees changes ──────────────────────── */

describe('AuditReportsSection renders the same markup from the trimmed payload', () => {
  it.each(Object.entries(SHAPES))('%s', async (_label, data) => {
    const state = await homepageState(data);
    const trimmed = renderToString(<Section client={clientFrom()} state={state} />);

    // Reference: the untrimmed response under the very key the section just
    // read (test 2 establishes that it reads the homepage's key).
    const reference = clientFrom();
    reference.setQueryData(auditsEntry(state).queryKey, clone(data));
    const full = renderToString(<Section client={reference} />);

    expect(trimmed).toEqual(full);
    // And the reference really did render findings where there are some, so
    // equality is not two empty panels agreeing.
    const largest = data.findings
      .filter((f) => f.amount_involved !== 'KES 0' && f.amount_numeric != null)
      .sort((a, b) => (b.amount_numeric as number) - (a.amount_numeric as number))[0];
    if (largest) expect(full).toContain(`Finding ${largest.id}:`);
  });
});
