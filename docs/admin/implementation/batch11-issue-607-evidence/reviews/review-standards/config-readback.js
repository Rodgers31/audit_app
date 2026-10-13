const fs = require('node:fs');
const crypto = require('node:crypto');
const path = '/app/frontend/node_modules/playwright/lib/common/configLoader.js';
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
(async () => {
  const full = await require(path).loadConfigFromFile('/app/frontend/playwright.ci-cohorts.config.ts');
  const project = full.config.projects.find(p => p.name === 'chromium');
  process.stdout.write(JSON.stringify({ configFile: full.config.configFile, workers: full.config.workers, viewport: project.use.viewport, baseURL: project.use.baseURL, retries: project.retries, configLoaderSha256: sha(path), configSha256: sha('/app/frontend/playwright.ci-cohorts.config.ts'), scope: 'Resolved unchanged configuration readback; does not execute tests or replace the completed browser run' }) + '\n');
})().catch(error => { process.stderr.write(String(error) + '\n'); process.exitCode = 1; });
