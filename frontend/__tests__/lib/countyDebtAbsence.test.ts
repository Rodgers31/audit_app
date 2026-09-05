/**
 * A county with no published debt figure must read as absent.
 *
 * 43 of the 47 counties have no sourced debt row: every one used to carry a
 * "County Government Debt" figure equal to a flat 15% of a budget that was
 * itself population x KSh 4,500. With those gone the API returns null, and
 * null has to survive all the way to the screen — as an em dash, not as
 * "KES 0", and not as a crash.
 */
import { fmtKES, pct } from '@/app/counties/[id]/shared';

describe('fmtKES', () => {
  it.each([null, undefined, NaN])('renders absence for %p', (v) => {
    expect(fmtKES(v as never)).toBe('—');
  });

  it('does not turn absence into zero', () => {
    expect(fmtKES(null as never)).not.toContain('0');
  });

  it('still renders a real zero as a figure', () => {
    // A publisher can report zero, and that is a number someone stands behind.
    expect(fmtKES(0)).toBe('KES 0');
  });

  it.each([
    [13_114_825_391, 'KES 13.11B'],
    [3_020_129, 'KES 3.0M'],
    [4_500, 'KES 5K'],
  ])('formats %p as %p', (input, expected) => {
    expect(fmtKES(input)).toBe(expected);
  });
});

describe('pct', () => {
  it.each([null, undefined, NaN])('renders absence for %p', (v) => {
    expect(pct(v as never)).toBe('—');
  });

  it('does not turn an absent ratio into 0.0%', () => {
    expect(pct(null as never)).not.toBe('0.0%');
  });

  it('still renders a real zero ratio', () => {
    expect(pct(0)).toBe('0.0%');
  });

  it('formats a ratio', () => {
    expect(pct(15.25)).toBe('15.3%');
  });
});
