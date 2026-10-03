/** Optional browser artifact export; all data is explicitly isolated test data. */
import SocialWorkspace from '@/components/admin/social/SocialWorkspace';
import PageShell from '@/components/layout/PageShell';
import api from '@/lib/api/axios';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { mkdirSync, readFileSync, writeFileSync } from 'fs';
import { resolve } from 'path';
import { accounts, assetId, facebookId, instagramId, post, system, validation } from '../../../tests/socialFixtures';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }), usePathname: () => '/admin/social', useSearchParams: () => new URLSearchParams() }));

test('renders the approved queue/editor/preview direction with ready fixture metadata', async () => {
  let mobile = false;
  const mediaListeners = new Set<() => void>();
  const originalMatchMedia = window.matchMedia;
  window.matchMedia = query => query === '(max-width: 600px)' ? { media: query, get matches() { return mobile; }, onchange: null, addListener: jest.fn(), removeListener: jest.fn(), addEventListener: (_event: string, listener: EventListenerOrEventListenerObject) => mediaListeners.add(listener as () => void), removeEventListener: (_event: string, listener: EventListenerOrEventListenerObject) => mediaListeners.delete(listener as () => void), dispatchEvent: () => true } : originalMatchMedia(query);
  const p = post({ editorial_state: 'pending_review', document: { ...post().document, master: { ...post().document.master, text: 'What does “unsupported expenditure” mean?\n\nThe auditor did not receive sufficient supporting documents for the spending examined. Read the finding, its period and the source context before drawing conclusions.', media: [{ asset_id: assetId, alt_text: 'An evidence-first explainer card', caption_asset_id: null }] }, targets: [{ account_id: facebookId, format: 'image', overrides: {} }, { account_id: instagramId, format: 'image', overrides: {} }] }, references: [{ url: 'https://example.org/source', label: 'Explicit test source reference' }] });
  const result = validation(p);
  (api.get as jest.Mock).mockImplementation(async path => ({ data: path.endsWith('/accounts') ? { accounts } : path.endsWith('/system/status') ? system : path.endsWith('/posts') ? { posts: [p, { ...p, id: '00000000-0000-4000-8000-000000000070', title: 'A county report needs source review' }], total: 2, page: 1, page_size: 20, has_more: false } : p }));
  (api.post as jest.Mock).mockResolvedValue({ data: result });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { container } = render(<QueryClientProvider client={qc}><PageShell title='Social publishing' subtitle='Review the evidence. Shape the message. Choose where it goes.'><SocialWorkspace /></PageShell></QueryClientProvider>);
  const queueButton = await screen.findByRole('button', { name: /What does unsupported expenditure mean/ });
  fireEvent.click(queueButton);
  await screen.findByRole('article', { name: 'Social post composer' });
  fireEvent.click(screen.getByRole('button', { name: 'Save & validate' }));
  await screen.findByText('Server-inspected image/png · 1200 × 630 · 12345 bytes');
  if (process.env.SOCIAL_VISUAL_DIR) {
    const directory = resolve(process.env.SOCIAL_VISUAL_DIR);
    mkdirSync(directory, { recursive: true });
    const css = readFileSync(resolve('components/admin/social/social.module.css'), 'utf8');
    const exportFixture = (filename: string) => {
      container.querySelectorAll('select').forEach(select => Array.from(select.options).forEach(option => { if (option.selected) option.setAttribute('selected', ''); else option.removeAttribute('selected'); }));
      const portal = document.querySelector('[data-social-actions-portal]')?.outerHTML ?? '';
      writeFileSync(resolve(directory, filename), `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Social UI fixture verification</title><link rel="stylesheet" href="global.css"><style>${css}</style></head><body><div style="padding:8px;background:#fff6e5;color:#563d1d;text-align:center">TEST FIXTURES · NO LIVE ACCOUNTS OR PUBLICATION</div>${container.innerHTML}${portal}</body></html>`);
    };
    exportFixture('queue.html');
    mobile = true;
    act(() => Array.from(mediaListeners).forEach(listener => listener()));
    expect(screen.getByRole('button', { name: 'Save draft' }).closest('[data-social-actions-portal]')).toBeInTheDocument();
    exportFixture('queue-mobile.html');
    fireEvent.click(screen.getByRole('button', { name: /^Preview$/ }));
    exportFixture('queue-preview.html');
  }
  window.matchMedia = originalMatchMedia;
});
