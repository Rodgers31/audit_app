import { render, screen, within } from '@testing-library/react';
import TermsPage, { metadata } from './page';
import ArchivedTermsPage from './2026-03-01/page';

describe('Terms of Use', () => {
  it('shows the review draft with a short summary and no confirmed dates', () => {
    render(<TermsPage />);

    expect(screen.getByRole('heading', { level: 1, name: 'Terms of Use' })).toBeInTheDocument();
    expect(screen.getByText('Draft for review')).toBeVisible();
    const summary = screen.getByRole('region', { name: 'The short version' });
    expect(within(summary).getAllByRole('listitem')).toHaveLength(5);
    expect(within(summary).getByText('Read the full terms below for details.')).toBeVisible();
    expect(screen.getByText('[last updated date]')).toBeVisible();
    expect(screen.getByText('[date]')).toBeVisible();
    expect(screen.getByText('[2.0]')).toBeVisible();
    expect(metadata.robots).toEqual({ index: false, follow: true });
  });

  it('links every numbered contents entry to its focusable heading', () => {
    render(<TermsPage />);

    const contents = screen.getByRole('navigation', { name: 'Contents' });
    expect(within(contents).getAllByRole('link')).toHaveLength(14);
    const headings = screen.getAllByRole('heading', { level: 3 });
    expect(headings).toHaveLength(14);
    headings.forEach((heading, index) => {
      expect(heading.textContent).toMatch(new RegExp(`^${index + 1}\\.`));
      const link = within(contents).getByRole('link', { name: heading.textContent ?? '' });
      expect(link).toHaveAttribute('href', `#${heading.id}`);
      expect(heading).toHaveAttribute('tabindex', '-1');
    });
  });

  it('leaves unconfirmed routes and licences bracketed in the policy text', () => {
    render(<TermsPage />);

    expect(screen.getByText('[auditgava.com/corrections]').closest('a')).toBeNull();
    expect(screen.getByText('[corrections@domain]').closest('a')).toBeNull();
    expect(screen.getByText('[legal@domain]').closest('a')).toBeNull();
    expect(screen.getByText('[Creative Commons Attribution 4.0 (CC BY 4.0)]')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Previous version' })).toHaveAttribute(
      'href', '/terms/2026-03-01'
    );
  });

  it('identifies the previous document as the 1 March 2026 archive', () => {
    render(<ArchivedTermsPage />);

    expect(screen.getByRole('heading', { level: 1, name: 'Terms of Use archive' })).toBeVisible();
    expect(screen.getByText('1 March 2026')).toHaveAttribute('datetime', '2026-03-01');
    expect(screen.getByText('March 1, 2026')).toBeVisible();
    expect(screen.getByRole('heading', { name: '11. Contact' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'See the Terms of Use draft' })).toHaveAttribute(
      'href', '/terms'
    );
  });
});
