// Actual component fixture export only. External requests are blocked.
import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';
const directory = resolve('.social-schedule-preview');
const files = new Set(['schedules.html', 'history.html', 'attention.html', 'global.css']);
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
  for (const file of ['schedules', 'history', 'attention']) for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`${base}/${file}.html`);
    const metrics = await page.evaluate(name => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, requiredRegionPresent: !!document.querySelector(`[aria-label="${name}"]`), unlabeled: Array.from(document.querySelectorAll('input,textarea,select')).filter(input => !input.labels?.length && !input.getAttribute('aria-label')).length, smallButtons: Array.from(document.querySelectorAll('.workspace button')).filter(button => button.getBoundingClientRect().width && button.getBoundingClientRect().height < 43.5).map(button => button.textContent) }), file === 'schedules' ? 'Schedule management' : file === 'history' ? 'Delivery history' : 'Post queue');
    if (metrics.scrollWidth > width || !metrics.requiredRegionPresent || metrics.unlabeled || metrics.smallButtons.length) throw new Error(JSON.stringify({ file, ...metrics }));
    await page.screenshot({ path: resolve(directory, `${file}-${width}.png`), fullPage: true });
    measurements.push({ file, ...metrics });
  }
  await writeFile(resolve(directory, 'browser-report.json'), JSON.stringify({ measurements, externalRequests: 'blocked' }, null, 2));
  console.log(JSON.stringify({ measurements, externalRequests: 'blocked' }, null, 2));
} finally { await browser?.close(); await new Promise(done => server.close(done)); }
