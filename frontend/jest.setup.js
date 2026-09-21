require('@testing-library/jest-dom');

// Polyfill window.matchMedia — jsdom doesn't ship it, but our
// ThemeToggle (and any future component reading prefers-color-scheme
// or other media queries) crashes without it. Returns a benign
// "no-match" object that satisfies the API surface used in code.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = function (query) {
    return {
      matches: false,
      media: query,
      onchange: null,
      addListener: function () {}, // legacy
      removeListener: function () {}, // legacy
      addEventListener: function () {},
      removeEventListener: function () {},
      dispatchEvent: function () {
        return false;
      },
    };
  };
}

// Polyfill ResizeObserver — jsdom doesn't ship it, and the editorial
// redesign's chart/responsive components construct one on mount. Without
// this, any test that renders NationalDebtCard or SummaryStrip dies with
// "ReferenceError: ResizeObserver is not defined" before it can assert
// anything, which would silently disable the units and risk-band
// regression fixtures rather than failing them honestly.
if (typeof global.ResizeObserver === 'undefined') {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Polyfill MessageChannel / TextEncoder / TextDecoder — jsdom ships none of
// them, and `react-dom/server`'s browser build reaches for all three at
// import time. Without them, any test that asserts on what a page
// SERVER-renders dies at import. That matters because the server render is
// the only way to see what the prerendered document contains: Testing
// Library's `render()` flushes effects, so a page whose data only arrives
// after an effect looks identical to one that server-rendered it, and a
// fixture written against `render()` would pass in both states.
//
// A hand-rolled MessageChannel rather than the one from `worker_threads`:
// that one's ports hold the event loop open and jest never exits.
if (typeof global.MessageChannel === 'undefined') {
  global.MessageChannel = class MessageChannel {
    constructor() {
      const makePort = () => ({
        onmessage: null,
        postMessage(data) {
          const peer = this._peer;
          if (peer && peer.onmessage) setTimeout(() => peer.onmessage({ data }), 0);
        },
        close() {},
        start() {},
        addEventListener() {},
        removeEventListener() {},
      });
      this.port1 = makePort();
      this.port2 = makePort();
      this.port1._peer = this.port2;
      this.port2._peer = this.port1;
    }
  };
}
if (typeof global.TextEncoder === 'undefined') {
  global.TextEncoder = require('util').TextEncoder;
}
if (typeof global.TextDecoder === 'undefined') {
  global.TextDecoder = require('util').TextDecoder;
}
