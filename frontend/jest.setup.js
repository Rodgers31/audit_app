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
