import { describeMaturities, type LadderBucket } from '@/components/debt/MaturityLadder.data';

function ladder(rows: Array<[number, number | null]>, asOf?: string) {
  return describeMaturities({
    status: 'success',
    source: { as_of: asOf },
    ladder: rows.map(([year, face_value]): LadderBucket => ({ year, face_value, instruments: 1 })),
  });
}

describe('Treasury bond maturity takeaways', () => {
  it('uses the five complete calendar years after the source snapshot and finds the largest non-past value', () => {
    const model = ladder([[2035, 60], [2027, 999], [2029, 12], [2030, 15], [2031, 0], [2032, 5], [2033, 21], [2028, 29]], '2028-10-11');
    expect(model.range).toEqual({ start: 2029, end: 2033 });
    expect(model.windowAmount).toBe(53);
    expect(model.windowComplete).toBe(true);
    expect(model.peakAmount).toBe(60);
    expect(model.peaks).toEqual([2035]);
    expect(model.rows[0]).toMatchObject({ year: 2027, amount: 999, past: true });
    expect(model.rows[1]).toMatchObject({ year: 2028, amount: 29, past: false });
    expect(model.maxBar).toBe(999);
  });

  it('retains signed amounts and distinguishes a reported zero from missing years or amounts', () => {
    const model = ladder([[2030, -30], [2031, null], [2033, 0]], '2028-10-11');
    expect(model.rows.map(row => row.amount)).toEqual([-30, null, 0]);
    expect(model.windowAmount).toBe(0);
    expect(model.windowComplete).toBe(false);
    expect(model.peaks).toEqual([]);
    expect(model.peakAmount).toBeNull();
    expect(model.maxBar).toBe(0);
  });

  it.each([undefined, '2029', '2029-02-29', '2028-10-11T00:00:00Z'])(
    'leaves the horizon unavailable for an absent or invalid source date (%s)',
    asOf => {
      const model = ladder([[2027, 20], [2030, 80], [2031, 80]], asOf);
      expect(model.date).toBeNull();
      expect(model.range).toBeNull();
      expect(model.windowAmount).toBeNull();
      expect(model.peaks).toEqual([2030, 2031]);
    },
  );

  it('distinguishes no usable near-term amount, no future peak and an empty ladder', () => {
    const pastOnly = ladder([[2027, 999]], '2028-10-11');
    expect(pastOnly.range).toEqual({ start: 2029, end: 2033 });
    expect(pastOnly.windowAmount).toBeNull();
    expect(pastOnly.peakAmount).toBeNull();
    expect(ladder([], '2028-10-11').rows).toEqual([]);
  });
});
