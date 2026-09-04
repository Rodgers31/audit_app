/**
 * Round-number-estimate detection on the homepage debt chart
 * (credibility audit F13).
 *
 * The 2013–2021 rows in /debt/timeline are round hundreds of billions across
 * external, domestic AND total at once. The homepage derived "4.0× since 2013"
 * and "From 58.4% in 2013" from the 2013 row, so both headline claims about
 * Kenya's debt trajectory rested on an invented base — and understated the
 * real rise, since actual 2013 debt was well below the 3.1T the fixture holds.
 *
 * These pin the detector in both directions. If it can only say "yes", it is
 * not a detector.
 */
import { isRoundNumberEstimate } from '@/components/dashboard/NationalDebtCard';

// Billions, exactly as they arrive from GET /debt/timeline on 2026-09-03.
const FIXTURE_YEARS = [
  { year: 2013, external: 1500, domestic: 1600, total: 3100 },
  { year: 2014, external: 1700, domestic: 1900, total: 3600 },
  { year: 2015, external: 2100, domestic: 2200, total: 4300 },
  { year: 2016, external: 2500, domestic: 2500, total: 5000 },
  { year: 2017, external: 2700, domestic: 2700, total: 5400 },
  { year: 2018, external: 2900, domestic: 2900, total: 5800 },
  { year: 2019, external: 3200, domestic: 3300, total: 6500 },
  { year: 2020, external: 3600, domestic: 3600, total: 7200 },
  { year: 2021, external: 3900, domestic: 4300, total: 8200 },
];

// The CBK Statistical Bulletin values applied by the 2026-08-29 correction.
const SOURCED_YEARS = [
  { year: 2022, external: 4673.1441, domestic: 4472.8385, total: 9145.9826 },
  { year: 2023, external: 6089.585, domestic: 5050.1085, total: 11139.6935 },
  { year: 2024, external: 5057.0058, domestic: 5868.2732, total: 10925.2789 },
  { year: 2025, external: 5461.9657, domestic: 6837.5107, total: 12299.4764 },
];

describe('isRoundNumberEstimate', () => {
  it.each(FIXTURE_YEARS)('flags the modelled year $year', (row) => {
    expect(isRoundNumberEstimate(row)).toBe(true);
  });

  it.each(SOURCED_YEARS)('does not flag the sourced year $year', (row) => {
    expect(isRoundNumberEstimate(row)).toBe(false);
  });

  it('needs all three components to be round, not just the total', () => {
    // A real reading whose total happens to land on 100B must not be flagged.
    expect(
      isRoundNumberEstimate({ external: 4673.1441, domestic: 4426.8559, total: 9100 })
    ).toBe(false);
  });

  it('does not flag zeroes or absent rows', () => {
    expect(isRoundNumberEstimate({ external: 0, domestic: 0, total: 0 })).toBe(false);
  });

  it('anchors growth on the first sourced year, not the first year', () => {
    const rows = [...FIXTURE_YEARS, ...SOURCED_YEARS];
    const firstSourced = rows.find((r) => !isRoundNumberEstimate(r));
    const last = rows[rows.length - 1];
    expect(firstSourced?.year).toBe(2022);

    // What the page publishes now, and what it used to publish.
    const honest = last.total / firstSourced!.total;
    const previous = last.total / rows[0].total;
    expect(honest).toBeCloseTo(1.34, 2);
    expect(previous).toBeCloseTo(3.97, 2);
    // The invented base did not merely mislead — it flattered the trend by
    // starting from a number larger than Kenya's actual 2013 debt.
    expect(previous).toBeGreaterThan(honest);
  });
});
