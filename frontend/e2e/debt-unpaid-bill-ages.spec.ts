import { expect, test } from '@playwright/test';
import { registerApiMocks } from './utils/mockApi';

const ageNames = ['Under one year', '1-2 years', '2-3 years', 'Over 3 years'];
const counties = [
  'Baringo', 'Bomet', 'Bungoma', 'Busia', 'Elgeyo-Marakwet', 'Embu', 'Garissa', 'Homa Bay', 'Isiolo',
  'Kajiado', 'Kakamega', 'Kericho', 'Kiambu', 'Kilifi', 'Kirinyaga', 'Kisii', 'Kisumu', 'Kitui',
  'Kwale', 'Laikipia', 'Lamu', 'Machakos', 'Makueni', 'Mandera', 'Marsabit', 'Meru', 'Migori',
  'Mombasa', 'Murang’a', 'Nairobi', 'Nakuru', 'Nandi', 'Narok', 'Nyamira', 'Nyandarua', 'Nyeri',
  'Samburu', 'Siaya', 'Taita-Taveta', 'Tana River', 'Tharaka-Nithi', 'Trans Nzoia', 'Turkana',
  'Uasin Gishu', 'Vihiga', 'Wajir', 'West Pokot',
];

function observation(scope: 'county_assembly' | 'county_executive', amounts: number[]) {
  const assembly = scope === 'county_assembly';
  return {
    version: assembly ? 2 : 1, scope, status: 'qualified', absent_reason: null,
    as_at: '2026-06-30', unit: 'KES', currency: 'KES', complete_total: null,
    artifact_sha256: 'a'.repeat(64), extraction_id: 3,
    source_url: 'https://cob.go.ke/synthetic-age-proof.pdf',
    publisher: 'Controller of Budget',
    table: assembly ? 'Table 2.12' : 'Table 2.11', page: assembly ? 55 : 54,
    chart_supported: !assembly,
    reported_total: amounts.reduce((sum, amount) => sum + amount, 0) + (assembly ? 100_000 : 0),
    buckets: ageNames.map((bucket, index) => ({ bucket, amount: amounts[index], raw_value: String(amounts[index]), absent_reason: null })),
    reader_notes: [{ code: assembly ? 'bands_differ_from_printed_total' : 'reported_executive_population_only' }],
    coverage: {
      expected_counties: 47, reported_counties: assembly ? 47 : 46, missing_counties: assembly ? [] : ['Nandi'],
      counties_with_all_bands: assembly ? 36 : 41, missing_band_counties: counties.slice(0, assembly ? 11 : 6),
      qualified_counties: ['Bomet'], complete: false,
    },
  };
}

test.use({ hasTouch: true });

test('mobile bill ages preserve executive readout and separately disclose assembly and unsupported populations', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 860 });
  await page.clock.setFixedTime(new Date(Date.now() + 2 * 60 * 60 * 1000));
  await registerApiMocks(page);
  await page.route('**/api/v1/pending-bills', route => route.fulfill({
    json: { status: 'success', summary: { total_pending: null, national_total: 100e9, record_count: 1 } },
  }));
  await page.route('**/api/v1/pending-bills/summary', route => route.fulfill({
    json: {
      total_pending_amount: null,
      aging_observations: {
        county_executive: observation('county_executive', [41e9, 25e9, 0, 61.25e9]),
        county_assembly: observation('county_assembly', [2e9, 1.5e9, 0.7e9, 1.35e9]),
      },
    },
  }));
  await page.goto('/debt');

  const region = page.getByRole('region', { name: 'How long bills have gone unpaid' });
  const chart = region.getByRole('group', { name: 'County executive bills by age' });
  const oldest = chart.getByRole('button', { name: 'Over 3 years 61.3B' });
  await expect(oldest).toBeVisible();
  await expect(oldest).toHaveAccessibleDescription('KES 61,250,000,000');
  await oldest.tap();
  await expect(oldest).toHaveAttribute('aria-pressed', 'true');
  await expect(region.getByText('Over 3 years · KES 61,250,000,000', { exact: true })).toBeVisible();
  await expect(chart.locator('[data-signal=alarm]')).toHaveAttribute('data-age-bar', 'Over 3 years');
  await expect(chart.getByRole('button', { name: '2–3 years 0' })).toHaveAccessibleDescription('KES 0');

  await region.getByText('Read chart data', { exact: true }).press('Space');
  await expect(region.getByRole('table')).toContainText('KES 61,250,000,000');
  const source = region.getByRole('link', { name: /Table 2.11, PDF p.54/ });
  await expect(source).toHaveAttribute('href', 'https://cob.go.ke/synthetic-age-proof.pdf');
  const notes = region.getByRole('button', { name: 'Coverage and source notes' });
  await notes.press('Enter');
  const sheet = page.getByRole('dialog', { name: 'Coverage and source notes', exact: true });
  await expect(sheet).toContainText('Missing: Nandi.');
  await page.keyboard.press('Escape');
  await expect(notes).toBeFocused();

  const scope = region.getByRole('combobox', { name: 'Whose bills' });
  await scope.selectOption('county_assembly');
  await expect(region.getByText(/age bands and printed total differ/)).toBeVisible();
  await expect(region.getByRole('table')).toContainText('KES 1,350,000,000');
  await expect(region.getByRole('table')).toContainText('KES 5,550,100,000');
  await expect(region.getByRole('link', { name: /Table 2.12, PDF p.55/ })).toBeVisible();
  await expect(region.getByRole('group', { name: /bills by age/ })).toHaveCount(0);
  for (const unsupported of ['national', 'combined']) {
    await scope.selectOption(unsupported);
    await expect(region.getByText('Age of these bills not published', { exact: true })).toBeVisible();
    await expect(region.getByRole('table')).toHaveCount(0);
    await expect(region.getByRole('group', { name: /bills by age/ })).toHaveCount(0);
  }
  await scope.selectOption('county_executive');
  await expect(oldest).toHaveAttribute('aria-pressed', 'false');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
});
