import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import type { Page, TestInfo } from '@playwright/test';

type ObserverResult = {
  schema: string;
  journal: unknown[];
  errors: unknown[];
  limits: { events: boolean; frames: boolean; errors: boolean };
  frames: number;
  allObserversStopped: boolean;
  wrappedSurfaces: string[];
};

/** Diagnostics only: no navigation, timing barrier or scroll-target changes. */
export function installCountyPaginationScrollObserver(): void {
  const key = '__countyPaginationScrollObserverV1';
  const scope = window as unknown as Record<string, unknown>;
  if (Object.getOwnPropertyDescriptor(window, key)) {
    Object.defineProperty(window, '__countyPaginationScrollObserverConflictV1', { value: true });
    return;
  }
  const apply = Reflect.apply;
  const getDescriptor = Object.getOwnPropertyDescriptor;
  const define = Object.defineProperty;
  const slice = String.prototype.slice;
  const codeAt = String.prototype.charCodeAt;
  const nativeAdd = EventTarget.prototype.addEventListener;
  const nativeRemove = EventTarget.prototype.removeEventListener;
  const request = window.requestAnimationFrame.bind(window);
  const cancel = window.cancelAnimationFrame.bind(window);
  const NativeError = Error;
  const NativeMutationObserver = MutationObserver;
  const journal: unknown[] = [];
  const errors: unknown[] = [];
  const limits = { events: false, frames: false, errors: false };
  const hooks: { owner: object; name: string; original: PropertyDescriptor; wrapper: unknown; setter: boolean; label: string; installed: PropertyDescriptor }[] = [];
  const listeners: [string, EventListener][] = [];
  let stopped = false;
  let frames = 0;
  let raf = 0;
  let previous = '';
  let previousCommit = '';
  let mutation: MutationObserver | undefined;
  let result: ObserverResult | undefined;

  function text(value: unknown, max: number): string | null {
    if (typeof value !== 'string') return null;
    let bytes = 0;
    let end = 0;
    for (let index = 0; index < value.length; index++) {
      const unit = apply(codeAt, value, [index]) as number;
      let width = unit < 0x80 ? 1 : unit < 0x800 ? 2 : 3;
      if (unit >= 0xd800 && unit <= 0xdbff && index + 1 < value.length) {
        const next = apply(codeAt, value, [index + 1]) as number;
        if (next >= 0xdc00 && next <= 0xdfff) { width = 4; index++; }
      }
      if (bytes + width > max) break;
      bytes += width;
      end = index + 1;
    }
    return apply(slice, value, [0, end]) as string;
  }
  function error(stage: string, caught: unknown): void {
    if (errors.length === 16) { limits.errors = true; return; }
    errors.push({ stage, kind: typeof caught, message: typeof caught === 'string' ? text(caught, 128) : null });
  }
  function point() {
    const root = document.documentElement;
    const body = document.body;
    const main = document.querySelector('main');
    return {
      url: text(location.href, 512), y: scrollY, x: scrollX,
      rootTop: root?.scrollTop ?? null, bodyTop: body?.scrollTop ?? null,
      rootHeight: root?.scrollHeight ?? null, bodyHeight: body?.scrollHeight ?? null,
      clientHeight: root?.clientHeight ?? null, innerHeight,
      mainClass: text(main?.firstElementChild?.className, 128),
      heading: text(main?.querySelector('h1')?.textContent, 256),
      activeTag: text(document.activeElement?.tagName, 32),
      inlineBehavior: text(root?.style.scrollBehavior, 32),
      computedBehavior: root ? text(getComputedStyle(root).scrollBehavior, 32) : null,
      restoration: text(history.scrollRestoration, 32), historyLength: history.length,
      stateKeys: history.state && typeof history.state === 'object' ? Object.keys(history.state).slice(0, 8).map(value => text(value, 64)) : null,
    };
  }
  function capture(type: string, detail: unknown = null, stack = false): void {
    if (stopped) return;
    if (journal.length === 768) { limits.events = true; return; }
    try {
      journal.push({ type, at: performance.now(), point: point(), detail,
        stack: stack ? text(new NativeError().stack, 2048) : null });
    } catch (caught) { error('capture', caught); }
  }
  function target(value: unknown): string {
    return value === window ? 'window' : value === document.documentElement ? 'html' : value === document.body ? 'body' : 'other';
  }
  function argumentsSummary(args: unknown[]) {
    return args.slice(0, 8).map(value => {
      if (value === null) return { kind: 'null' };
      if (typeof value === 'string') return { kind: 'string', value: text(value, 256) };
      if (typeof value === 'number') return { kind: 'number', value: Number.isFinite(value) ? value : Number.isNaN(value) ? 'NaN' : value > 0 ? 'Infinity' : '-Infinity' };
      if (typeof value === 'boolean') return { kind: 'boolean', value };
      return { kind: typeof value };
    });
  }
  function method(owner: object, name: string, label: string): void {
    const original = getDescriptor(owner, name);
    if (!original || typeof original.value !== 'function') return;
    const delegate = original.value;
    const wrapper = function (this: unknown, ...args: unknown[]) {
      try { capture(`js:${label}.${name}`, { target: target(this), args: argumentsSummary(args), argumentCount: args.length }, true); }
      catch (caught) { error('method-observation', caught); }
      return apply(delegate, this, args);
    };
    try {
      define(owner, name, { ...original, value: wrapper });
      hooks.push({ owner, name, original, wrapper, setter: false, label: `${label}.${name}`, installed: { ...original, value: wrapper } });
    } catch (caught) { error(`install:${label}.${name}`, caught); }
  }
  // Establish cleanup custody before any fallible hook/observer setup.
  define(scope, key, { value: Object.freeze({ finish }) });
  for (const [owner, label] of [[window, 'Window.own'], [Window.prototype, 'Window.prototype'], [Element.prototype, 'Element.prototype']] as const) {
    for (const name of ['scroll', 'scrollTo', 'scrollBy', 'scrollIntoView']) method(owner, name, label);
  }
  method(HTMLElement.prototype, 'focus', 'HTMLElement.prototype');
  for (const name of ['scrollTop', 'scrollLeft']) {
    const original = getDescriptor(Element.prototype, name);
    if (!original?.set) { error(`missing:${name}`, 'Native setter unavailable'); continue; }
    const delegate = original.set;
    const wrapper = function (this: unknown, value: unknown) {
      try { capture(`js:Element.prototype.${name}`, { target: target(this), args: argumentsSummary([value]) }, true); }
      catch (caught) { error('setter-observation', caught); }
      return apply(delegate, this, [value]);
    };
    try {
      define(Element.prototype, name, { ...original, set: wrapper });
      hooks.push({ owner: Element.prototype, name, original, wrapper, setter: true, label: `Element.prototype.${name}`, installed: { ...original, set: wrapper } });
    } catch (caught) { error(`install:${name}`, caught); }
  }
  for (const name of ['scroll', 'scrollend', 'popstate', 'pageshow', 'pagehide', 'hashchange', 'DOMContentLoaded', 'load', 'focusin', 'focusout']) {
    const listener: EventListener = event => capture(`native:${name}`, { target: target(event.target), trusted: event.isTrusted });
    try { apply(nativeAdd, window, [name, listener, { capture: true, passive: true }]); listeners.push([name, listener]); }
    catch (caught) { error(`listener:${name}`, caught); }
  }
  function commit(): void {
    try {
      const current = point();
      const signature = JSON.stringify([current.url, current.mainClass, current.heading]);
      if (signature !== previousCommit) { previousCommit = signature; capture('dom:route-commit'); }
    } catch (caught) { error('commit', caught); }
  }
  try {
    mutation = new NativeMutationObserver(commit);
    mutation.observe(document, { childList: true, subtree: true });
  }
  catch (caught) { error('mutation-install', caught); }
  function frame(): void {
    if (stopped) return;
    if (frames === 1800) { limits.frames = true; return; }
    frames++;
    try {
      const signature = JSON.stringify(point());
      if (signature !== previous) { previous = signature; capture('raf:geometry'); }
      commit();
    } catch (caught) { error('frame', caught); }
    schedule();
  }
  function schedule(): void {
    if (stopped) return;
    try { raf = request(frame); } catch (caught) { error('raf-schedule', caught); }
  }
  function sameDescriptor(current: PropertyDescriptor | undefined, expected: PropertyDescriptor): boolean {
    return !!current && ['value', 'get', 'set', 'writable', 'enumerable', 'configurable'].every(name =>
      Object.prototype.hasOwnProperty.call(current, name) === Object.prototype.hasOwnProperty.call(expected, name)
      && current[name as keyof PropertyDescriptor] === expected[name as keyof PropertyDescriptor]);
  }
  function finish(): ObserverResult {
    if (result) return result;
    capture('observer:finish'); stopped = true;
    try { cancel(raf); } catch (caught) { error('raf-cleanup', caught); }
    try { mutation?.disconnect(); } catch (caught) { error('mutation-cleanup', caught); }
    for (const [name, listener] of listeners) {
      try { apply(nativeRemove, window, [name, listener, { capture: true }]); }
      catch (caught) { error(`listener-cleanup:${name}`, caught); }
    }
    for (const hook of hooks.slice().reverse()) {
      try {
        const current = getDescriptor(hook.owner, hook.name);
        if (!sameDescriptor(current, hook.installed)) { error(`owner-changed:${hook.label}`, 'Later owner preserved'); continue; }
        define(hook.owner, hook.name, hook.original);
      } catch (caught) { error(`hook-cleanup:${hook.label}`, caught); }
    }
    result = { schema: 'COUNTY_PAGINATION_SCROLL_OBSERVER_V1', journal, errors, limits, frames,
      allObserversStopped: errors.length === 0 && !limits.events && !limits.frames && !limits.errors,
      wrappedSurfaces: hooks.map(hook => hook.label) };
    return result;
  }
  for (const name of ['scroll', 'scrollTo', 'scrollBy']) {
    if (!hooks.some(hook => hook.label === `Window.own.${name}` || hook.label === `Window.prototype.${name}`)) error(`missing:Window.${name}`, 'Native method unavailable');
  }
  for (const name of ['scroll', 'scrollTo', 'scrollBy', 'scrollIntoView']) {
    if (!hooks.some(hook => hook.label === `Element.prototype.${name}`)) error(`missing:Element.${name}`, 'Native method unavailable');
  }
  if (!hooks.some(hook => hook.label === 'HTMLElement.prototype.focus')) error('missing:focus', 'Native method unavailable');
  capture('observer:installed'); schedule();
}

export function collectCountyPaginationScrollObserver(): ObserverResult | null {
  if (Object.getOwnPropertyDescriptor(window, '__countyPaginationScrollObserverConflictV1')) return null;
  const descriptor = Object.getOwnPropertyDescriptor(window, '__countyPaginationScrollObserverV1');
  if (!descriptor || descriptor.configurable || descriptor.writable || !descriptor.value || !Object.isFrozen(descriptor.value)) return null;
  const finish = Object.getOwnPropertyDescriptor(descriptor.value, 'finish');
  return finish && typeof finish.value === 'function' ? Reflect.apply(finish.value, descriptor.value, []) as ObserverResult : null;
}

/** Wrap only the existing third case; original failure always stays primary. */
export function withCountyPaginationScrollObserver(
  callback: (args: { page: Page }, testInfo: TestInfo) => Promise<void>,
): (args: { page: Page }, testInfo: TestInfo) => Promise<void> {
  return async function observedCountyPagination({ page }, testInfo) {
    let didThrow = false;
    let primary: unknown;
    let incomplete = false;
    let diagnostic: ObserverResult | null = null;
    await page.addInitScript(installCountyPaginationScrollObserver);
    try { await callback({ page }, testInfo); }
    catch (caught) { didThrow = true; primary = caught; }
    finally {
      try { diagnostic = await page.evaluate(collectCountyPaginationScrollObserver); }
      catch { incomplete = true; }
      incomplete ||= !diagnostic?.allObserversStopped;
      const sidecar = { schema: 'COUNTY_PAGINATION_DIAGNOSTIC_SIDECAR_V1', diagnostic,
        observerIncomplete: incomplete, originalCaseFailed: didThrow,
        scope: 'Bounded main-document owner observations only; no product repair or full acceptance claim.' };
      try {
        const output = testInfo.outputPath('county-pagination-scroll-observer.json');
        mkdirSync(dirname(output), { recursive: true });
        writeFileSync(output, JSON.stringify(sidecar) + '\n', { flag: 'wx' });
        await testInfo.attach('county-pagination-scroll-observer', { path: output, contentType: 'application/json' });
      } catch {
        incomplete = true;
        try { console.error('County pagination scroll observer: sidecar export incomplete'); } catch { /* Original failure remains primary. */ }
      }
    }
    if (didThrow) throw primary;
    if (incomplete) throw new Error('County pagination scroll observer incomplete; inspect diagnostic sidecar and original case result');
  };
}
