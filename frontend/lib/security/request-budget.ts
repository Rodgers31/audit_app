/** Small application bounds, independent of the host's larger payload limit. */
export class RequestFailure extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}
export class RequestBudget {
  readonly controller = new AbortController();
  readonly signal = this.controller.signal;
  private readonly timer: ReturnType<typeof setTimeout>;
  private readonly expiresAt: number;
  private readonly onAbort = () => this.controller.abort(new RequestFailure(408, 'request_cancelled'));
  constructor(private readonly request: Request, milliseconds: number) {
    this.expiresAt = performance.now() + milliseconds;
    this.timer = setTimeout(() => this.controller.abort(new RequestFailure(504, 'request_deadline')), milliseconds);
    request.signal.addEventListener('abort', this.onAbort, { once: true });
    if (request.signal.aborted)
      this.onAbort();
  }
  check() {
    // Fulfilled stream promises can postpone timer dispatch. Check monotonic time too.
    if (!this.signal.aborted && performance.now() >= this.expiresAt) {
      this.controller.abort(new RequestFailure(504, 'request_deadline'));
    }
    if (this.signal.aborted)
      throw this.signal.reason;
  }
  async wait<T>(operation: Promise<T>): Promise<T> {
    try {
      this.check();
    }
    catch (error) {
      // The response already refuses; observe a later rejection without leaking
      // it as an unhandled promise. Actual SDK ownership is released separately.
      void operation.catch(() => {
      });
      throw error;
    }
    let onAbort: () => void = () => {
    };
    const aborted = new Promise<never>((_, reject) => {
      onAbort = () => reject(this.signal.reason);
      this.signal.addEventListener('abort', onAbort, { once: true });
      if (this.signal.aborted)
        onAbort();
    });
    try {
      const result = await Promise.race([operation, aborted]);
      this.check();
      return result;
    }
    finally {
      this.signal.removeEventListener('abort', onAbort);
    }
  }
  dispose() {
    clearTimeout(this.timer);
    this.request.signal.removeEventListener('abort', this.onAbort);
  }
}
// No identity map, waiting queue or retained request material. This guards one
// warm JS instance only; serverless replicas/restarts have independent counters.
export function createAdmission(limit: number) {
  let active = 0;
  return () => {
    if (active >= limit)
      throw new RequestFailure(503, 'request_capacity');
    active++;
    let released = false;
    return () => {
      if (!released) {
        released = true;
        active--;
      }
    };
  };
}
export async function readBoundedBytes(body: ReadableStream<Uint8Array> | null, headers: Headers, budget: RequestBudget, maxBytes: number, readExpiresAt = Infinity): Promise<Uint8Array> {
  budget.check();
  const length = headers.get('content-length');
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > maxBytes)) {
    // Cancellation is best effort; never let a hostile stream's cancellation
    // promise delay a refusal. There is no read or buffer on this path.
    void body?.cancel().catch(() => {
    });
    throw new RequestFailure(413, 'body_too_large');
  }
  if (!body)
    return new Uint8Array();
  const check = () => {
    budget.check();
    if (performance.now() >= readExpiresAt) {
      budget.controller.abort(new RequestFailure(408, 'body_deadline'));
      budget.check();
    }
  };
  const reader = body.getReader();
  const output = new Uint8Array(maxBytes);
  let size = 0;
  let emptyChunks = 0;
  try {
    while (true) {
      check();
      const { done, value } = await budget.wait(reader.read());
      check();
      if (done)
        return output.slice(0, size);
      if (value.byteLength === 0) {
        if (++emptyChunks > 16)
          throw new RequestFailure(400, 'body_stream_no_progress');
        continue;
      }
      emptyChunks = 0;
      if (value.byteLength > maxBytes - size)
        throw new RequestFailure(413, 'body_too_large');
      output.set(value, size);
      size += value.byteLength;
    }
  }
  catch (error) {
    void reader.cancel().catch(() => {
    });
    if (error instanceof RequestFailure)
      throw error;
    throw new RequestFailure(400, 'invalid_body_stream');
  }
  finally {
    reader.releaseLock();
  }
}
export async function readRequestBytes(request: Request, budget: RequestBudget, maxBytes: number) {
  const timer = setTimeout(() => budget.controller.abort(new RequestFailure(408, 'body_deadline')), 5000);
  try {
    return await readBoundedBytes(request.body, request.headers, budget, maxBytes, performance.now() + 5000);
  }
  finally {
    clearTimeout(timer);
  }
}
export function jsonObject(bytes: Uint8Array): Record<string, unknown> {
  try {
    const value: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    if (!value || typeof value !== 'object' || Array.isArray(value))
      throw new Error();
    return value as Record<string, unknown>;
  }
  catch {
    throw new RequestFailure(400, 'malformed_body');
  }
}
