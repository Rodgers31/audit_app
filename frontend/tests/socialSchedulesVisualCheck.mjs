// Actual component fixture export only. External requests are blocked.
import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';
const directory = resolve('.social-schedule-preview');
const files = new Set(['schedules.html', 'global.css']);
const server = createServer(async (request, response) => {
  const file = new URL(request.url, 'http://localhost').pathname.slice(1);
  if (!files.has(file)) { response.writeHead(404); response.end(); return; }
  try { response.writeHead(200, { 'Content-Type': file.endsWith('.css') ? 'text/css' : 'text/html', 'Cache-Control': 'no-store' }); response.end(await readFile(resolve(directory, file))); }
  catch { response.writeHead(404); response.end(); }
});
await new Promise(done => server.listen(0, '127.0.0.1', done));
const base = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.route('**/*', route => route.request().url().startsWith(`${base}/`) ? route.continue() : route.abort());
  const measurements = [];
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`${base}/schedules.html`);
    const metrics = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, schedulePresent: !!document.querySelector('[aria-label="Schedule management"]'), unlabeled: Array.from(document.querySelectorAll('input,textarea,select')).filter(input => !input.labels?.length && !input.getAttribute('aria-label')).length, smallButtons: Array.from(document.querySelectorAll('.workspace button')).filter(button => button.getBoundingClientRect().width && button.getBoundingClientRect().height < 43.5).map(button => button.textContent) }));
    if (metrics.scrollWidth > width || !metrics.schedulePresent || metrics.unlabeled || metrics.smallButtons.length) throw new Error(JSON.stringify(metrics));
    await page.screenshot({ path: resolve(directory, `schedules-${width}.png`), fullPage: true });
    measurements.push(metrics);
  }
  await writeFile(resolve(directory, 'browser-report.json'), JSON.stringify({ measurements, externalRequests: 'blocked' }, null, 2));
  console.log(JSON.stringify({ measurements, externalRequests: 'blocked' }, null, 2));
} finally { await browser?.close(); await new Promise(done => server.close(done)); }
