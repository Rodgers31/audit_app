(() => {
  const events = [];
  window.__b11Navigation = events;
  let activeUntil = 0;
  let frame = 0;
  const geometry = () => ({ y: scrollY, height: document.documentElement.scrollHeight,
    bodyHeight: document.body?.scrollHeight, viewport: innerHeight,
    rows: document.querySelectorAll('table tbody tr').length,
    firstRow: document.querySelector('table tbody tr')?.textContent?.slice(0, 180),
    showing: [...document.querySelectorAll('div,span,p')].find(n => /^Showing\s+\d+[–-]\d+\s+of/.test(n.textContent ?? '') && n.children.length === 0)?.textContent,
    active: document.activeElement?.outerHTML.slice(0, 200) });
  const safeState = state => ({ __NA: state?.__NA, __N: state?.__N,
    tree: state?.__PRIVATE_NEXTJS_INTERNALS_TREE });
  const emit = (kind, extra = {}, layout = true) => {
    if (events.length >= 5000) return;
    events.push({ kind, time: performance.now(), url: location.pathname + location.search,
      historyLength: history.length, restoration: history.scrollRestoration,
      readyState: document.readyState, state: safeState(history.state),
      ...(layout ? geometry() : {}), ...extra });
  };
  for (const method of ['pushState', 'replaceState']) {
    const original = history[method];
    history[method] = function (state, unused, url) {
      emit(method + ':before', { target: String(url), suppliedState: safeState(state),
        stack: new Error().stack }, false);
      const result = original.apply(this, arguments);
      emit(method + ':after', { target: String(url) });
      activeUntil = performance.now() + 2500;
      return result;
    };
  }
  for (const name of ['popstate', 'pageshow', 'pagehide', 'DOMContentLoaded', 'load', 'scroll', 'focusin']) {
    window.addEventListener(name, event => {
      emit(name, name === 'popstate' ? { eventState: safeState(event.state) } : {});
      if (name !== 'scroll') activeUntil = performance.now() + 2500;
    }, true);
  }
  document.addEventListener('click', event => {
    const target = event.target.closest('a,button');
    emit('click:capture', { target: target?.outerHTML.slice(0, 400) });
    activeUntil = performance.now() + 5000;
  }, true);
  document.addEventListener('click', event => emit('click:bubble', { prevented: event.defaultPrevented }));
  const originalSetItem = Storage.prototype.setItem;
  Storage.prototype.setItem = function (key, value) {
    if (key === 'auditgava-nav-trail') emit('trail:set', { trail: JSON.parse(value) });
    return originalSetItem.apply(this, arguments);
  };
  new MutationObserver(() => {
    if (performance.now() < activeUntil) emit('layout:mutation');
  }).observe(document, { childList: true, subtree: true });
  const sample = () => {
    if (++frame % 4 === 0 && performance.now() < activeUntil) emit('frame');
    requestAnimationFrame(sample);
  };
  requestAnimationFrame(sample);
  emit('probe:alive', {}, false);
})();
