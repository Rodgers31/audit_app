import React from 'react';
import { renderToString } from 'react-dom/server.node';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Overview from '@/app/admin/page';
import Etl from '@/app/admin/etl/page';

let mockPathname = '/admin';
jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: jest.fn(), back: jest.fn() }),
}));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({
  user: { id: 'inert-admin', roles: ['admin'] }, authUser: { id: 'inert-admin' },
  isAuthenticated: true, isLoading: false,
}) }));
jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn() } }));

// Use actual Framer Motion, PageShell and route components. Other page tests
// replace motion with plain elements and cannot observe hidden first frames.
function firstFrame(path: string, page: React.ReactNode) {
  mockPathname = path;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const html = renderToString(<QueryClientProvider client={client}>{page}</QueryClientProvider>);
  client.clear();
  return new DOMParser().parseFromString(html, 'text/html');
}

function expectPainted(element: Element | null) {
  expect(element).not.toBeNull();
  for (let current = element; current; current = current.parentElement) {
    expect((current as HTMLElement).style.opacity).not.toBe('0');
    expect((current as HTMLElement).style.transform).not.toMatch(/translateY\((?!0px)/);
  }
}

test('overview working cards are visible at their first frame after access is verified', () => {
  const document = firstFrame('/admin', <Overview />);
  const cards = Array.from(document.querySelectorAll('.page-shell-content a'))
    .filter(element => element.querySelector('strong'));
  expect(cards.length).toBeGreaterThanOrEqual(5);
  cards.forEach(expectPainted);
});

test('ETL planning cards and source container are visible without another entrance delay', () => {
  const document = firstFrame('/admin/etl', <Etl />);
  for (const label of ['Planned today', 'Worker evidence', 'Planning vs fixed']) {
    expectPainted(Array.from(document.querySelectorAll('p')).find(element => element.textContent === label) ?? null);
  }
  expectPainted(Array.from(document.querySelectorAll('h2')).find(element => element.textContent === 'Sources') ?? null);
});
