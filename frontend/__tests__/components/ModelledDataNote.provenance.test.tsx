/**
 * The standing amber note on the county pages must name the source of the
 * figures the reader is actually looking at.
 *
 * Its first clause read, unconditionally:
 *
 *   "County budget allocations are a modelled estimate — not official
 *    Controller of Budget figures — using the Commission on Revenue
 *    Allocation (CRA) equitable-share formula."
 *
 * County budgets now come from the Controller of Budget's County Budget
 * Implementation Review Report for all 47 counties, reconciling to the printed
 * 633,303.87m total. Baringo's page prints KES 9.54B off that parse under a
 * banner calling it a CRA model.
 *
 * Both kinds of period still exist — CBIRR-reported ones and CRA
 * equitable-share PROJECTION ones, which a reader reaches via ?fy= — so the
 * note is conditional on the provenance the API reports, not reworded.
 */
import ModelledDataNote from '@/components/ModelledDataNote';
import { LangProvider } from '@/lib/i18n/LangProvider';
import { MESSAGES } from '@/lib/i18n/messages';
import { render, screen } from '@testing-library/react';

const renderNote = (props: React.ComponentProps<typeof ModelledDataNote> = {}) =>
  render(
    <LangProvider>
      <ModelledDataNote {...props} />
    </LangProvider>
  );

const noteText = () => screen.getByRole('note').textContent ?? '';

/** The sentence that must not appear over Controller of Budget figures. */
const MODELLED_CLAIM = /modelled estimate/i;
const NOT_OFFICIAL_CLAIM = /not official Controller of Budget figures/i;

describe('ModelledDataNote — budget provenance', () => {
  it('does not call CBIRR figures a modelled estimate', () => {
    renderNote({ budgetSource: 'cob_cbirr' });
    const text = noteText();
    expect(text).not.toMatch(MODELLED_CLAIM);
    expect(text).not.toMatch(NOT_OFFICIAL_CLAIM);
  });

  it('credits the Controller of Budget for CBIRR figures', () => {
    renderNote({ budgetSource: 'cob_cbirr' });
    const text = noteText();
    expect(text).toMatch(/Controller of Budget/i);
    expect(text).toMatch(/Budget Implementation Review Report|CBIRR/i);
  });

  it('still calls a CRA projection a modelled estimate', () => {
    // Pointed the other way: a fix that just hardcodes the CBIRR wording is
    // the same defect, and would now overclaim official provenance.
    renderNote({ budgetSource: 'cra_model' });
    const text = noteText();
    expect(text).toMatch(MODELLED_CLAIM);
    expect(text).toMatch(/equitable-share/i);
  });

  it('keeps the clauses about the other figures in every case', () => {
    // Pending bills, county debt and audit findings have their own
    // provenance; switching the budget clause must not drop them.
    for (const budgetSource of ['cob_cbirr', 'cra_model', undefined] as const) {
      const { unmount } = renderNote({ budgetSource });
      const text = noteText();
      expect(text).toMatch(/pending bills/i);
      expect(text).toMatch(/Auditor-General/i);
      expect(text).toMatch(/dash/i);
      unmount();
    }
  });

  it('says nothing about budget provenance when no budget was published', () => {
    // Absence has no source. Defaulting to either label prints a provenance
    // note about a figure the page never showed.
    renderNote({ budgetSource: null });
    const text = noteText();
    expect(text).not.toMatch(MODELLED_CLAIM);
    expect(text).not.toMatch(/Controller of Budget/i);
    expect(text).toMatch(/Auditor-General/i);
  });

  // ── Mixed pages (list / compare) ────────────────────────────────────────

  it('accepts a list of counties and agrees when they all agree', () => {
    renderNote({ budgetSource: ['cob_cbirr', 'cob_cbirr', null] });
    expect(noteText()).not.toMatch(MODELLED_CLAIM);
    expect(noteText()).toMatch(/Controller of Budget/i);
  });

  it('does not claim one source for a page showing both', () => {
    renderNote({ budgetSource: ['cob_cbirr', 'cra_model'] });
    const text = noteText();
    expect(text).toMatch(/Controller of Budget/i);
    expect(text).toMatch(/equitable-share/i);
  });

  // ── Translations ────────────────────────────────────────────────────────

  it('carries every new clause in all three languages', () => {
    const keys = Object.keys(MESSAGES).filter((k) =>
      k.startsWith('counties.provenance.')
    );
    expect(keys.length).toBeGreaterThan(0);
    for (const key of keys) {
      const entry = (MESSAGES as any)[key];
      for (const lang of ['en', 'sw', 'plain']) {
        expect(typeof entry[lang]).toBe('string');
        expect(entry[lang].length).toBeGreaterThan(0);
      }
    }
  });
});
