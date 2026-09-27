/**
 * Tests for lib/utils.ts
 *
 * Covers:
 *  formatCurrency  – KES with T / B / M / plain formatting
 *  formatPercentage – decimal + % suffix
 *  formatNumber     – thousands separator
 *  cn               – tailwind-merge wrapper
 */

import {
  cn,
  formatCurrency,
  formatKesWords,
  formatNumber,
  formatPercentage,
} from '@/lib/utils';

// ── formatCurrency ──────────────────────────────────────────────────────

describe('formatCurrency', () => {
  it('formats values in trillions', () => {
    expect(formatCurrency(1_500_000_000_000)).toMatch(/KES.*1\.5.*T/);
  });

  it('formats values in billions', () => {
    expect(formatCurrency(3_200_000_000)).toMatch(/KES.*3\.2.*B/);
  });

  it('formats values in millions', () => {
    expect(formatCurrency(45_600_000)).toMatch(/KES.*45\.6.*M/);
  });

  it('formats small values with commas', () => {
    const result = formatCurrency(12345);
    expect(result).toContain('KES');
    expect(result).toContain('12,345');
  });

  it('formats zero', () => {
    expect(formatCurrency(0)).toContain('KES');
  });

  it('handles exact boundary: 1 trillion', () => {
    expect(formatCurrency(1e12)).toMatch(/T/);
  });

  it('handles exact boundary: 1 billion', () => {
    expect(formatCurrency(1e9)).toMatch(/B/);
  });

  it('handles exact boundary: 1 million', () => {
    expect(formatCurrency(1e6)).toMatch(/M/);
  });
});

// ── formatPercentage ────────────────────────────────────────────────────

describe('formatPercentage', () => {
  it('formats a decimal percentage', () => {
    expect(formatPercentage(73.456)).toBe('73.5%');
  });

  it('formats zero', () => {
    expect(formatPercentage(0)).toBe('0.0%');
  });

  it('formats 100', () => {
    expect(formatPercentage(100)).toBe('100.0%');
  });

  it('rounds to one decimal place', () => {
    expect(formatPercentage(99.95)).toBe('100.0%');
  });
});

// ── formatNumber ────────────────────────────────────────────────────────

describe('formatNumber', () => {
  it('adds thousands separator', () => {
    expect(formatNumber(1234567)).toBe('1,234,567');
  });

  it('handles small numbers without separator', () => {
    expect(formatNumber(42)).toBe('42');
  });

  it('handles zero', () => {
    expect(formatNumber(0)).toBe('0');
  });
});

// ── cn (tailwind-merge wrapper) ─────────────────────────────────────────

describe('cn', () => {
  it('merges class names', () => {
    const result = cn('px-4', 'py-2');
    expect(result).toContain('px-4');
    expect(result).toContain('py-2');
  });

  it('deduplicates conflicting tailwind classes', () => {
    const result = cn('px-4', 'px-8');
    // tailwind-merge should keep only px-8
    expect(result).toBe('px-8');
  });

  it('handles conditional classes', () => {
    const isActive = true;
    const result = cn('base', isActive && 'active');
    expect(result).toContain('active');
  });

  it('filters falsy values', () => {
    const result = cn('base', false, null, undefined, 'extra');
    expect(result).toBe('base extra');
  });
});

describe('formatKesWords', () => {
  it('formats trillions to 2dp (no KES prefix)', () => {
    expect(formatKesWords(16_224_478_000_000)).toBe('16.22 trillion');
    expect(formatKesWords(4_190_000_000_000)).toBe('4.19 trillion');
  });

  it('formats billions as whole numbers', () => {
    expect(formatKesWords(405_000_000_000)).toBe('405 billion');
  });

  it('formats millions as whole numbers', () => {
    expect(formatKesWords(5_000_000)).toBe('5 million');
  });
});
