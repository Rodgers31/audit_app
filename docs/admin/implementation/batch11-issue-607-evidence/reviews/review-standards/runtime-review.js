const fs = require('node:fs');
const crypto = require('node:crypto');
const os = require('node:os');
const { chromium } = require('/app/frontend/node_modules/@playwright/test');
const sha = path => crypto.createHash('sha256').update(fs.readFileSync(path)).digest('hex');
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    process.stdout.write(JSON.stringify({ nodeVersion: process.version, nodeExecutable: process.execPath, nodeExecutableSha256: sha(process.execPath), execArgv: process.execArgv, playwrightVersion: require('/app/frontend/node_modules/@playwright/test/package.json').version, nextVersion: require('/app/frontend/node_modules/next/package.json').version, browserVersion: browser.version(), chromiumExecutable: chromium.executablePath(), chromiumExecutableSha256: sha(chromium.executablePath()), platform: os.platform(), architecture: os.arch(), kernel: os.release(), scope: 'Fresh reviewer runtime readback in owned isolated container' }) + '\n');
  } finally {
    await browser.close();
  }
})().catch(error => { process.stderr.write(String(error) + '\n'); process.exitCode = 1; });
