import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { lstatSync, readFileSync, readdirSync, realpathSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const packageRoot = dirname(fileURLToPath(import.meta.url));
const repository = resolve(packageRoot, '../../../..');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const baseCommit = 'f6c31e271297eece52f34102dc40a1e2ed7069a8';
const baseTree = '69ddfad6deb814dd08fdaee2db2d512d73e14c78';
const targetedRecords = [
  ['original-linux-20', 20, 'positive-diagnostic', 'run_record.py'],
  ['probe-linux-cpu1', 6, 'positive-diagnostic', 'run_record_v2.py'],
  ['probe-linux-cpu8', 10, 'positive-diagnostic', 'run_record_v2.py'],
  ['probe-native-absent-negative', 1, 'negative-detector', 'run_record_v2.py'],
  ['probe-chunk-delay1000', 10, 'positive-diagnostic', 'run_record_v2.py'],
  ['original-node22-linux-100', 100, 'observed-precondition-failure', 'run_record_v3.py'],
];
const requireCondition = (condition, message) => {
  if (!condition) throw new Error(message);
};

function inside(root, path) {
  requireCondition(typeof path === 'string' && path.length > 0 && !isAbsolute(path), 'Invalid archive path');
  requireCondition(!path.split(/[\\/]/).includes('..'), 'Archive path traversal');
  const target = resolve(root, path);
  const actual = realpathSync(target);
  requireCondition(!relative(realpathSync(root), actual).startsWith('..'), 'Archive path escapes package');
  requireCondition(lstatSync(target).isFile() && !lstatSync(target).isSymbolicLink(), 'Archive must be a regular file');
  return target;
}

function dataFiles(root) {
  const directory = resolve(root, 'data');
  requireCondition(lstatSync(directory).isDirectory() && !lstatSync(directory).isSymbolicLink(), 'Archive directory symlinks are refused');
  const files = [];
  const visit = directory => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = resolve(directory, entry.name);
      requireCondition(!entry.isSymbolicLink(), 'Archive symlinks are refused');
      if (entry.isDirectory()) visit(path);
      else {
        requireCondition(entry.isFile(), 'Unexpected archive entry');
        files.push(relative(root, path));
      }
    }
  };
  visit(directory);
  return files.sort();
}

function allTests(report, instrumented) {
  requireCondition(Array.isArray(report.errors) && report.errors.length === 0 && Array.isArray(report.suites), 'Invalid execution report');
  const tests = [];
  const visit = suite => {
    requireCondition(Array.isArray(suite.specs), 'Invalid suite');
    for (const spec of suite.specs) {
      requireCondition(spec.file === (instrumented ? 'probe.spec.ts' : 'smart-back.spec.ts') && spec.line === (instrumented ? 73 : 72) && spec.column === 7 && spec.title === 'scroll position is roughly preserved after smart-back', 'Wrong targeted case identity');
      requireCondition(Array.isArray(spec.tests) && spec.tests.length > 0, 'Empty test specification');
      for (const test of spec.tests) {
        requireCondition(test.projectName === 'chromium' && test.expectedStatus === 'passed', 'Unexpected targeted test');
        requireCondition(Array.isArray(test.results) && test.results.length === 1 && test.results[0].retry === 0, 'Missing or retried targeted result');
        requireCondition(Number.isFinite(test.results[0].duration) && test.results[0].duration >= 0, 'Invalid targeted duration');
        if (test.results[0].status === 'passed') {
          requireCondition(test.results[0].error === undefined && (test.results[0].errors === undefined || (Array.isArray(test.results[0].errors) && test.results[0].errors.length === 0)), 'Passing result contains an error');
        }
        tests.push(test);
      }
    }
    if (suite.suites !== undefined) {
      requireCondition(Array.isArray(suite.suites), 'Invalid nested suites');
      suite.suites.forEach(visit);
    }
  };
  report.suites.forEach(visit);
  requireCondition(tests.length > 0, 'Empty targeted execution');
  const counters = ['expected', 'unexpected', 'skipped', 'flaky'].map(key => report.stats?.[key]);
  requireCondition(counters.every(n => Number.isInteger(n) && n >= 0) && counters.reduce((a, b) => a + b) === tests.length, 'Contradictory targeted counters');
  return tests;
}

/** Validates the published archive. Success means integrity, never a scroll fix. */
export async function verifyPackage(root = packageRoot, repo = repository) {
  const manifest = JSON.parse(readFileSync(resolve(root, 'manifest.json'), 'utf8'));
  requireCondition(manifest.schema === 1 && manifest.issue === 601 && manifest.status === 'unresolved', 'The issue must remain unresolved');
  requireCondition(manifest.target_commit === baseCommit && manifest.target_tree === baseTree, 'Wrong author source identity');
  requireCondition(Array.isArray(manifest.files) && manifest.files.length > 0, 'Empty archive manifest');
  const paths = manifest.files.map(entry => entry.path);
  requireCondition(new Set(paths).size === paths.length, 'Duplicate archive paths');
  requireCondition(JSON.stringify([...paths].sort()) === JSON.stringify(dataFiles(root)), 'Unlisted or omitted archive files');
  // This is one frozen historical publication, not a general-purpose receipt
  // validator. Pin all required raw inputs, including instrumentation/runtime
  // files and command receipts, even if a caller recomputes their checksums.
  const rawCensus = JSON.stringify(manifest.files.map(({ path, compression, input_sha256 }) => ({ path, compression, input_sha256 })).sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  requireCondition(digest(rawCensus) === '5de10e5b0fa1ec05f12ecc8c112cf65d0837ee2add58626112975ef0e5ba2fb9', 'Frozen raw-input census changed');
  const bytes = new Map();
  for (const entry of manifest.files) {
    requireCondition(/^data\//.test(entry.path) && entry.compression === 'gzip' && /^[a-f0-9]{64}$/.test(entry.sha256), 'Invalid archive identity');
    const stored = readFileSync(inside(root, entry.path));
    requireCondition(digest(stored) === entry.sha256, `Archive hash mismatch: ${entry.path}`);
    const raw = gunzipSync(stored);
    requireCondition(digest(raw) === entry.input_sha256, `Input hash mismatch: ${entry.path}`);
    bytes.set(entry.path, raw);
  }
  const json = path => {
    requireCondition(bytes.has(path), `Required archive absent: ${path}`);
    return JSON.parse(bytes.get(path).toString('utf8'));
  };
  requireCondition(manifest.generated_by === 'data/publisher.py.gz' && bytes.has(manifest.generated_by) && digest(bytes.get(manifest.generated_by)) === manifest.generator_sha256, 'Archived publisher identity mismatch');
  requireCondition(manifest.sources && !Array.isArray(manifest.sources) && typeof manifest.sources === 'object', 'Missing source identities');
  const census = JSON.stringify(Object.fromEntries(Object.entries(manifest.sources).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)));
  // Pin the original consumed-source census, not a caller-selected subset.
  requireCondition(digest(census) === '883610c29551c60f51f6b58bdecdcb94e943139fcaa3a58938469088debdf42a', 'Incomplete or changed source census');
  for (const [path, expected] of Object.entries(manifest.sources)) {
    requireCondition(digest(readFileSync(inside(repo, path))) === expected, `Published source drift: ${path}`);
  }
  const verifyReceipt = (receipt, generator, log, expectedExit) => {
    requireCondition(receipt.target_commit === baseCommit && receipt.target_tree === baseTree, 'Wrong receipt source identity');
    requireCondition(Array.isArray(receipt.source_changed_during_run) && receipt.source_changed_during_run.length === 0 && receipt.timeout === false && receipt.generator_unchanged === true && receipt.child_exit === expectedExit && receipt.verification_exit === expectedExit, 'Receipt drift, timeout or exit mismatch');
    requireCondition(bytes.has(generator) && digest(bytes.get(generator)) === receipt.generator_sha256 && receipt.generated_by?.endsWith('/' + generator.slice(5, -3)), 'Receipt generator mismatch');
    requireCondition(bytes.has(log) && digest(bytes.get(log)) === receipt.log_sha256 && receipt.log === log.slice(5, -3), 'Receipt log mismatch');
    for (const [path, expected] of Object.entries(manifest.sources)) {
      requireCondition(receipt.source_hashes?.[path] === expected, `Receipt consumed-source mismatch: ${path}`);
    }
  };
  const historical = json(manifest.historical_run);
  requireCondition(historical.headSha === 'b70996e9e1e28f7e6b445f0d3c41be3681fadd61' && historical.attempt === 1, 'Wrong historical execution');
  requireCondition(historical.jobs.some(job => job.databaseId === 114085507802 && job.conclusion === 'failure'), 'Historical browser failure missing');
  requireCondition(bytes.has(manifest.historical_trace) && digest(bytes.get(manifest.historical_trace)) === '75522647fc9dbe493b54c8670e79baabf8c67e1a2fc86f17886e9e67963572b4', 'Wrong original trace');

  {
    const inventory = json(manifest.inventory);
    requireCondition(digest(bytes.get(manifest.inventory)) === '4833cfef43e7856b3938103c61a42637f40f42dba356f54db5aca5bccdc9e4ba', 'Original inventory identity changed');
    const parent = json('data/full-original-chromium.json.gz');
    verifyReceipt(parent, 'data/run_record_v3.py.gz', 'data/full-original-chromium.log.gz', 0);
    requireCondition(parent.source_hashes?.[parent.command?.[1]] === digest(bytes.get('data/run_full.py.gz')), 'Full runner consumed-source mismatch');
    verifyReceipt(json('data/original-inventory.json.gz'), 'data/run_record_v2.py.gz', 'data/original-inventory.log.gz', 0);
    requireCondition(inventory.total === 323, 'Original inventory changed');
    requireCondition(Array.isArray(manifest.cohorts) && manifest.cohorts.length === inventory.cohorts.length, 'Incomplete original cohort records');
    requireCondition(new Set(manifest.cohorts.map(c => c.name)).size === inventory.cohorts.length, 'Duplicate cohort records');
    let passed = 0;
    let skipped = 0;
    const cohortInputs = [];
    for (const cohort of manifest.cohorts) {
      const expected = inventory.cohorts.find(c => c.name === cohort.name);
      requireCondition(expected, 'Unknown cohort');
      const report = json(cohort.report);
      const receipt = json(cohort.receipt);
      requireCondition(receipt.cohort === cohort.name && receipt.child_exit === 0 && receipt.verification_exit === 0 && receipt.error === '' && typeof receipt.readback === 'string', `Invalid cohort execution: ${cohort.name}`);
      const readback = JSON.parse(receipt.readback);
      requireCondition(readback.passed === true && JSON.stringify(readback.stats) === JSON.stringify(report.stats), 'Cohort execution diagnostic mismatch');
      const verifyRetries = suite => {
        for (const spec of suite.specs) for (const test of spec.tests) requireCondition(test.results?.length === 1 && test.results[0].retry === 0, 'Original result was retried');
        (suite.suites ?? []).forEach(verifyRetries);
      };
      report.suites.forEach(verifyRetries);
      // Archived reports retain their actual container paths. Only the known
      // /app/frontend mount prefix is translated for local source existence
      // checks; case names, results and the lossless archive are unchanged.
      requireCondition(/^\/app\/frontend\/e2e(?:\/|$)/.test(report.config?.rootDir), 'Unexpected archived source root');
      const localReport = structuredClone(report);
      localReport.config.rootDir = resolve(repo, 'frontend', relative('/app/frontend', report.config.rootDir));
      cohortInputs.push({ report: localReport, expected: expected.cases, exit: receipt.child_exit });
      passed += report.stats.expected;
      skipped += report.stats.skipped;
    }
    const parser = pathToFileURL(resolve(repo, 'frontend/scripts/ci-browser-cohorts.mjs')).href;
    const child = `import {executionPassed,verifyPartition} from ${JSON.stringify(parser)};let raw='';for await(const chunk of process.stdin)raw+=chunk;const {inventory,cohorts}=JSON.parse(raw);if(verifyPartition(inventory.baseline_cases,inventory.cohorts.map(c=>c.cases))!==323||!cohorts.every(c=>executionPassed(c.report,c.expected,c.exit)))throw Error('Original cohort execution refused');console.log('Original cohort execution verified');`;
    const readback = execFileSync(process.execPath, ['--input-type=module', '-e', child], {
      cwd: resolve(repo, 'frontend'), input: JSON.stringify({ inventory, cohorts: cohortInputs }),
      encoding: 'utf8', timeout: 15000, maxBuffer: 1024 * 1024,
    });
    requireCondition(readback.trim() === 'Original cohort execution verified', 'Missing parser execution diagnostic');
    requireCondition(passed === 312 && skipped === 11, 'Original pass/fixme inventory changed');
    requireCondition(Array.isArray(manifest.targets) && manifest.targets.length === targetedRecords.length, 'Missing targeted controls');
    const targetNames = new Set();
    for (const target of manifest.targets) {
      requireCondition(!targetNames.has(target.name), 'Duplicate targeted control');
      targetNames.add(target.name);
      const identity = targetedRecords.find(([name]) => name === target.name);
      requireCondition(identity && target.count === identity[1] && target.role === identity[2] && target.report === `data/${target.name}-report.json.gz` && target.receipt === `data/${target.name}-receipt.json.gz` && target.generator === `data/${identity[3]}.gz`, 'Wrong targeted control identity');
      const report = json(target.report);
      const receipt = json(target.receipt);
      verifyReceipt(receipt, target.generator, `data/${target.name}.log.gz`, target.role === 'positive-diagnostic' ? 0 : 1);
      const tests = allTests(report, target.name.startsWith('probe-'));
      requireCondition(Number.isInteger(target.count) && target.count > 0 && tests.length === target.count, 'Targeted case count mismatch');
      if (target.role === 'negative-detector') {
        requireCondition(target.count === 1 && receipt.child_exit === 1 && report.stats.unexpected === 1 && report.stats.expected === 0, 'Native absence control did not fail');
        const test = tests[0];
        const result = test.results[0];
        const capture = result.attachments.find(a => a.name === 'scroll-events');
        requireCondition(test.status === 'unexpected' && result.status === 'failed' && capture?.body, 'Negative execution was not an assertion failure');
        const observed = JSON.parse(Buffer.from(capture.body, 'base64').toString());
        const message = result.error.message.replace(/\u001b\[[0-9;]*m/g, '');
        requireCondition(observed.nativeAbsent === true && observed.events.length > 0 && observed.events.at(-1).y === 0 && /Expected:\s*>\s*100/.test(message), 'Wrong negative diagnostic');
      } else if (target.role === 'observed-precondition-failure') {
        requireCondition(target.name === 'original-node22-linux-100' && target.count === 100 && receipt.child_exit === 1 && report.stats.expected === 99 && report.stats.unexpected === 1 && report.stats.skipped === 0 && report.stats.flaky === 0, 'Wrong precondition execution');
        const failures = tests.filter(t => t.status === 'unexpected');
        requireCondition(failures.length === 1 && tests.filter(t => t.status === 'expected' && t.results[0].status === 'passed').length === 99, 'Contradictory precondition results');
        const result = failures[0].results[0];
        const message = result.error?.message?.replace(/\u001b\[[0-9;]*m/g, '') ?? '';
        requireCondition(result.status === 'failed' && result.error?.location?.line === 38 && /toHaveURL/.test(message) && /p=2/.test(message) && /gotoPageNOfCountiesList/.test(result.error?.stack ?? ''), 'Wrong precondition diagnostic');
        requireCondition(bytes.has('data/node22-precondition-trace.zip.gz') && digest(bytes.get('data/node22-precondition-trace.zip.gz')) === '632bd83708061ba281d908c4b1ad40acb4db5707277ce8f88ca5b150b8cc9585', 'Wrong precondition trace');
      } else {
        requireCondition(target.role === 'positive-diagnostic' && receipt.child_exit === 0 && report.stats.expected === target.count && report.stats.unexpected === 0 && report.stats.flaky === 0 && report.stats.skipped === 0, 'Invalid positive diagnostic');
        requireCondition(tests.every(t => t.status === 'expected' && t.results[0].status === 'passed'), 'Positive diagnostic contains a failure');
      }
    }
    requireCondition(targetNames.has('probe-native-absent-negative') && targetNames.has('original-linux-20') && targetNames.has('original-node22-linux-100'), 'Required detector controls missing');
    return { archive_integrity: 'verified', issue_601: 'unresolved', original_inventory: 323, passed, existing_fixmes: skipped, targeted_records: manifest.targets.length };
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { console.log(JSON.stringify(await verifyPackage())); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
