// Run after the visual Jest export and Tailwind CSS build described in UI_HANDOFF.
// Serves only explicit fixture files on an ephemeral loopback port. Every external
// browser request is blocked; this never connects to app/auth/social APIs.
import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const directory = resolve('.social-preview');
const reference = await readFile(resolve('../docs/social-publishing/design-reference/approved-admin-concept.html'), 'utf8');
await writeFile(resolve(directory, 'approved.html'), `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>${reference}</body></html>`);
const files = new Set(['queue.html', 'queue-mobile.html', 'queue-preview.html', 'global.css', 'approved.html']);
const server = createServer(async (request, response) => {
  const file = new URL(request.url, 'http://localhost').pathname.slice(1);
  if (!files.has(file)) { response.writeHead(404); response.end(); return; }
  try {
    response.writeHead(200, { 'Content-Type': file.endsWith('.css') ? 'text/css; charset=utf-8' : 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    response.end(await readFile(resolve(directory, file)));
  } catch { response.writeHead(404); response.end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const base = `http://127.0.0.1:${server.address().port}`;
let browser;
const report = [];
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.route('**/*', route => route.request().url().startsWith(`${base}/`) ? route.continue() : route.abort());
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`${base}/${width <= 600 ? 'queue-mobile.html' : 'queue.html'}`);
    await page.waitForFunction(() => Array.from(document.querySelectorAll('.ledger-enter')).every(element => Number(getComputedStyle(element).opacity) === 1));
    const metrics = await page.evaluate(() => ({
      width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
      smallButtons: Array.from(document.querySelectorAll('.workspace button')).filter(button => button.getBoundingClientRect().width && button.getBoundingClientRect().height < 43.5).map(button => button.textContent),
      unlabeledInputs: Array.from(document.querySelectorAll('.workspace input, .workspace textarea, .workspace select')).filter(input => !input.labels?.length && !input.getAttribute('aria-label')).length,
      masterVisible: document.querySelector('textarea').getBoundingClientRect().width > 0,
      headingWraps: Array.from(document.querySelectorAll('.editorHeading h2')).every(title => title.scrollWidth <= title.clientWidth),
    }));
    if (metrics.scrollWidth > width || metrics.smallButtons.length || metrics.unlabeledInputs || !metrics.masterVisible || !metrics.headingWraps) throw new Error(`Responsive fixture failed: ${JSON.stringify(metrics)}`);
    await page.screenshot({ path: resolve(directory, `queue-${width}.png`), fullPage: true });
    report.push(metrics);
  }
  await page.setViewportSize({ width: 390, height: 1000 });
  await page.goto(`${base}/queue-mobile.html`);
  await page.waitForFunction(() => Array.from(document.querySelectorAll('.ledger-enter')).every(element => Number(getComputedStyle(element).opacity) === 1));
  const mobileHeader = await page.evaluate(() => {
    document.documentElement.style.scrollBehavior = 'auto';
    scrollTo(0, document.querySelector('.editorHeading').getBoundingClientRect().top + scrollY - 100);
    const title = document.querySelector('.editorHeading h2').getBoundingClientRect();
    const bar = document.querySelector('.actionBar').getBoundingClientRect();
    return { titleTop: title.top, titleBottom: title.bottom, barTop: bar.top, barBottom: bar.bottom, viewport: innerHeight };
  });
  if (mobileHeader.barBottom > mobileHeader.viewport || mobileHeader.barTop < mobileHeader.titleBottom) throw new Error(`Mobile action bar obscures heading: ${JSON.stringify(mobileHeader)}`);
  await page.evaluate(() => { const marker = document.querySelector('body > div'); Object.assign(marker.style, { position: 'fixed', top: '0', left: '0', right: '0', zIndex: '100' }); });
  await page.screenshot({ path: resolve(directory, 'mobile-composer-viewport.png') });
  await page.goto(`${base}/queue-preview.html`);
  await page.waitForFunction(() => Array.from(document.querySelectorAll('.ledger-enter')).every(element => Number(getComputedStyle(element).opacity) === 1));
  if (!await page.getByRole('region', { name: 'Resolved post preview' }).isVisible() || await page.locator('textarea').isVisible()) throw new Error('Mobile Preview state failed to switch panels.');
  await page.screenshot({ path: resolve(directory, 'mobile-preview.png'), fullPage: true });
  await page.keyboard.press('Tab');
  const outline = await page.evaluate(() => ({ width: getComputedStyle(document.activeElement).outlineWidth, style: getComputedStyle(document.activeElement).outlineStyle }));
  if (outline.style === 'none' || parseFloat(outline.width) < 2) throw new Error(`Keyboard focus is not visible: ${JSON.stringify(outline)}`);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${base}/approved.html`);
  await page.locator('section[data-variant="Queue and preview"]').screenshot({ path: resolve(directory, 'approved-queue.png') });
  await writeFile(resolve(directory, 'browser-report.json'), JSON.stringify({ viewports: report, mobileHeader, mobilePreview: 'passed', keyboardFocus: outline, externalRequests: 'blocked' }, null, 2));
  console.log(JSON.stringify({ viewports: report, mobileHeader, mobilePreview: 'passed', keyboardFocus: outline, externalRequests: 'blocked' }, null, 2));
} finally {
  await browser?.close();
  await new Promise(done => server.close(done));
}
