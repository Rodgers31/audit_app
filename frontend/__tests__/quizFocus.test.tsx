import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import QuizGame from '@/components/learn/QuizGame';
import { LangProvider } from '@/lib/i18n/LangProvider';

jest.mock('next/navigation', () => ({
  usePathname: () => '/learn/quiz',
  useRouter: () => ({ back: jest.fn() }),
}));

beforeEach(() => {
  jest.spyOn(Math, 'random').mockReturnValue(0.5);
  localStorage.clear();
  // jsdom does not implement dialog top-layer transitions. The browser suite
  // proves the actual native behavior, including Escape and inert navigation.
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', ''); } },
    close: { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open'); } },
  });
});

afterEach(() => jest.restoreAllMocks());

it('retains the question count, marks one answer, and restores the category focus', () => {
  render(<QuizGame />);
  const launch = screen.getByRole('button', { name: /Public Finance/i });
  expect(screen.getByText('36 questions across 6 categories')).toBeInTheDocument();

  fireEvent.click(launch);
  const round = screen.getByRole('dialog');
  expect(within(round).getByRole('progressbar')).toHaveAttribute('aria-valuetext', '1 of 6');
  const option = within(round).getByRole('button', { name: 'Kenya Revenue Authority (KRA)' });
  fireEvent.click(option);
  fireEvent.click(option);
  expect(within(round).getByRole('heading', { name: 'Correct.' })).toHaveFocus();
  expect(within(round).queryByRole('link')).not.toBeInTheDocument();

  fireEvent.click(within(round).getByRole('button', { name: 'Next question' }));
  expect(within(round).getByRole('progressbar')).toHaveAttribute('aria-valuetext', '2 of 6');
  fireEvent.click(within(round).getByRole('button', { name: 'Controller of Budget' }));
  expect(within(round).getByRole('link', { name: /Article 228/ })).toHaveAttribute('href', '/learn?article=228');
  fireEvent.click(within(round).getByRole('button', { name: 'Quit quiz' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Public Finance/i })).toHaveFocus();
});

it('uses Kiswahili for the controls and preserves the English source text', () => {
  localStorage.setItem('auditgava-lang', 'sw');
  render(<LangProvider><QuizGame /></LangProvider>);
  fireEvent.click(screen.getByRole('button', { name: /Fedha za umma/i }));
  const round = screen.getByRole('dialog');
  expect(within(round).getByRole('progressbar', { name: 'Maendeleo ya maswali' })).toHaveAttribute('aria-valuetext', '1 kati ya 6');
  expect(within(round).getByRole('heading', { level: 1 })).toHaveAttribute('lang', 'en');
});
