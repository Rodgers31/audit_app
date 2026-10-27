/** @jest-environment node */
import assert from 'node:assert/strict';
import { readBoundedBytes, readRequestBytes, RequestBudget } from '@/lib/security/request-budget';
test('elapsed monotonic budget refuses a fulfilled stream before timer dispatch', async () => {
  const clock = jest.spyOn(performance, 'now').mockReturnValue(0);
  const budget = new RequestBudget(new Request('https://app.test'), 10);
  clock.mockReturnValue(11);
  try {
    const body = new ReadableStream<Uint8Array>({ start(controller) {
        controller.enqueue(new TextEncoder().encode('{}'));
        controller.close();
      } });
    await assert.rejects(readBoundedBytes(body, new Headers(), budget, 8192), error => (error as {
      status?: number;
    }).status === 504);
  }
  finally {
    clock.mockRestore();
    budget.dispose();
  }
});
test('consecutive zero-byte chunks have a finite no-progress bound', async () => {
  let reads = 0;
  const cancel = jest.fn();
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      reads++;
      if (reads <= 1000)
        controller.enqueue(new Uint8Array());
      else {
        controller.enqueue(new TextEncoder().encode('{}'));
        controller.close();
      }
    }, cancel,
  });
  const budget = new RequestBudget(new Request('https://app.test'), 5000);
  try {
    await assert.rejects(readBoundedBytes(body, new Headers(), budget, 8192), error => (error as {
      status?: number;
    }).status === 400);
    expect(reads).toBeLessThanOrEqual(18);
    expect(cancel).toHaveBeenCalledTimes(1);
  }
  finally {
    budget.dispose();
  }
});
test('an isolated empty chunk does not change healthy bytes', async () => {
  const body = new ReadableStream<Uint8Array>({ start(controller) {
      controller.enqueue(new Uint8Array());
      controller.enqueue(new TextEncoder().encode('{}'));
      controller.close();
    } });
  const budget = new RequestBudget(new Request('https://app.test'), 5000);
  try {
    expect(new TextDecoder().decode(await readBoundedBytes(body, new Headers(), budget, 8192))).toBe('{}');
  }
  finally {
    budget.dispose();
  }
});
test('body phase enforces elapsed five seconds before timer dispatch', async () => {
  const clock = jest.spyOn(performance, 'now').mockReturnValue(0);
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      clock.mockReturnValue(5001);
      controller.enqueue(new TextEncoder().encode('{}'));
      controller.close();
    },
  });
  const request = new Request('https://app.test', { method: 'POST', body, duplex: 'half' } as any);
  const budget = new RequestBudget(request, 15000);
  try {
    await assert.rejects(readRequestBytes(request, budget, 8192), error => (error as {
      status?: number;
    }).status === 408);
  }
  finally {
    clock.mockRestore();
    budget.dispose();
  }
});
test('wait rejects a fulfilled operation after elapsed budget', async () => {
  const clock = jest.spyOn(performance, 'now').mockReturnValue(0);
  const budget = new RequestBudget(new Request('https://app.test'), 10);
  clock.mockReturnValue(11);
  try {
    await assert.rejects(budget.wait(Promise.resolve('inert')), error => (error as {
      status?: number;
    }).status === 504);
  }
  finally {
    clock.mockRestore();
    budget.dispose();
  }
});
test('elapsed wait consumes a rejected operation without an unhandled rejection', async () => {
  const clock = jest.spyOn(performance, 'now').mockReturnValue(0);
  const budget = new RequestBudget(new Request('https://app.test'), 10);
  clock.mockReturnValue(11);
  try {
    await assert.rejects(budget.wait(Promise.reject(new Error('inert_dependency_failure'))), error => (error as {
      status?: number;
    }).status === 504);
    await new Promise(resolve => setImmediate(resolve));
  }
  finally {
    clock.mockRestore();
    budget.dispose();
  }
});
