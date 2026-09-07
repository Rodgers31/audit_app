/**
 * Creditor names must not render the source API's column padding.
 *
 * World Bank IDS pads its creditor labels to a fixed width with non-breaking
 * spaces, and the seeding writer stores them verbatim. Production serves — and
 * /debt renders, in the loans table and in the treemap drill-down — names like
 * "Multilateral (World Bank-IDA<25 NBSPs>)".
 *
 * The padding is INTERIOR, before the closing parenthesis, so `trim()` cannot
 * reach it even though JS `trim()` does remove U+00A0. The runs have to be
 * collapsed.
 *
 * Display only: the stored string is the join key
 * `reconcile_external_creditors` matches on, so nothing here writes back.
 *
 * Fixtures are the exact strings from GET /api/v1/debt/loans on 2026-09-06
 * (production, `5ff5fa9`) — 3 of the 47 rows carry padding.
 */

import { displayLenderName } from '@/lib/debt/lenderName';

const NBSP = ' ';

/** Verbatim from the live response. */
const LIVE = {
  ida: `Multilateral (World Bank-IDA${NBSP.repeat(25)})`,
  afdb: `Multilateral (African Dev. Bank${NBSP.repeat(9)})`,
  ibrd: `Multilateral (World Bank-IBRD${NBSP.repeat(25)})`,
};

describe('displayLenderName — the live padded names', () => {
  it('renders World Bank-IDA without its 25 non-breaking spaces', () => {
    expect(displayLenderName(LIVE.ida)).toBe('Multilateral (World Bank-IDA)');
  });

  it('renders African Dev. Bank without its padding', () => {
    expect(displayLenderName(LIVE.afdb)).toBe('Multilateral (African Dev. Bank)');
  });

  it('renders World Bank-IBRD without its padding', () => {
    expect(displayLenderName(LIVE.ibrd)).toBe('Multilateral (World Bank-IBRD)');
  });

  it('leaves no non-breaking space anywhere in the output', () => {
    for (const raw of Object.values(LIVE)) {
      expect(displayLenderName(raw)).not.toMatch(/[  -   　]/);
    }
  });

  it('would not have been fixed by trim() alone — the padding is interior', () => {
    // Guards the reason this helper exists: `trim()` removes U+00A0 but the
    // padding sits before the ')', so the naive fix leaves it untouched.
    expect(LIVE.ida.trim()).toBe(LIVE.ida);
    expect(displayLenderName(LIVE.ida)).not.toBe(LIVE.ida);
  });
});

describe('displayLenderName — leaves clean names alone', () => {
  it.each([
    'Eurobond 2024 (10-year)',
    'Treasury Bonds (Fixed & Floating)',
    'Bilateral (China Exim Bank)',
    'Central Bank of Kenya Advance',
  ])('passes %s through unchanged', (name) => {
    expect(displayLenderName(name)).toBe(name);
  });

  it('is idempotent', () => {
    const once = displayLenderName(LIVE.ida);
    expect(displayLenderName(once)).toBe(once);
  });

  it('does not mutate its input', () => {
    const raw = LIVE.afdb;
    displayLenderName(raw);
    expect(raw).toBe(`Multilateral (African Dev. Bank${NBSP.repeat(9)})`);
  });
});

describe('displayLenderName — other invisible padding', () => {
  it('collapses ordinary double spaces', () => {
    expect(displayLenderName('Multilateral  (IMF   )')).toBe('Multilateral (IMF)');
  });

  it('strips leading and trailing whitespace', () => {
    expect(displayLenderName(`${NBSP} Eurobond 2028 \t`)).toBe('Eurobond 2028');
  });

  it('removes zero-width characters that survive a PDF copy-paste', () => {
    expect(displayLenderName('Euro​bond﻿ 2032')).toBe('Eurobond 2032');
  });

  it('returns an empty string for an absent name rather than inventing one', () => {
    // An unnamed creditor is a gap in the data, not a creditor called
    // "Unknown". The caller decides what absence looks like.
    expect(displayLenderName(null)).toBe('');
    expect(displayLenderName(undefined)).toBe('');
    expect(displayLenderName(NBSP.repeat(4))).toBe('');
  });
});
