import React from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { HISTORY_BRIDGE_BOOTSTRAP, historyBridge } from '@/lib/navigation/historyBridge';
import { retainHistoryTracking, useUnsavedHistoryGuard } from '@/lib/navigation/historyGuard';

const key = Symbol.for('auditgava.history-event-bridge.v1');
const globals = window as unknown as Record<symbol, unknown>;
type Listener = (event: PopStateEvent) => void;
let originalBridge: unknown;
let listeners: Listener[];
let bootWindow: Record<PropertyKey, unknown>;

beforeEach(() => {
  originalBridge = globals[key];
  listeners = [];
  bootWindow = { addEventListener: (_type: string, listener: Listener) => listeners.push(listener) };
  delete globals[key];
});

afterEach(() => {
  cleanup();
  globals[key] = originalBridge;
  jest.restoreAllMocks();
});

function bootstrap() {
  // Execute the shipping bootstrap against an isolated native-listener inventory.
  // Its bridge is then used by the real hook and manager on this test's Window.
  new Function('window', HISTORY_BRIDGE_BOOTSTRAP)(bootWindow);
  globals[key] = bootWindow[key];
}

async function popInRecordedChromeOrder() {
  const event = new PopStateEvent('popstate', { state: history.state });
  let stopped = false;
  Object.defineProperty(event, 'stopImmediatePropagation', { value: () => { stopped = true; } });
  Object.defineProperty(event, 'cancelBubble', { get: () => stopped });
  // Chrome Window targets ran an earlier bubble listener before a later capture
  // listener. Returning from each callback also allowed the route to commit.
  // JSDOM's dispatchEvent does not model that observed ordering/checkpoint.
  for (const listener of [...listeners]) {
    if (stopped) break;
    await act(async () => { listener(event); });
  }
}

function DirtyDraft() {
  useUnsavedHistoryGuard(true, 'current draft');
  return <p>Unsaved draft remains mounted</p>;
}

test('early relay cancels before a Next restore can retire the late-mounted guard', async () => {
  bootstrap();
  let view: ReturnType<typeof render>;
  const restore = jest.fn(() => view.rerender(<p>Next destination</p>));
  listeners.push(restore); // Framework listener exists before the editor mounts.
  view = render(<DirtyDraft />);
  jest.spyOn(window, 'confirm').mockReturnValue(false);
  await popInRecordedChromeOrder();
  expect(window.confirm).toHaveBeenCalledTimes(1);
  expect(restore).not.toHaveBeenCalled();
  expect(screen.getByText('Unsaved draft remains mounted')).toBeInTheDocument();
});

test('accepted traversal delegates once and permits the route commit', async () => {
  bootstrap();
  let view: ReturnType<typeof render>;
  const restore = jest.fn(() => view.rerender(<p>Next destination</p>));
  listeners.push(restore);
  view = render(<DirtyDraft />);
  jest.spyOn(window, 'confirm').mockReturnValue(true);
  await popInRecordedChromeOrder();
  expect(window.confirm).toHaveBeenCalledTimes(1);
  expect(restore).toHaveBeenCalledTimes(1);
  expect(screen.getByText('Next destination')).toBeInTheDocument();
});

test('bootstrap remains one early listener across repeated execution and subscriptions', () => {
  bootstrap();
  const bridge = historyBridge();
  const unsubscribe = bridge.subscribe(jest.fn());
  unsubscribe();
  bootstrap();
  expect(historyBridge()).toBe(bridge);
  expect(listeners).toHaveLength(1);
});

test('missing bootstrap refuses tracking before changing history', () => {
  const state = history.state;
  expect(() => retainHistoryTracking()).toThrow('History protection is unavailable');
  expect(history.state).toBe(state);
});

test('wrong version or non-callable subscription refuses tracking', () => {
  globals[key] = { version: 0, subscribe: () => () => {} };
  expect(() => retainHistoryTracking()).toThrow('History protection is unavailable');
  globals[key] = { version: 1, subscribe: null };
  expect(() => retainHistoryTracking()).toThrow('History protection is unavailable');
});
