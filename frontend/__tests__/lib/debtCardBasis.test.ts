import { gdpRatioComparison } from '@/lib/debt/debtCardBasis';

describe('gdpRatioComparison', () => {
  const timelineBase = { gdpRatio: 67.8, year: 2022 };

  it('withholds the comparison when the displayed ratio is the IMF measure', () => {
    // 69.3% is IMF general government; 67.8% is CBK total / World Bank GDP.
    // "From 67.8% in 2022" would assert a movement along one series.
    expect(gdpRatioComparison(69.3, timelineBase)).toBeNull();
  });

  it('allows the comparison when both sides are the timeline basis', () => {
    expect(gdpRatioComparison(null, timelineBase)).toEqual({ pct: 67.8, year: 2022 });
    expect(gdpRatioComparison(undefined, timelineBase)).toEqual({ pct: 67.8, year: 2022 });
  });

  it('withholds when there is no sourced base to compare against', () => {
    expect(gdpRatioComparison(null, null)).toBeNull();
    expect(gdpRatioComparison(null, { gdpRatio: null, year: 2022 })).toBeNull();
    expect(gdpRatioComparison(null, { gdpRatio: 67.8, year: null })).toBeNull();
  });

  it('does not treat a zero ratio as absent', () => {
    expect(gdpRatioComparison(null, { gdpRatio: 0, year: 2013 })).toEqual({
      pct: 0,
      year: 2013,
    });
  });
});
