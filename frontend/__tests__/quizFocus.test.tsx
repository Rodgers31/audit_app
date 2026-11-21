import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import QuizGame from '@/components/learn/QuizGame';
import { DAILY_QUIZ_STORAGE_KEY, dailyQuizDay, dailyQuizQuestions } from '@/components/learn/quizDaily';
import type { QuizDebtQuestion } from '@/components/learn/quizDebtQuestion';
import { getAllQuestions } from '@/data/quizData';
import { LangProvider } from '@/lib/i18n/LangProvider';

jest.mock('next/navigation', () => ({
  usePathname: () => '/learn/quiz',
  useRouter: () => ({ back: jest.fn() }),
}));
jest.mock('@/components/learn/QuizDailyShare', () => ({ __esModule: true, default: () => null }));

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

it('keeps the live question and citations stable from answer through review', () => {
  const liveQuestion: QuizDebtQuestion = {
    id: 'fin-debt-live',
    difficulty: 'medium',
    question: 'How much goes to debt repayments?',
    explanation: 'FY 2026/27 debt repayments total KES 2.32T.',
    language: 'en',
    context: 'FY 2026/27 approved budget',
    options: ['KES 25', 'KES 50', 'KES 78', 'KES 95'],
    correctIndex: 2,
    sourceUrl: 'https://www.treasury.go.ke/fixture.pdf',
  };
  const { rerender } = render(<QuizGame liveQuestion={liveQuestion} />);
  fireEvent.click(screen.getByRole('button', { name: /Quick Play/i }));
  const round = within(screen.getByRole('dialog'));

  for (let i = 0; i < 2; i++) {
    fireEvent.click(round.getAllByRole('button').slice(1)[0]);
    fireEvent.click(round.getByRole('button', { name: 'Next question' }));
  }
  expect(round.getByRole('progressbar')).toHaveAttribute('aria-valuetext', '3 of 10');
  rerender(<QuizGame />);
  fireEvent.click(round.getByRole('button', { name: 'KES 50' }));
  expect(round.getByRole('heading', { name: 'Not quite.' })).toHaveFocus();
  expect(round.getByRole('link', { name: /See it on the debt page/ })).toHaveAttribute('href', '/debt');
  expect(round.getByRole('link', { name: /Source document/ })).toHaveAttribute('href', liveQuestion.sourceUrl);

  for (let i = 3; i < 10; i++) {
    fireEvent.click(round.getByRole('button', { name: 'Next question' }));
    fireEvent.click(round.getAllByRole('button').slice(1)[0]);
  }
  fireEvent.click(round.getByRole('button', { name: 'See results' }));
  const review = within(screen.getByRole('region', { name: 'Review Answers' }));
  expect(review.getByText('FY 2026/27 approved budget')).toBeInTheDocument();
  expect(review.getByText('KES 78')).toBeInTheDocument();
  expect(review.getByRole('link', { name: /Source document/ })).toHaveAttribute('href', liveQuestion.sourceUrl);
});

it('limits Quick Play to the chosen difficulty without changing the daily round', () => {
  render(<QuizGame />);
  fireEvent.change(screen.getByRole('combobox', { name: 'Difficulty' }), { target: { value: 'hard' } });
  const hard = getAllQuestions().filter(question => question.difficulty === 'hard');
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`Quick Play.*${hard.length} questions`) }));
  const round = within(screen.getByRole('dialog'));
  hard.forEach((question, index) => {
    expect(round.getByRole('heading', { level: 1 })).toHaveTextContent(question.question);
    fireEvent.click(round.getByRole('button', { name: question.options[question.correctIndex] }));
    fireEvent.click(round.getByRole('button', { name: index === hard.length - 1 ? 'See results' : 'Next question' }));
  });
  fireEvent.click(screen.getByRole('button', { name: 'All categories' }));
  fireEvent.click(screen.getByRole('button', { name: /Daily 3/ }));
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuetext', '1 of 3');
});

it('saves a completed Daily 3 score, restores it after reload, and replays the same set', () => {
  const day = dailyQuizDay();
  const questions = dailyQuizQuestions(day);
  const view = render(<QuizGame />);
  fireEvent.click(screen.getByRole('button', { name: /Daily 3/ }));
  const round = within(screen.getByRole('dialog'));
  questions.forEach((question, index) => {
    expect(round.getByRole('heading', { level: 1 })).toHaveTextContent(question.question);
    fireEvent.click(round.getByRole('button', { name: question.options[question.correctIndex] }));
    expect(round.getByRole('link', { name: /Article/ })).toBeInTheDocument();
    fireEvent.click(round.getByRole('button', { name: index === 2 ? 'See results' : 'Next question' }));
  });
  expect(screen.getByRole('heading', { name: '3 of 3 correct' })).toHaveFocus();
  expect(screen.getByRole('region', { name: 'Review Answers' })).toBeInTheDocument();
  expect(JSON.parse(localStorage.getItem(DAILY_QUIZ_STORAGE_KEY)!)).toEqual({ day, score: 3 });
  view.unmount();

  render(<QuizGame />);
  fireEvent.click(screen.getByRole('button', { name: /Daily 3.*Today’s score is 3 of 3/ }));
  expect(screen.getByRole('heading', { name: '3 of 3 correct' })).toHaveFocus();
  fireEvent.click(screen.getByRole('button', { name: 'Play Again' }));
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(questions[0].question);
  fireEvent.click(screen.getByRole('button', { name: 'Quit quiz' }));
  expect(screen.getByRole('button', { name: /Daily 3/ })).toHaveFocus();
});
