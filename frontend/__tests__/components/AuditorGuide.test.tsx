import { render, screen, within } from '@testing-library/react';
import AuditorGuide from '@/app/learn/auditor-general-guide/AuditorGuide';
import { AUDITOR_GUIDE_STEPS, auditorGuideHref, findAuditorGuideStep } from '@/app/learn/auditor-general-guide/auditorGuideData';
import { LangProvider } from '@/lib/i18n/LangProvider';

jest.mock('next/navigation', () => ({
  useRouter: () => ({ back: jest.fn() }),
  usePathname: () => '/learn/auditor-general-guide',
}));

describe('Auditor-General guided path', () => {
  it('resolves named steps and defaults missing, unknown and repeated values to the first step', () => {
    for (const step of AUDITOR_GUIDE_STEPS) {
      expect(findAuditorGuideStep(step.key)).toBe(step);
      expect(auditorGuideHref(step)).toBe(`/learn/auditor-general-guide?step=${step.key}`);
    }
    for (const invalid of [undefined, 'missing', '4', ['reporting', 'opinion']]) {
      expect(findAuditorGuideStep(invalid).key).toBe('office');
    }
  });

  it.each([
    { key: 'office', figure: '8 years', source: /229\(1\) and \(3\)/, page: '#page=135' },
    { key: 'reporting', figure: '6 months', source: /229\(4\)/, page: '#page=135' },
    { key: 'opinion', figure: '44 of 47', source: /table 8, p\. 21/, page: '#page=35' },
    { key: 'action', figure: '3 months', source: /229\(7\) and \(8\)/, page: '#page=136' },
  ])('renders the qualified measure and exact source for $key', ({ key, figure, source, page }) => {
    render(<LangProvider><AuditorGuide step={findAuditorGuideStep(key)} /></LangProvider>);
    const card = within(screen.getByRole('article'));
    expect(card.getAllByRole('definition')).toHaveLength(1);
    expect(card.getByRole('definition')).toHaveTextContent(figure);
    expect(card.getByRole('link', { name: source }).getAttribute('href')).toContain(page);
    expect(card.getByRole('link', { name: 'Read Article 229' })).toHaveAttribute('href', '/learn?article=229');
  });

  it('labels the reporting period and distinguishes the opinion from allegations', () => {
    render(<LangProvider><AuditorGuide step={findAuditorGuideStep('opinion')} /></LangProvider>);
    const card = within(screen.getByRole('article'));
    expect(card.getByText('Financial year ended 30 June 2025')).toBeVisible();
    expect(card.getByRole('term')).toHaveTextContent('County executive financial statements');
    expect(card.getByText(/significant problem.*or a significant gap in the evidence/i)).toBeVisible();
    expect(card.getByText(/allegation about someone’s conduct is a separate claim/i)).toBeVisible();
    expect(card.getByRole('link', { name: 'Read audit findings' })).toHaveAttribute('href', '/audits');
  });
});
