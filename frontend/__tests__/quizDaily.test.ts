import { quizArticleReferences } from '@/components/learn/quizArticleReferences';
import {
  DAILY_QUIZ_STORAGE_KEY, dailyQuizDay, dailyQuizQuestions, readDailyQuizScore, saveDailyQuizScore,
} from '@/components/learn/quizDaily';

beforeEach(() => localStorage.clear());

it('rotates the same three sourced questions at midnight in Kenya', () => {
  const before = dailyQuizDay(new Date('2026-11-21T20:59:59Z'));
  const after = dailyQuizDay(new Date('2026-11-21T21:00:00Z'));
  expect(before).toBe('2026-11-21');
  expect(after).toBe('2026-11-22');

  const questions = dailyQuizQuestions(before);
  expect(questions).toEqual(dailyQuizQuestions(before));
  expect(questions).not.toEqual(dailyQuizQuestions(after));
  expect(new Set(questions.map(question => question.id)).size).toBe(3);
  expect(questions.every(question => quizArticleReferences.has(question.id))).toBe(true);
});

it('stores only the current day and completed score', () => {
  const day = dailyQuizDay();
  saveDailyQuizScore({ day, score: 0 });
  saveDailyQuizScore({ day: '2026-01-01', score: 3 });
  expect(JSON.parse(localStorage.getItem(DAILY_QUIZ_STORAGE_KEY)!)).toEqual({ day, score: 0 });
  expect(readDailyQuizScore(day)).toEqual({ day, score: 0 });
  expect(readDailyQuizScore('2026-01-01')).toBeNull();
});

it('ignores malformed or out-of-range stored scores', () => {
  localStorage.setItem(DAILY_QUIZ_STORAGE_KEY, '{');
  expect(readDailyQuizScore(dailyQuizDay())).toBeNull();
  localStorage.setItem(DAILY_QUIZ_STORAGE_KEY, JSON.stringify({ day: dailyQuizDay(), score: 4 }));
  expect(readDailyQuizScore(dailyQuizDay())).toBeNull();
});
