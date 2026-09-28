import { getQueryClient } from '@/lib/react-query/getQueryClient';
import CountiesPage from '@/app/counties/page';

const getCounties = jest.fn();
jest.mock('@/lib/api/counties', () => ({ getCounties: (...args: unknown[]) => getCounties(...args) }));
jest.mock('@/app/counties/CountiesPageClient', () => () => null);

describe('SSR prefetch timeout', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    getQueryClient().clear();
    getCounties.mockReset();
  });

  afterEach(() => {
    getQueryClient().clear();
    jest.useRealTimers();
  });

  it('aborts the losing county request when the page stops waiting', async () => {
    let aborted = false;
    getCounties.mockImplementation((_filters: unknown, signal: AbortSignal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => {
          aborted = true;
          reject(new Error('cancelled'));
        }, { once: true });
      })
    );

    const page = CountiesPage();
    await jest.advanceTimersByTimeAsync(5000);
    await page;

    expect(getCounties).toHaveBeenCalledTimes(1);
    expect(aborted).toBe(true);
  });
});
