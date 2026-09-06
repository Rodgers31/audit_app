/**
 * A county nobody has counted must read as absent on its own page.
 *
 * `/api/v1/counties/{id}/comprehensive` used to answer this in three
 * descending shades of confidence: the census row if there was one, else
 * bootstrap's un-sourced copy of it out of `entity.meta`, else the number 0.
 * The endpoint now serves the census row or `null`, and `null` has to survive
 * to the screen — as an em dash, not as the literal word "null", which is what
 * `String(null)` in the old `fmtPop` would have printed at a reader.
 *
 * All 47 counties have a KNBS 2019 census row, so this is not reachable in
 * production today. It is pinned because the path is walked the day an
 * extractor drops a county.
 */
import { fmtPop } from '@/app/counties/[id]/shared';

describe('fmtPop', () => {
  it.each([null, undefined, NaN])('renders absence for %p', (v) => {
    expect(fmtPop(v as never)).toBe('—');
  });

  it('never prints the word "null" at a reader', () => {
    expect(fmtPop(null as never)).not.toContain('null');
  });

  it('does not turn absence into a population of zero', () => {
    expect(fmtPop(null as never)).not.toContain('0');
  });

  it('still renders a real zero as a figure', () => {
    // No county reports this, but a publisher who did would be saying
    // something, and it is not ours to hide.
    expect(fmtPop(0)).toBe('0');
  });

  it.each([
    [4_397_073, '4.40M'],
    [866_820, '867K'],
    [143_920, '144K'],
    [812, '812'],
  ])('formats %p as %p', (input, expected) => {
    expect(fmtPop(input)).toBe(expected);
  });
});
