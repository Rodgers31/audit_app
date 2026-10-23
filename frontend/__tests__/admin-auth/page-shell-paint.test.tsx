import { renderToString } from 'react-dom/server.node';
import PageShell from '@/components/layout/PageShell';

let mockPathname = '/';
jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ back: jest.fn() }),
}));

function shell() {
  const html = renderToString(
    <PageShell title='Working heading' className='caller-content'>
      <p>Working content</p>
    </PageShell>
  );
  const document = new DOMParser().parseFromString(html, 'text/html');
  const heading = document.querySelector('h1');
  const content = document.querySelector('.page-shell-content');
  expect(heading?.textContent).toBe('Working heading');
  expect(content?.textContent).toBe('Working content');
  expect(content?.classList.contains('caller-content')).toBe(true);
  return { heading: heading!.parentElement!, content: content! };
}

test.each(['/admin', '/admin/', '/admin/etl', '/admin/social/new', '/status'])(
  'access-guarded route %s shows heading and content without an extra entrance fade',
  pathname => {
    mockPathname = pathname;
    const { heading, content } = shell();
    expect(heading.classList.contains('ledger-enter')).toBe(false);
    expect(content.classList.contains('ledger-enter')).toBe(false);
    expect(content.classList.contains('ledger-enter-delayed')).toBe(false);
  }
);

test.each(['/', '/counties', '/administrator', '/admin-tools', '/status-extra', '/statuses', '/status/child'])(
  'public or unrelated route %s retains its existing entrance animation',
  pathname => {
    mockPathname = pathname;
    const { heading, content } = shell();
    expect(heading.classList.contains('ledger-enter')).toBe(true);
    expect(content.classList.contains('ledger-enter')).toBe(true);
    expect(content.classList.contains('ledger-enter-delayed')).toBe(true);
  }
);
