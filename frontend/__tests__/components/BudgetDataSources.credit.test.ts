/**
 * The budget page's standing source credit must describe what the page shows.
 *
 * The "Revenue by Source" entry in the Sources modal read:
 *
 *   "Tax revenue breakdown (PAYE, VAT, Corporation Tax, Excise Duty, Customs)
 *    from KRA annual performance press releases."
 *
 * It named five heads while the section renders six, and the sixth — "Other
 * Tax Revenue" — is this project's own subtraction, not a line in any KRA
 * release. The charted FY 2022/23 is back-computed from the FY 2023/24
 * release's growth rates and is likewise not stated by the cited document.
 *
 * So the one place on the page that made a provenance claim made it about
 * figures the cited source does not contain. These pin the corrected credit
 * to the properties that matter rather than to its exact wording.
 */
import { DATA_SOURCES } from '@/app/budget/dataSources';

const entry = () => {
  const found = DATA_SOURCES.find((s) => s.section === 'Revenue by Source');
  if (!found) throw new Error('Revenue by Source credit is missing entirely');
  return found;
};

/** Everything the modal puts in front of the reader for this entry. */
const creditText = () => {
  const { description, methodology } = entry();
  return [description, methodology ?? ''].join(' ');
};

describe('Revenue by Source credit', () => {
  it('discloses that the residual head is not a KRA-published line', () => {
    expect(creditText()).toMatch(/residual/i);
  });

  it('discloses that the earliest charted year is derived', () => {
    expect(creditText()).toMatch(/2022\/23/);
    expect(creditText()).toMatch(/derived|back-computed/i);
  });

  it('does not present the head list as the whole of what is shown', () => {
    // The old copy read "(PAYE, VAT, Corporation Tax, Excise Duty, Customs)
    // from KRA annual performance press releases" — a closed list of five
    // standing in for six rendered cards.
    const description = creditText();
    const namesFive =
      /\(PAYE[^)]*Customs\)\s*from KRA annual performance press releases\.?$/i.test(
        description.trim()
      );
    expect(namesFive).toBe(false);
  });

  it('still credits KRA for the heads KRA does publish', () => {
    expect(entry().authority).toMatch(/Kenya Revenue Authority/i);
    expect(creditText()).toMatch(/KRA/);
  });
});
