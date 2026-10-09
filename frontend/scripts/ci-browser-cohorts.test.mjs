import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolve } from 'node:path';
import { cohorts, cohortEnvironment, executionPassed, listedCases, selectedCohort, verifyPartition } from './ci-browser-cohorts.mjs';

const report = () => ({
  config: { rootDir: resolve('e2e') }, errors: [],
  suites: [{ specs: [{ file: 'home.spec.ts', line: 1, column: 1, title: 'fixture case',
    tests: [{ projectName: 'chromium', expectedStatus: 'passed', status: 'expected',
      results: [{ status: 'passed', duration: 1 }] }] }] }],
  stats: { expected: 1, unexpected: 0, flaky: 0, skipped: 0 },
});

test('complete partition refuses omissions, substitutions, duplicates and empty cohorts', () => {
  const baseline = cohorts.map(cohort => cohort.name);
  const groups = baseline.map(name => [name]);
  assert.equal(verifyPartition(baseline, groups), 6);
  for (const bad of [[], groups.slice(1), [...groups.slice(1), []],
    [...groups.slice(1), [baseline[1]]], [...groups.slice(1), ['substituted']]]) {
    assert.throws(() => verifyPartition(baseline, bad));
  }
  assert.throws(() => verifyPartition([], groups));
  assert.throws(() => verifyPartition([...baseline, baseline[0]], groups));
});

test('configuration rejects unknown ownership and strips ambient provider credentials', () => {
  for (const value of [undefined, null, '', true, 'unknown']) assert.throws(() => selectedCohort(value));
  const env = cohortEnvironment({ name: 'coordinator', api: 'remote.invalid' }, {
    PATH: '/usr/bin', DATABASE_URL: 'production.invalid', SUPABASE_SERVICE_ROLE_KEY: 'ambient-secret',
    BROWSER_TARGET_SHA: 'a'.repeat(40),
  });
  assert.equal(env.NEXT_PUBLIC_API_URL, 'http://127.0.0.1:8163');
  assert.equal(env.SUPABASE_SERVICE_ROLE_KEY, 'batch7-coordinator-inert-service-key');
  assert.equal(env.BATCH7_COORDINATOR_TARGET_SHA, 'a'.repeat(40));
  assert.equal(env.BROWSER_TARGET_SHA, 'a'.repeat(40));
  assert.ok(!JSON.stringify(env).includes('ambient-secret'));
  assert.ok(!JSON.stringify(env).includes('production.invalid'));
});

test('collection refuses absent, empty, malformed and non-Chromium source records', () => {
  assert.equal(listedCases(report()).length, 1);
  for (const value of [null, {}, { ...report(), suites: [] }, { ...report(), errors: [{}] },
    { ...report(), suites: [{ specs: null }] }]) assert.throws(() => listedCases(value));
  for (const file of ['absent.spec.ts', '../outside.spec.ts']) {
    const value = report(); value.suites[0].specs[0].file = file;
    assert.throws(() => listedCases(value));
  }
  const wrongProject = report(); wrongProject.suites[0].specs[0].tests[0].projectName = 'webkit';
  assert.throws(() => listedCases(wrongProject));
  const duplicate = report(); duplicate.suites[0].specs.push(duplicate.suites[0].specs[0]);
  assert.throws(() => listedCases(duplicate));
  for (const column of [NaN, Infinity, -1, 0, true, false, null, undefined, '1']) {
    const value = report(); value.suites[0].specs[0].column = column;
    assert.throws(() => listedCases(value));
  }
});

test('execution success requires every collected case, valid counts and successful child exit', () => {
  const value = report(); const cases = listedCases(value);
  assert.equal(executionPassed(value, cases, 0), true);
  assert.equal(executionPassed(value, cases, 1), false);
  assert.throws(() => executionPassed(value, [], 0));
  assert.throws(() => executionPassed(value, ['substituted'], 0));
  for (const counter of [NaN, Infinity, -1, true, '1', null]) {
    const bad = report(); bad.stats.expected = counter;
    assert.throws(() => executionPassed(bad, cases, 0));
  }
  for (const code of [NaN, Infinity, -1, true, '0', null]) {
    assert.throws(() => executionPassed(value, cases, code));
  }
  const falseGreen = report(); falseGreen.stats.expected = 0; falseGreen.stats.unexpected = 1;
  falseGreen.suites[0].specs[0].tests[0].status = 'unexpected';
  falseGreen.suites[0].specs[0].tests[0].results[0].status = 'failed';
  assert.equal(executionPassed(falseGreen, cases, 0), false);
  const noExecution = report(); noExecution.stats.expected = 0;
  assert.throws(() => executionPassed(noExecution, cases, 0));
  const missingResult = report(); missingResult.suites[0].specs[0].tests[0].results = [];
  assert.throws(() => executionPassed(missingResult, cases, 0));
  const contradictory = report(); contradictory.suites[0].specs[0].tests[0].results[0].status = 'failed';
  assert.throws(() => executionPassed(contradictory, cases, 0));
  const disguisedSkip = report();
  disguisedSkip.suites[0].specs[0].tests[0].expectedStatus = 'skipped';
  disguisedSkip.suites[0].specs[0].tests[0].results[0].status = 'skipped';
  assert.throws(() => executionPassed(disguisedSkip, cases, 0));
  const skipError = report();
  skipError.stats.expected = 0; skipError.stats.skipped = 1;
  skipError.suites[0].specs[0].tests[0].status = 'skipped';
  skipError.suites[0].specs[0].tests[0].results[0].status = 'skipped';
  skipError.suites[0].specs[0].tests[0].results[0].errors = [{ message: 'interrupted' }];
  assert.throws(() => executionPassed(skipError, cases, 0));
});
