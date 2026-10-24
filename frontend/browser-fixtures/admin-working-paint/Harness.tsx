'use client';

import React, { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FixtureAuth } from './auth';
import { usePathname } from 'next/navigation';

/** DOM-visible diagnostics: CUA needs no credentials or runtime introspection. */
function Measurements() {
  const pathname = usePathname();
  useEffect(() => {
    let frame = 0;
    let started: number | null = null;
    const deadline = performance.now() + 4000;
    let firstAllVisibleMs: number | null = null;
    let first: unknown = null;
    const candidates: unknown[] = [];
    const output = document.getElementById('fixture-measurements')!;
    const required = pathname === '/admin'
      ? ['Ingestion (last 7 days)', 'ETL today', 'ETL scheduler calculation', 'Users', 'Social publishing', 'Audit evidence (30 days)']
      : pathname === '/admin/etl' ? ['Planned today', 'Worker evidence', 'Planning vs fixed', 'Sources'] : [];
    const observer = new PerformanceObserver(list => {
      for (const item of list.getEntries()) {
        const entry = item as PerformanceEntry & { element?: Element; size?: number };
        candidates.push({ startTime: entry.startTime, size: entry.size,
          tag: entry.element?.tagName ?? null,
          applicationContent: !!entry.element?.closest('.page-shell-content'),
          text: entry.element?.tagName === 'IMG' ? null : entry.element?.textContent?.slice(0, 80),
        });
      }
    });
    observer.observe({ type: 'largest-contentful-paint', buffered: true });
    const opacity = (element: Element) => {
      let value = 1;
      for (let current: Element | null = element; current; current = current.parentElement)
        value *= Number(getComputedStyle(current).opacity);
      return value;
    };
    const tick = () => {
      const content = document.querySelector('.page-shell-content');
      const targets = content ? Array.from(content.querySelectorAll('a h3, section h2, li, p'))
        .filter(element => element.matches('a h3, section h2, li') ||
          ['Planned today', 'Worker evidence', 'Planning vs fixed'].includes(element.textContent ?? '')) : [];
      if (targets.length && started === null) started = performance.now();
      const values = targets.map(element => ({ text: element.textContent?.slice(0, 80), opacity: opacity(element) }));
      if (targets.length && first === null) first = values;
      const missing = required.filter(label => !values.some(value => value.text === label));
      const allVisible = required.length > 0 && missing.length === 0 && values.every(value => value.opacity === 1);
      const elapsed = started === null ? null : performance.now() - started;
      if (allVisible && firstAllVisibleMs === null) firstAllVisibleMs = elapsed;
      output.textContent = JSON.stringify({
        scope: 'inert actual-route fixture; not field FCP/LCP acceptance',
        route: pathname, required, missing, viewport: { width: innerWidth, height: innerHeight },
        visibility: document.visibilityState, firstFrame: first,
        allVisible, firstAllVisibleMs, elapsedMs: elapsed, candidates,
        paints: performance.getEntriesByType('paint').map(p => ({ name: p.name, startTime: p.startTime })),
      });
      // Keep the observation bounded; a nonempty target inventory is required.
      if (performance.now() < deadline && (started === null || elapsed! < 1800)) frame = requestAnimationFrame(tick);
      else observer.disconnect();
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, [pathname]);
  return <details><summary>Fixture measurements</summary><pre id='fixture-measurements'>pending</pre></details>;
}

export default function Harness({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: {
    retry: false, gcTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false,
  } } }));
  return <QueryClientProvider client={client}><FixtureAuth>
    <p>INERT ADMIN ROUTE FIXTURE · no provider, account, backend or worker connection</p>
    <Measurements />
    {children}
  </FixtureAuth></QueryClientProvider>;
}
