/**
 * A county with no census row must read as absent, not as "null residents".
 *
 * The API used to fall back to `entity.meta["metrics"]["population"]` —
 * bootstrap's copy of the same 2019 count, wrong for Mandera by 333,433 — and
 * then to 0 when even that was missing, which states that a county has no
 * residents. The stored copy is gone, so `demographics.population` is now null
 * where nobody has counted, and null has to survive to the screen as an em
 * dash.
 */
import { fmtPop } from '@/app/counties/[id]/shared';

describe('fmtPop', () => {
  it.each([null, undefined, NaN])('renders absence for %p', (v) => {
    expect(fmtPop(v as never)).toBe('—');
  });

  it('does not print the word null at a reader', () => {
    expect(fmtPop(null as never)).not.toMatch(/null|undefined|NaN/);
  });

  it('does not turn absence into zero', () => {
    expect(fmtPop(null as never)).not.toBe('0');
  });

  it.each([
    [867_457, '867K'],
    [4_397_073, '4.40M'],
    [666_763, '667K'],
  ])('formats %p as %p', (input, expected) => {
    expect(fmtPop(input)).toBe(expected);
  });

  it('still renders a real zero', () => {
    // Not a population any census reports, but a figure is a figure.
    expect(fmtPop(0)).toBe('0');
  });
});
