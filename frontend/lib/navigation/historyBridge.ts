/** Installed before Next hydrates, so a cancelled traversal cannot unmount an editor first. */
export const HISTORY_BRIDGE_BOOTSTRAP = `(() => {
  const key = Symbol.for('auditgava.history-event-bridge.v1');
  if (window[key]) return;
  const subscribers = new Set();
  window[key] = {
    version: 1,
    subscribe(listener) { subscribers.add(listener); return () => subscribers.delete(listener); }
  };
  window.addEventListener('popstate', event => {
    for (const listener of subscribers) {
      listener(event);
      if (event.cancelBubble) break;
    }
  }, true);
})();`;

type HistoryBridge = {
  version: 1;
  subscribe: (listener: (event: PopStateEvent) => void) => () => void;
};

export function historyBridge(): HistoryBridge {
  const bridge = (window as unknown as Record<symbol, HistoryBridge | undefined>)[Symbol.for('auditgava.history-event-bridge.v1')];
  if (bridge?.version !== 1 || typeof bridge.subscribe !== 'function') {
    throw new Error('History protection is unavailable. Reload before editing a draft.');
  }
  return bridge;
}
