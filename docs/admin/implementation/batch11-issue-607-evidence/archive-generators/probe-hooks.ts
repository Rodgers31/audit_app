import { test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  const rate = Number(process.env.SCROLL_CPU || '1');
  const session = await page.context().newCDPSession(page);
  await session.send('Emulation.setCPUThrottlingRate', { rate });
  const errors: string[] = [];
  const network: any[] = [];
  (page as any).__scrollNetwork = network;
  page.on('response', response => {
    if (/counties|\.js/.test(response.url())) network.push({time: Date.now(), url: response.url(), status: response.status()});
  });
  const delay = Number(process.env.SCROLL_CHUNK_DELAY || '0');
  if (delay) await page.route('**/_next/static/chunks/*.js', async route => {
    if (/\/counties\/[\w-]+/.test(page.url())) {
      network.push({time: Date.now(), delayed: delay, url: route.request().url()});
      await new Promise(resolve => setTimeout(resolve, delay));
    }
    await route.continue();
  });
  (page as any).__scrollErrors = errors;
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('requestfailed', request => errors.push(`${request.url()}: ${request.failure()?.errorText}`));
  await page.addInitScript(({ manual }) => {
    if (manual) history.scrollRestoration = 'manual';
    const events: any[] = [];
    (window as any).__scrollEvents = events;
    const record = (event: string, extra: unknown = null) => {
      const root = document.documentElement;
      const link = document.querySelector('table tbody tr a');
      const rect = link?.getBoundingClientRect();
      const detail = document.querySelector('h1')?.textContent;
      const state = history.state;
      const item = { event, time: performance.now(), url: location.href, y: scrollY,
        height: root?.scrollHeight, maxY: root ? root.scrollHeight - innerHeight : null,
        viewport: [innerWidth, innerHeight], scrollRestoration: history.scrollRestoration,
        behavior: root ? getComputedStyle(root).scrollBehavior : null,
        rows: document.querySelectorAll('table tbody tr').length, detail,
        link: rect ? { top: rect.top, bottom: rect.bottom } : null,
        state: state ? { __NA: state.__NA, tree: state.__PRIVATE_NEXTJS_INTERNALS_TREE } : null,
        trail: sessionStorage.getItem('auditgava-nav-trail'),
        fonts: document.fonts?.status, images: [...document.images].map(i => ({ src: i.getAttribute('src'), complete: i.complete, height: i.height })), extra };
      if (events.length < 5000) events.push(item);
    };
    (window as any).__scrollRecord = record;
    for (const method of ['pushState', 'replaceState'] as const) {
      const original = history[method].bind(history);
      history[method] = (...args: any[]) => {
        record(`before:${method}`, args[2]);
        original(args[0], args[1], args[2]);
        record(`after:${method}`, args[2]);
      };
    }
    const scrollTo = window.scrollTo.bind(window);
    window.scrollTo = ((...args: any[]) => {
      record('scrollTo', args);
      (scrollTo as any)(...args);
    }) as typeof window.scrollTo;
    const scrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (...args) {
      record('scrollIntoView', { tag: this.tagName, args });
      scrollIntoView.apply(this, args);
    };
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key === 'auditgava-nav-trail') record('save:trail', value);
      setItem.call(this, key, value);
    };
    addEventListener('popstate', () => {
      record('popstate:capture');
      queueMicrotask(() => record('popstate:microtask'));
      requestAnimationFrame(() => record('popstate:frame'));
      setTimeout(() => record('popstate:next-task'), 0);
    }, true);
    addEventListener('click', event => {
      const link = (event.target as Element)?.closest('a');
      if (link) record('click:capture', { href: link.getAttribute('href'), rect: link.getBoundingClientRect().toJSON() });
    }, true);
    addEventListener('scroll', () => record('scroll'), { passive: true });
    addEventListener('DOMContentLoaded', () => {
      record('DOMContentLoaded');
      new ResizeObserver(() => record('resize')).observe(document.body);
      new MutationObserver(() => record('mutation')).observe(document.body, { childList: true, subtree: true });
      document.fonts.ready.then(() => record('fonts:ready'));
    });
    let last = '';
    const sample = () => {
      const current = `${location.href}|${scrollY}|${document.documentElement.scrollHeight}|${document.querySelectorAll('table tbody tr').length}`;
      if (current !== last) { record('frame:change'); last = current; }
      requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  }, { manual: process.env.SCROLL_NATIVE_ABSENT === 'true' });
});

test.afterEach(async ({ page }, testInfo) => {
  const events = await page.evaluate(() => {
    (window as any).__scrollRecord?.('after:test');
    return (window as any).__scrollEvents;
  });
  await testInfo.attach('scroll-events', { body: JSON.stringify({
    cpu: process.env.SCROLL_CPU || '1', chunkDelay: process.env.SCROLL_CHUNK_DELAY || '0', nativeAbsent: process.env.SCROLL_NATIVE_ABSENT === 'true', network: (page as any).__scrollNetwork, events, errors: (page as any).__scrollErrors,
  }, null, 2), contentType: 'application/json' });
  await page.screenshot({ path: testInfo.outputPath('settled.png') });
});
