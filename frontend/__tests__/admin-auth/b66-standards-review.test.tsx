import React from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import Harness from '@/browser-fixtures/admin-working-paint/Harness';
import api from '@/browser-fixtures/admin-working-paint/api';
import Layout from '@/app/admin/layout';
import Overview from '@/app/admin/page';
import Etl from '@/app/admin/etl/page';
const mockRouter = { replace: jest.fn(), back: jest.fn(), push: jest.fn() };
let mockPathname = '/admin';
jest.mock('next/navigation', () => ({ useRouter: () => mockRouter, usePathname: () => mockPathname, useSearchParams: () => new URLSearchParams() }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => require('@/browser-fixtures/admin-working-paint/auth').useAuth() }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: require('@/browser-fixtures/admin-working-paint/api').default }));
jest.mock('@/lib/supabase/client', () => ({ createClient: () => ({ auth: { onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }) } }) }));
let frames: FrameRequestCallback[] = [];
let mockGet: jest.SpyInstance;
function renderRoute(route = '/admin') {
  mockPathname = route;
  return render(<Harness><Layout>{route === '/admin' ? <Overview /> : <Etl />}</Layout></Harness>);
}
async function advance(ms: number) { await act(async () => { jest.advanceTimersByTime(ms); }); }
function tick() { const batch = frames; frames = []; act(() => batch.forEach(callback => callback(performance.now()))); }
function measurements() { return JSON.parse(document.getElementById('fixture-measurements')!.textContent!); }
beforeEach(() => {
  jest.useFakeTimers(); window.history.replaceState(null, '', '/admin'); frames = [];
  global.PerformanceObserver = class { observe() {} disconnect() {} } as unknown as typeof PerformanceObserver;
  jest.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { frames.push(callback); return frames.length; });
  jest.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
  Object.defineProperty(performance, 'getEntriesByType', { value: jest.fn(() => []), configurable: true });
  jest.spyOn(window, 'getComputedStyle').mockImplementation(element => ({ opacity: (element as HTMLElement).style.opacity || '1' } as CSSStyleDeclaration));
  mockGet = jest.spyOn(api, 'get');
});
afterEach(() => { cleanup(); jest.restoreAllMocks(); jest.useRealTimers(); });
test.each(['restoring', 'citizen', 'expired'])('real guard refuses %s auth without reads or working content', async auth => {
  window.history.replaceState(null, '', `/admin?auth=${auth}`); renderRoute(); await advance(5000); tick();
  expect(mockGet).not.toHaveBeenCalled(); expect(document.querySelector('.page-shell-content')).toBeNull();
  expect(measurements().allVisible).toBe(false); expect(measurements().firstAllVisibleMs).toBeNull();
  if (auth !== 'restoring') expect(mockRouter.replace).toHaveBeenCalledWith('/');
});
test.each(['failed', 'cancelled'])('verified ETL displays unavailable evidence for %s requests', async mode => {
  window.history.replaceState(null, '', `/admin/etl?data=${mode}`); renderRoute('/admin/etl');
  await advance(200); await advance(50); await advance(10);
  expect(mockGet).toHaveBeenCalled();
  expect(screen.getByText('Calendar plan unavailable. Refresh to retry.')).toBeInTheDocument();
  expect(screen.getByText('Could not load execution evidence.')).toBeInTheDocument(); expect(screen.queryByText('0/6')).not.toBeInTheDocument();
});
test('API refuses unlisted/absolute/prototype reads and exposed writes, with abort rejection', async () => {
  for (const path of ['/admin/unlisted', 'https://invalid.example/admin/etl/health', '__proto__', 'constructor']) {
    const result = api.get(path).catch(error => error.message); await advance(40); expect(await result).toBe('Unlisted inert read refused');
  }
  await expect(api.post()).rejects.toThrow('All fixture writes refused');
  for (const method of ['put', 'patch', 'delete']) expect((api as unknown as Record<string, unknown>)[method]).toBeUndefined();
  const controller = new AbortController();
  const pending = api.get('/admin/etl/health', { signal: controller.signal }).catch(error => error.message);
  controller.abort(); expect(await pending).toBe('Inert request cancelled');
  expect(await api.get('/admin/etl/health', { signal: controller.signal }).catch(error => error.message)).toBe('Inert request cancelled');
});
test('empty target inventory cannot produce a successful visibility observation', () => {
  render(<Harness><div className='page-shell-content' /></Harness>); tick();
  expect(measurements().allVisible).toBe(false); expect(measurements().firstAllVisibleMs).toBeNull();
});
test('incomplete inventory cannot certify ETL working content as all visible', () => {
  mockPathname = '/admin/etl'; render(<Harness><div className='page-shell-content'><ul><li>Unrelated item</li></ul></div></Harness>); tick();
  expect(measurements().allVisible).toBe(false);
});

test('loaded actual ETL rows are opaque and inert worker controls remain unavailable', async () => {
  renderRoute('/admin/etl'); await advance(200); await advance(50); await advance(10);
  for (const label of ['treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra']) {
    const text = Array.from(document.querySelectorAll('li')).find(element => element.textContent?.toLowerCase().includes(label));
    expect(text).toBeDefined();
    for (let element: Element | null = text!; element; element = element.parentElement) expect((element as HTMLElement).style.opacity).not.toBe('0');
  }
  for (const button of Array.from(document.querySelectorAll('button')).filter(element => /dispatch|trigger|execute|run now/i.test(element.textContent ?? ''))) expect(button.disabled).toBe(true);
});

test('unmount during slow data aborts pending route reads', async () => {
  window.history.replaceState(null, '', '/admin/etl?data=slow');
  const view = renderRoute('/admin/etl'); await advance(200);
  const signals = mockGet.mock.calls.map(call => call[1]?.signal as AbortSignal | undefined).filter(Boolean);
  expect(signals.length).toBeGreaterThan(0); view.unmount();
  await advance(2000);
  expect(signals.every(signal => signal!.aborted)).toBe(true);
});

test('missing one required ETL heading refuses success even when other expected labels are present', () => {
  mockPathname = '/admin/etl';
  render(<Harness><div className='page-shell-content'><p>Planned today</p><p>Worker evidence</p><p>Planning vs fixed</p></div></Harness>); tick();
  expect(measurements().missing).toEqual(['Sources']);
  expect(measurements().allVisible).toBe(false); expect(measurements().firstAllVisibleMs).toBeNull();
});
test('unsupported route refuses a visibility verdict over otherwise complete ETL content', () => {
  mockPathname = '/admin/etl-extra';
  render(<Harness><div className='page-shell-content'><p>Planned today</p><p>Worker evidence</p><p>Planning vs fixed</p><section><h2>Sources</h2></section></div></Harness>); tick();
  expect(measurements().required).toEqual([]);
  expect(measurements().allVisible).toBe(false); expect(measurements().firstAllVisibleMs).toBeNull();
});
test('SPA navigation starts a new required inventory and clears previous successful timing', () => {
  mockPathname = '/admin/etl';
  const content = <div className='page-shell-content'><p>Planned today</p><p>Worker evidence</p><p>Planning vs fixed</p><section><h2>Sources</h2></section></div>;
  const view = render(<Harness>{content}</Harness>); tick();
  expect(measurements().allVisible).toBe(true); expect(measurements().firstAllVisibleMs).not.toBeNull();
  frames = []; mockPathname = '/admin'; view.rerender(<Harness>{content}</Harness>); tick();
  expect(measurements().route).toBe('/admin'); expect(measurements().missing.length).toBe(6);
  expect(measurements().allVisible).toBe(false); expect(measurements().firstAllVisibleMs).toBeNull();
});
