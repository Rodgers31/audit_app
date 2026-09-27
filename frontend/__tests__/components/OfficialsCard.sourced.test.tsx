/**
 * The county officials card shows only names a publisher supplied (#231).
 *
 * It used to read party, term, deputy governor, CEC Finance, speaker and
 * website from `lib/data/county-officials.ts`, typed in for the 2022 cycle.
 * For Meru, production served the Council of Governors' governor, Isaac
 * Mutuma M'ethingia, next to his impeached predecessor's "Independent · since
 * 2022", and listed "Isaac Mutuma" again as DEPUTY. The Council gives the
 * deputy as Linda Kiome.
 */
import '@testing-library/jest-dom';
import { render, screen, within } from '@testing-library/react';
import React from 'react';

import OverviewTab from '@/app/counties/[id]/tabs/OverviewTab';
import { LangProvider } from '@/lib/i18n/LangProvider';
import type { CountyComprehensive } from '@/types';

import MERU_PROD from '../fixtures/meru-comprehensive.json';

const COG = 'https://cog.go.ke/current-governors/';
const COG_DEPUTIES = 'https://cog.go.ke/current-deputy-governors/';

/**
 * Meru's real payload from production, fetched 2026-09-26 (before #231, so
 * it has no deputy or source fields yet), plus what the #231 API adds.
 */
function meru(overrides: Record<string, unknown> = {}): CountyComprehensive {
  return {
    ...MERU_PROD,
    deputy_governor: 'Linda Kiome',
    officials_source: {
      governor: { publisher: 'Council of Governors', source_url: COG, fetched_at: '2026-09-26T03:00:00+00:00' },
      deputy_governor: {
        publisher: 'Council of Governors',
        source_url: COG_DEPUTIES,
        fetched_at: '2026-09-26T03:00:00+00:00',
      },
    },
    ...overrides,
  } as unknown as CountyComprehensive;
}

function officialsCard() {
  render(
    <LangProvider>
      <OverviewTab data={meru()} />
    </LangProvider>
  );
  const heading = screen.getByText('Who Runs This County');
  // The card is the heading's nearest bordered container.
  return heading.closest('div.rounded-xl') as HTMLElement;
}

function role(card: HTMLElement, title: string): string {
  const label = within(card).getByText(title);
  return (label.parentElement as HTMLElement).textContent ?? '';
}

describe('county officials card — sourced names only (#231)', () => {
  it('shows the deputy the Council of Governors lists, not a typed-in one', () => {
    const card = officialsCard();
    expect(role(card, 'Deputy Governor')).toContain('Linda Kiome');
    expect(role(card, 'Deputy Governor')).not.toContain('Mutuma');
  });

  it('does not attach a party or a term that no publisher supplied', () => {
    const card = officialsCard();
    const gov = role(card, 'Governor');
    expect(gov).toContain('Isaac Mutuma M’ethingia');
    expect(gov).not.toMatch(/Independent|since 20\d\d/i);
  });

  it('has no CEC Finance or Speaker rows, and no typed-in website', () => {
    const card = officialsCard();
    expect(within(card).queryByText('CEC — Finance')).toBeNull();
    expect(within(card).queryByText('Assembly Speaker')).toBeNull();
    expect(card.querySelector('a[href*="meru.go.ke"]')).toBeNull();
  });

  it('names the publisher and links to its page', () => {
    const card = officialsCard();
    const links = Array.from(card.querySelectorAll('a')).map((a) => a.getAttribute('href'));
    expect(links).toEqual(expect.arrayContaining([COG, COG_DEPUTIES]));
    expect(card.textContent).toContain('Council of Governors');
  });
});
