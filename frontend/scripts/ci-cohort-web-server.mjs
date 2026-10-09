import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { cohortEnvironment, selectedCohort } from './ci-browser-cohorts.mjs';

for (const name of ['.env', '.env.local', '.env.production', '.env.production.local']) {
  if (existsSync(name)) throw new Error(`Synthetic browser build refuses ${name}; use a clean checkout`);
}
const cohort = selectedCohort(process.env.BROWSER_TEST_COHORT);
const env = cohortEnvironment(cohort);
console.log(`Browser cohort=${cohort.name} API=127.0.0.1:${cohort.api} frontend=127.0.0.1:${cohort.web} production-build=true synthetic=true`);
let child;
const run = args => new Promise((resolve, reject) => {
  child = spawn(process.execPath, ['node_modules/next/dist/bin/next', ...args], { env, stdio: 'inherit' });
  child.once('error', reject);
  child.once('exit', code => resolve(code ?? 1));
});
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child?.kill(signal));
const built = await run(['build']);
process.exitCode = built === 0
  ? await run(['start', '--hostname', '127.0.0.1', '--port', String(cohort.web)]) : built;
