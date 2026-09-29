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
  expect(screen.getByRole('tooltip')).toHaveTextContent('separate from the accountability score');

  fireEvent.click(screen.getByRole('button', { name: 'Switch to English' }));
  expect(screen.getByRole('tooltip')).toHaveTextContent('audit opinion carries the same weight');
});

it('keeps English glossary text for terms without a translation', () => {
  localStorage.setItem('auditgava-lang', 'sw');
  render(
    <LangProvider>
      <InfoTip term='debt-to-gdp' />
    </LangProvider>
  );

  fireEvent.click(screen.getByRole('button', { name: 'What is Debt-to-GDP Ratio?' }));
  expect(screen.getByRole('tooltip')).toHaveTextContent('Debt-to-GDP Ratio');
  expect(screen.getByRole('tooltip')).toHaveTextContent("country's total debt as a percentage");
});
