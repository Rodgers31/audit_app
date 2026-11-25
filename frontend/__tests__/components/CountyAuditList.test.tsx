import { fireEvent, render, screen, within } from '@testing-library/react';
import AuditTab from '@/app/counties/[id]/tabs/AuditTab';
import type { AuditFinding, CountyComprehensive, UnaccountedCase } from '@/types';

const source = 'https://example.test/audit.pdf#page=3';
const paragraph = 'The statement of receipts and payments includes several transactions for which the County Assembly provided no vouchers. The sample audit continues by describing the rows separately.';
const report = 'Unsupported project payments\n' + paragraph;
const finding = (id: number, patch: Partial<AuditFinding> = {}): AuditFinding => ({
  id, finding: `Audit finding ${id}\n${paragraph}`, audited_entity_name: 'County Assembly',
  severity: 'warning', status: 'open', category: 'other', amount_involved: 0, amount_label: '',
  source_url: source, page_ref: 'p. 3', ...patch,
});

function data(findings: AuditFinding[], cases: UnaccountedCase[] = []) {
  return {
    audit: { findings, findings_count: findings.length, total_amount_involved: null, by_severity: {} },
    missing_funds: { cases },
  } as unknown as CountyComprehensive;
}

it('opens all 45 findings in batches with a live count and focus on the first new result', () => {
  const findings = Array.from({ length: 45 }, (_, i) => finding(i + 1));
  render(<AuditTab data={data(findings)} />);
  const list = within(screen.getByRole('region', { name: 'All audit findings' }));
  const count = list.getByRole('status');
  expect(list.getAllByRole('article')).toHaveLength(20);
  expect(count).toHaveTextContent('Showing 20 of 45 findings');
  fireEvent.click(list.getByRole('button', { name: 'Show 20 more' }));
  expect(list.getAllByRole('article')).toHaveLength(40);
  expect(count).toHaveTextContent('Showing 40 of 45 findings');
  expect(list.getByRole('heading', { name: 'Audit finding 21' })).toHaveFocus();
  fireEvent.click(list.getByRole('button', { name: 'Show 5 more' }));
  expect(list.getAllByRole('article')).toHaveLength(45);
  expect(count).toHaveTextContent('Showing 45 of 45 findings');
  expect(list.getByRole('heading', { name: 'Audit finding 41' })).toHaveFocus();
  expect(list.queryByRole('button', { name: /Show .* more/ })).toBeNull();
  expect(screen.queryByRole('group', { name: 'Findings by category' })).toBeNull();
  expect(list.queryByText('Other')).toBeNull();
});

it('applies the category before slicing and resets the count when changing categories', () => {
  const findings = Array.from({ length: 45 }, (_, i) => finding(i + 1,
    { category: i % 2 === 0 ? 'Payroll Issues' : 'other' }));
  render(<AuditTab data={data(findings)} />);
  const category = screen.getByRole('button', { name: /Payroll issues/ });
  fireEvent.click(category);
  expect(category).toHaveAttribute('aria-pressed', 'true');
  const list = within(screen.getByRole('region', { name: 'Payroll issues findings' }));
  expect(list.getByRole('status')).toHaveTextContent('Showing 20 of 23 findings');
  expect(list.queryByRole('heading', { name: /^Audit finding 2$/ })).toBeNull();
  fireEvent.click(list.getByRole('button', { name: 'Show 3 more' }));
  expect(list.getByRole('heading', { name: 'Audit finding 41' })).toHaveFocus();
  expect(list.getAllByRole('article')).toHaveLength(23);
  fireEvent.click(screen.getByRole('button', { name: 'Show all categories' }));
  expect(screen.getByRole('status')).toHaveTextContent('Showing 20 of 45 findings');
});

it('starts collapsed and keeps the report heading, exact words, recommendation and citation', () => {
  const titled = finding(1, { finding: report, amount_involved: 61e6, recommendation: 'Produce the original payment vouchers.' });
  const inline = finding(2, { finding: 'Lack of Risk Management Policy As previously reported, the county lacked a policy.' });
  const noSafeLead = finding(3, { finding: 'The auditors requested records to examine a payment.', source_url: null });
  render(<AuditTab data={data([titled, inline, noSafeLead])} />);
  const row = screen.getByRole('article', { name: 'Unsupported project payments' });
  const item = within(row);
  const trigger = item.getByText('Read the Auditor’s words', { selector: 'summary' });
  expect(trigger.parentElement).not.toHaveAttribute('open');
  expect(item.getByText(/^The statement of receipts/)).toHaveClass('line-clamp-2');
  expect(item.getByRole('link', { name: 'Source report, p. 3' })).toHaveAttribute('href', source);
  expect(item.getByText('KES 61.0M')).toBeVisible();
  fireEvent.click(trigger);
  expect(trigger.parentElement).toHaveAttribute('open');
  expect(row.querySelector('blockquote')?.textContent).toBe(report);
  expect(item.getByText('Produce the original payment vouchers.')).toBeVisible();
  expect(screen.getByRole('article', { name: 'Lack of Risk Management Policy' })).toBeVisible();
  expect(within(screen.getByRole('article', { name: /^Audit finding$/ })).queryByRole('link')).toBeNull();
});

it('uses the bounded typed preview only when its finding ID and source page match', () => {
  const cases = [{ finding_id: 1, title: 'Unaccounted for certified seeds', excerpt: paragraph.repeat(8), source: { page_url: source } },
    { finding_id: 2, title: 'Wrong report', excerpt: paragraph, source: { page_url: 'https://example.test/other.pdf' } }] as UnaccountedCase[];
  render(<AuditTab data={data([finding(1), finding(2)], cases)} />);
  const card = screen.getByRole('article', { name: cases[0].title });
  expect(card).toHaveTextContent('Unaccounted for / loss');
  expect(card.querySelector('.line-clamp-2')!.textContent!.length).toBeLessThanOrEqual(181);
  expect(screen.getByRole('article', { name: 'Audit finding 2' })).toBeVisible();
});
