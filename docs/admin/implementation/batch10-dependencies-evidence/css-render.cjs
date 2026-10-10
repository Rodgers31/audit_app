'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const local = createRequire(path.resolve(process.argv[2], 'package.json'));

async function main() {
  const browser = await local('@playwright/test').chromium.launch({ headless: true });
  const results = [];
  try {
    for (const css of process.argv.slice(3)) {
      const page = await browser.newPage();
      await page.route('**/*', route => route.abort());
      await page.setContent('<div id="fixture" class="rounded-sm shadow-sm bg-gov-forest text-neutral-text p-4">Existing utility contract</div>');
      await page.addStyleTag({ content: fs.readFileSync(css, 'utf8') });
      const values = await page.locator('#fixture').evaluate(element => {
        const s = getComputedStyle(element);
        return { borderRadius: s.borderRadius, boxShadow: s.boxShadow, padding: s.padding,
          backgroundColor: s.backgroundColor, color: s.color };
      });
      results.push({ css, values });
      await page.close();
    }
    console.log(JSON.stringify({ check: 'rendered-existing-utility-contract', browser: browser.version(), results }, null, 2));
    assert.equal(results.length, 2);
    assert.deepEqual(results[1].values, results[0].values, 'Existing utility render contract changed');
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
