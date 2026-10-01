import { fireEvent, render, screen } from '@testing-library/react';
import InfoTip from '@/components/InfoTip';
import { LangProvider, useLang } from '@/lib/i18n/LangProvider';

function ChangeLanguage() {
  const { setLang } = useLang();
  return (
    <>
      <button onClick={() => setLang('en')}>Switch to English</button>
      <button onClick={() => setLang('sw')}>Switch to Swahili</button>
      <button onClick={() => setLang('plain')}>Switch to plain English</button>
    </>
  );
}

afterEach(() => localStorage.clear());

it('localizes the financial-health explanation and accessible name while open', () => {
  render(
    <LangProvider>
      <ChangeLanguage />
      <InfoTip term='financial-health' />
    </LangProvider>
  );

  fireEvent.click(screen.getByRole('button', { name: 'What is Financial Health Score?' }));
  expect(screen.getByRole('tooltip')).toHaveTextContent('Financial Health Score');
  expect(screen.getByRole('tooltip')).toHaveTextContent(/at least two inputs/i);
  expect(screen.getByRole('tooltip')).toHaveTextContent('separate from the accountability score');

  fireEvent.click(screen.getByRole('button', { name: 'Switch to Swahili' }));
  expect(screen.getByRole('button', { name: 'Alama ya Afya ya Kifedha ni nini?' })).toBeInTheDocument();
  expect(screen.getByRole('tooltip')).toHaveTextContent('Alama ya Afya ya Kifedha');
  expect(screen.getByRole('tooltip')).toHaveTextContent('Angalau vipengele viwili');
  expect(screen.getByRole('tooltip')).toHaveTextContent('uzito sawa na vipengele vingine vitatu');
  expect(screen.getByRole('tooltip')).toHaveTextContent('tofauti na alama ya uwajibikaji');

  fireEvent.click(screen.getByRole('button', { name: 'Switch to plain English' }));
  expect(screen.getByRole('button', { name: 'What does Money Health Score mean?' })).toBeInTheDocument();
  expect(screen.getByRole('tooltip')).toHaveTextContent('Money Health Score');
  expect(screen.getByRole('tooltip')).toHaveTextContent('at least two');
  expect(screen.getByRole('tooltip')).toHaveTextContent('counts as much as the other three together');
  expect(screen.getByRole('tooltip')).toHaveTextContent('The accountability score is separate');

  fireEvent.click(screen.getByRole('button', { name: 'Switch to English' }));
  expect(screen.getByRole('tooltip')).toHaveTextContent('audit signal carries the same weight');
});

// Expected reader-facing names and meaning fragments, independent of catalog lookup.
const activeTerms = [
  ['debt-to-gdp', 'Uwiano wa Deni kwa Pato la Taifa', 'Debt compared with the economy', 'thamani ya sasa', 'present value'],
  ['external-debt', 'Deni la Nje', 'Debt to lenders abroad', 'sarafu', 'currencies'],
  ['domestic-debt', 'Deni la Ndani', 'Debt to lenders in Kenya', 'hati', 'bills'],
  ['pending-bills', 'Bili Ambazo Hazijalipwa', 'Unpaid bills', 'sifuri', 'zero'],
  ['budget-execution', 'Kiwango cha Matumizi ya Bajeti', 'Share of the budget spent', 'ufisadi', 'corruption'],
  ['audit-clean', 'Maoni ya Ukaguzi Yasiyo na Masharti', 'Clean audit opinion', 'wizi', 'theft'],
  ['outstanding', 'Salio la Deni', 'Amount still owed', 'wadai', 'creditor'],
  ['multilateral', 'Mkopeshaji wa Kimataifa wa Nchi Nyingi', 'Lender backed by several countries', 'mkataba', 'agreement'],
  ['bilateral', 'Mkopeshaji wa Nchi Moja', 'Lender from another government', 'mkataba', 'agreement'],
  ['commercial', 'Mkopeshaji wa Kibiashara', 'Private lender', 'mkataba', 'agreement'],
  ['development-spending', 'Matumizi ya Maendeleo', 'Spending on long-term projects', 'miradi', 'projects'],
  ['recurrent-spending', 'Matumizi ya Kawaida', 'Day-to-day spending', 'mishahara', 'salaries'],
] as const;

it.each(activeTerms)('switches the open %s tooltip coherently in all modes and persists selection',
  (term, swTitle, plainTitle, swMeaning, plainMeaning) => {
    render(<LangProvider><ChangeLanguage /><InfoTip term={term} /></LangProvider>);
    const help = screen.getAllByRole('button').find(button => button.getAttribute('aria-label'))!;
    const englishLabel = help.getAttribute('aria-label');
    fireEvent.focus(help);
    const englishBody = screen.getByRole('tooltip').textContent;

    fireEvent.click(screen.getByRole('button', { name: 'Switch to Swahili' }));
    expect(help).toHaveAccessibleName(`${swTitle} ni nini?`);
    expect(screen.getByRole('tooltip')).toHaveTextContent(swTitle);
    expect(screen.getByRole('tooltip')).toHaveTextContent(swMeaning);
    expect(screen.getByRole('tooltip').textContent).not.toBe(englishBody);
    expect(localStorage.getItem('auditgava-lang')).toBe('sw');

    fireEvent.click(screen.getByRole('button', { name: 'Switch to plain English' }));
    expect(help).toHaveAccessibleName(`What does ${plainTitle} mean?`);
    expect(screen.getByRole('tooltip')).toHaveTextContent(plainTitle);
    expect(screen.getByRole('tooltip')).toHaveTextContent(plainMeaning);
    expect(localStorage.getItem('auditgava-lang')).toBe('plain');

    fireEvent.click(screen.getByRole('button', { name: 'Switch to English' }));
    expect(help).toHaveAccessibleName(englishLabel!);
    expect(screen.getByRole('tooltip').textContent).toBe(englishBody);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('tooltip') === null).toBe(true);
  });

it.each([
  ['sw', 'Bili Ambazo Hazijalipwa ni nini?', 'kutopatikana si sawa na sifuri'],
  ['plain', 'What does Unpaid bills mean?', 'Missing information is not zero'],
])('hydrates stored %s and restores it after provider remount', (lang, label, meaning) => {
  localStorage.setItem('auditgava-lang', lang);
  const first = render(<LangProvider><InfoTip term='pending-bills' /></LangProvider>);
  fireEvent.click(screen.getByRole('button', { name: label }));
  expect(screen.getByRole('tooltip')).toHaveTextContent(meaning);
  first.unmount();
  render(<LangProvider><InfoTip term='pending-bills' /></LangProvider>);
  expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
});

it.each(['toString', 'constructor', '__proto__', 'hasOwnProperty', 'valueOf', 'missing-term', ''])
  ('renders no control or tooltip for unknown %s', term => {
    const { container } = render(<LangProvider><InfoTip term={term} /></LangProvider>);
    expect(container.childElementCount).toBe(0);
    expect(screen.queryByRole('button') === null).toBe(true);
    expect(screen.queryByRole('tooltip') === null).toBe(true);
  });

it('preserves a valid English fallback under stored Swahili', () => {
  localStorage.setItem('auditgava-lang', 'sw');
  render(<LangProvider><InfoTip term='principal' /></LangProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'What is Principal?' }));
  expect(screen.getByRole('tooltip')).toHaveTextContent('The original amount borrowed');
});

it('renders English without a provider and rejects prototype keys there too', () => {
  render(<><InfoTip term='pending-bills' /><InfoTip term='constructor' /></>);
  expect(screen.getAllByRole('button').length).toBe(1);
  fireEvent.click(screen.getByRole('button', { name: 'What is Pending Bills?' }));
  expect(screen.getByRole('tooltip')).toHaveTextContent('Missing information is not zero');
});

it('removes an open valid tooltip when its term becomes unknown', () => {
  const { rerender } = render(<InfoTip term='financial-health' />);
  fireEvent.click(screen.getByRole('button'));
  expect(screen.getByRole('tooltip')).toBeInTheDocument();
  rerender(<InfoTip term='toString' />);
  expect(screen.queryByRole('tooltip') === null).toBe(true);
  expect(screen.queryByRole('button') === null).toBe(true);
});
