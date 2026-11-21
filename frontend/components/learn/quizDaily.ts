import { getAllQuestions } from '@/data/quizData';
import { quizArticleReferences } from './quizArticleReferences';

export const DAILY_QUIZ_COUNT = 3;
export const DAILY_QUIZ_STORAGE_KEY = 'auditgava.quiz.daily';

const reviewedQuestions = getAllQuestions().filter(question => quizArticleReferences.has(question.id));
const kenyaDate = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Africa/Nairobi', year: 'numeric', month: '2-digit', day: '2-digit',
});

export function dailyQuizDay(now = new Date()): string {
  const parts = Object.fromEntries(kenyaDate.formatToParts(now).map(part => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function dailyQuizQuestions(day: string) {
  // A dated shuffle makes the three sourced questions the same for every
  // reader and independent of API availability or this browser's history.
  const questions = [...reviewedQuestions];
  let seed = Number(day.replaceAll('-', ''));
  for (let index = questions.length - 1; index > 0; index--) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    const other = Math.floor((seed / 2 ** 32) * (index + 1));
    [questions[index], questions[other]] = [questions[other], questions[index]];
  }
  return questions.slice(0, DAILY_QUIZ_COUNT);
}

export interface DailyQuizScore {
  day: string;
  score: number;
}

export function readDailyQuizScore(day: string): DailyQuizScore | null {
  try {
    const raw = localStorage.getItem(DAILY_QUIZ_STORAGE_KEY);
    if (raw === null) return null;
    const result: DailyQuizScore | null = JSON.parse(raw);
    if (result?.day === day && Number.isInteger(result.score) &&
      result.score >= 0 && result.score <= DAILY_QUIZ_COUNT) return { day, score: result.score };
  } catch {
    // A private or restricted browser can still play the daily round.
  }
  return null;
}

export function saveDailyQuizScore(result: DailyQuizScore) {
  // A round that crosses midnight must not displace the new day's score.
  if (result.day !== dailyQuizDay()) return;
  try {
    localStorage.setItem(DAILY_QUIZ_STORAGE_KEY, JSON.stringify(result));
  } catch {
    // The current result and sharing still work with storage blocked.
  }
}
