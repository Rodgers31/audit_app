/**
 * The revenue mix must say which of its figures KRA actually published.
 *
 * Six tax heads render as equal cards under one section credit reading
 * "Source: KRA Annual Performance". Two of the six are not KRA figures:
 *
 *  - "Other Tax Revenue" is a subtraction — the exchequer total less the
 *    identified heads — and rendered at KES 181B, 7.8% of the displayed mix,
 *    described as "Stamp duty, agricultural cess, minor taxes lumped
 *    together", which is not even what the row's own note says it covers;
 *  - FY 2022/23 is back-computed in every head, and is the leftmost bar of
 *    all six sparklines.
 *
 * The page's own idiom for this already exists a section above, on the
 * budget flow: "the two segments marked residual are computed balancing
 * items, not published lines". These pin the same standard here.
 *
 * The credit is asserted as a property of the rendered rows rather than as a
 * fixed string: whatever the section claims about its source has to follow
 * from what it is showing, so this keeps holding when the years move on.
 */
import RevenueMix, { type RevFy } from '@/components/budget/RevenueMix';
import { render, screen, within } from '@testing-library/react';
import React from 'react';

jest.mock('framer-motion', () => ({
  motion: new Proxy(
    {},
    {
      get:
        () =>
        ({ children, initial: _i, animate: _a, whileInView: _w, viewport: _v, transition: _t, ...props }: any) => (
          <div {...props}>{children}</div>
        ),
    }
  ),
}));

/* The shape /api/v1/budget/enhanced serves, with the FY 2022/23 and residual
   rows exactly as the fixture declares them. */
const PUBLISHED_NOTE = (fy: string, head: string, amt: string) =>
  `KRA Annual Performance ${fy}: ${head} collected KES ${amt}`;

const HEADS: [string, number, number, number][] = [
  // head, FY22/23 (derived), FY23/24 (published), FY24/25 (published)
  ['Customs & Import Duty', 754.4, 791.4, 879.3],
  ['PAYE', 495.2, 543.2, 561.0],
  ['VAT', 272.5, 314.2, 327.3],
  ['Corporation Tax', 265.2, 278.2, 304.8],
  ['Excise Duty', 68.1, 73.6, 69.4],
];

const RESIDUAL_NOTE =
  'Residual: Exchequer 2323B minus identified tax heads. Includes withholding tax, ' +
  'capital gains, stamp duty, betting taxes, digital economy taxes.';

const SERIES: RevFy[] = [
  {
    fiscal_year: 'FY 2022/23',
    sources: [
      ...HEADS.map(([head, a]) => ({
        revenue_type: head,
        category: 'tax',
        amount: a,
        basis: 'derived',
        basis_note: `Derived: FY 2023/24 ${head} grew 4.9%, implies prior year ~${a}B`,
      })),
      {
        revenue_type: 'Other Tax Revenue',
        category: 'tax',
        amount: 174.6,
        basis: 'residual',
        basis_note: 'Residual: Exchequer ~2030B minus identified tax heads.',
      },
    ],
  },
  {
    fiscal_year: 'FY 2023/24',
    sources: [
      ...HEADS.map(([head, , b]) => ({
        revenue_type: head,
        category: 'tax',
        amount: b,
        basis: 'published',
        basis_note: PUBLISHED_NOTE('FY 2023/24', head, `${b}B`),
      })),
      {
        revenue_type: 'Other Tax Revenue',
        category: 'tax',
        amount: 222.4,
        basis: 'residual',
        basis_note: RESIDUAL_NOTE,
      },
    ],
  },
  {
    fiscal_year: 'FY 2024/25',
    sources: [
      ...HEADS.map(([head, , , c]) => ({
        revenue_type: head,
        category: 'tax',
        amount: c,
        basis: 'published',
        basis_note: PUBLISHED_NOTE('FY 2024/25', head, `${c}B`),
      })),
      {
        revenue_type: 'Other Tax Revenue',
        category: 'tax',
        amount: 181.2,
        basis: 'residual',
        basis_note: RESIDUAL_NOTE,
      },
    ],
  },
];

const cardFor = (head: string) => {
  const heading = screen.getByText(head);
  const card = heading.closest('[data-revenue-card]');
  if (!card) throw new Error(`no card element found for ${head}`);
  return card as HTMLElement;
};

describe('RevenueMix — per-row provenance', () => {
  it('marks the residual head as a residual, not a measured stream', () => {
    render(<RevenueMix revenueBySource={SERIES} />);
    const card = cardFor('Other Tax Revenue');
    expect(card).toHaveAttribute('data-basis', 'residual');
    expect(within(card).getByText(/residual/i)).toBeInTheDocument();
  });

  it('does not mark the KRA-published heads', () => {
    render(<RevenueMix revenueBySource={SERIES} />);
    for (const [head] of HEADS) {
      const card = cardFor(head);
      expect(card).toHaveAttribute('data-basis', 'published');
      expect(within(card).queryByText(/residual|derived|projected/i)).toBeNull();
    }
  });

  it("describes the residual from its own note, not the hardcoded blurb", () => {
    // The blurb said "Stamp duty, agricultural cess, minor taxes lumped
    // together". The row says withholding tax, capital gains, betting and
    // digital-economy taxes, and says nothing about agricultural cess.
    render(<RevenueMix revenueBySource={SERIES} />);
    const card = cardFor('Other Tax Revenue');
    expect(card.textContent).toMatch(/withholding tax/i);
    expect(card.textContent).not.toMatch(/agricultural cess/i);
  });

  it('names the charted years that are not published figures', () => {
    // FY 2022/23 is the leftmost bar of every sparkline and every one of its
    // heads is back-computed. A reader looking at that bar must be told.
    render(<RevenueMix revenueBySource={SERIES} />);
    const note = screen.getByTestId('revenue-basis-footnote');
    expect(note.textContent).toMatch(/2022\/23/);
    expect(note.textContent).toMatch(/derived|back-computed/i);
    expect(note.textContent).not.toMatch(/2024\/25/);
  });

  it('marks the derived years inside the sparkline itself', () => {
    render(<RevenueMix revenueBySource={SERIES} />);
    const card = cardFor('PAYE');
    const bars = within(card).getAllByTestId('spark-bar');
    const byYear = Object.fromEntries(
      bars.map((b) => [b.getAttribute('data-year'), b.getAttribute('data-basis')])
    );
    expect(byYear['2022/23']).toBe('derived');
    expect(byYear['2023/24']).toBe('published');
    expect(byYear['2024/25']).toBe('published');
  });
});

describe('RevenueMix — the section credit follows the rows', () => {
  it('does not credit KRA for a mix that contains figures KRA did not publish', () => {
    render(<RevenueMix revenueBySource={SERIES} />);
    const credit = screen.getByTestId('revenue-section-source');
    // The mix shown includes the residual, so an unqualified KRA credit is a
    // claim about a figure KRA never published.
    expect(credit.textContent).toMatch(/KRA/);
    expect(credit.textContent).toMatch(/residual|partly|except/i);
  });

  it('credits KRA plainly when every displayed head is published', () => {
    const allPublished: RevFy[] = SERIES.map((fy) => ({
      ...fy,
      sources: fy.sources
        .filter((s) => s.revenue_type !== 'Other Tax Revenue')
        .map((s) => ({ ...s, basis: 'published' })),
    }));
    render(<RevenueMix revenueBySource={allPublished} />);
    const credit = screen.getByTestId('revenue-section-source');
    expect(credit.textContent).toMatch(/KRA/);
    expect(credit.textContent).not.toMatch(/residual|derived|projected/i);
  });

  it('keeps the editorial blurb when a row carries a note but no basis', () => {
    // The deploy window: rows seeded before `basis` existed still carry
    // `notes`. An undeclared basis is not evidence the figure is unpublished,
    // so the card must not swap its blurb for the raw provenance note — which
    // would print "KRA Annual Performance FY 2024/25: PAYE collected KES
    // 560.963B" where the reader expects a description of the tax, and would
    // put a KRA sourcing claim back on the page through the side door.
    const noBasis: RevFy[] = SERIES.map((fy) => ({
      ...fy,
      sources: fy.sources.map(({ basis: _b, ...rest }) => rest),
    }));
    render(<RevenueMix revenueBySource={noBasis} />);
    const card = cardFor('PAYE');
    expect(card.textContent).toMatch(/income tax withheld from salaries/i);
    expect(card.textContent).not.toMatch(/KRA Annual Performance/);
    expect(screen.queryByTestId('revenue-section-source')).toBeNull();
  });

  it('makes no source claim at all when no row declares one', () => {
    // Absence of provenance must read as absence, not as a KRA credit. This
    // is the same rule as never publishing a zero for an unmeasured figure.
    const undeclared: RevFy[] = SERIES.map((fy) => ({
      ...fy,
      sources: fy.sources.map(({ basis: _b, basis_note: _n, ...rest }) => rest),
    }));
    render(<RevenueMix revenueBySource={undeclared} />);
    expect(screen.queryByTestId('revenue-section-source')).toBeNull();
    expect(screen.queryByText(/KRA Annual Performance/)).toBeNull();
  });
});

describe('RevenueMix — nothing is dropped or zeroed to achieve this', () => {
  it('still renders all six heads and their amounts', () => {
    render(<RevenueMix revenueBySource={SERIES} />);
    for (const [head] of HEADS) expect(screen.getByText(head)).toBeInTheDocument();
    expect(screen.getByText('Other Tax Revenue')).toBeInTheDocument();
    // The residual keeps its real figure — labelled, not withheld or zeroed.
    expect(cardFor('Other Tax Revenue').textContent).toMatch(/181/);
  });

  it('keeps FY 2022/23 in the sparkline rather than withholding it', () => {
    render(<RevenueMix revenueBySource={SERIES} />);
    const bars = within(cardFor('VAT')).getAllByTestId('spark-bar');
    expect(bars.map((b) => b.getAttribute('data-year'))).toEqual([
      '2022/23',
      '2023/24',
      '2024/25',
    ]);
  });
});
