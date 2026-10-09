import { existsSync } from 'node:fs';
import { relative, resolve } from 'node:path';
import { legacyEnvironment } from './legacy-e2e-env.mjs';

const frontend = resolve('.');
export const cohorts = Object.freeze([
  { name: 'public', directory: 'e2e', api: 8141, web: 3141,
    fixture: 'legacy_browser_fixture_api.py', health: '/health', workers: 2, timeout: 30000 },
  { name: 'users', directory: 'e2e/admin-users', api: 8151, web: 3151,
    fixture: 'admin_users_browser_fixture.py', health: '/health', workers: 1, timeout: 45000 },
  { name: 'operations', directory: 'e2e/operations', api: 8152, web: 3152,
    fixture: 'admin_operations_browser_fixture.py', health: '/health', workers: 1, timeout: 30000 },
  { name: 'overview-audit', directory: 'e2e/admin-overview-audit', api: 8153, web: 3153,
    fixture: 'admin_overview_audit/browser_api.py', health: '/health', workers: 1, timeout: 45000 },
  { name: 'etl-ui', directory: 'e2e/batch7-etl-ui', api: 8162, web: 3162,
    fixture: 'batch7_etl_ui_fixture.py', health: '/fixture/requests', workers: 1, timeout: 30000 },
  { name: 'coordinator', directory: 'e2e/batch7_coordinator_integration', api: 8163, web: 3163,
    fixture: 'batch7_coordinator_integration_fixture.py', health: '/fixture/health', workers: 1, timeout: 45000 },
].map(cohort => Object.freeze(cohort)));

export function selectedCohort(name) {
  const cohort = cohorts.find(item => item.name === name);
  if (!cohort) throw new Error('An explicit supported browser cohort is required');
  return cohort;
}

export function cohortEnvironment(cohort, source = process.env) {
  cohort = selectedCohort(cohort?.name);
  const env = {
    ...legacyEnvironment(source), BROWSER_TEST_COHORT: cohort.name,
    PYTHONPATH: resolve(frontend, '..', 'backend'), BATCH9_CI_BROWSER: 'true',
    BROWSER_FIXTURE_POSTGRES_PORT: '55494',
    NEXT_PUBLIC_API_URL: `http://127.0.0.1:${cohort.api}`,
    NEXT_PUBLIC_SUPABASE_URL: `http://127.0.0.1:${cohort.api}`,
  };
  if (cohort.name === 'coordinator') Object.assign(env, {
    DATABASE_URL: 'postgresql+psycopg2://batch7_coordinator:batch7-inert-coordinator-local@127.0.0.1:55494/batch7_coordinator',
    BATCH7_COORDINATOR_INTEGRATION: 'true',
    BATCH7_COORDINATOR_ARTIFACTS: resolve(frontend, 'legacy-results/coordinator/fixture'),
    ...(source.BROWSER_TARGET_SHA ? { BROWSER_TARGET_SHA: source.BROWSER_TARGET_SHA,
      BATCH7_COORDINATOR_TARGET_SHA: source.BROWSER_TARGET_SHA } : {}),
    SUPABASE_URL: 'http://127.0.0.1:8163',
    SUPABASE_SERVICE_ROLE_KEY: 'batch7-coordinator-inert-service-key',
    SUPABASE_JWT_SECRET: 'batch7-coordinator-inert-signing-key-for-local-tests',
  });
  return env;
}

export function listedCases(report) {
  if (!report || typeof report.config?.rootDir !== 'string'
      || !Array.isArray(report.suites) || !Array.isArray(report.errors)
      || report.errors.length) throw new Error('Invalid browser collection report');
  const cases = [];
  function visit(suite) {
    if ((suite.suites !== undefined && !Array.isArray(suite.suites)) || !Array.isArray(suite.specs)) {
      throw new Error('Malformed browser suite');
    }
    for (const spec of suite.specs) {
      if (typeof spec.file !== 'string' || !Number.isInteger(spec.line) || spec.line < 1
          || !Number.isInteger(spec.column) || spec.column < 1
          || typeof spec.title !== 'string' || !spec.title || !Array.isArray(spec.tests)
          || spec.tests.length !== 1 || spec.tests[0].projectName !== 'chromium') {
        throw new Error('Malformed or non-Chromium browser case');
      }
      const file = relative(resolve(frontend, 'e2e'), resolve(report.config.rootDir, spec.file));
      if (file.startsWith('..') || !file.endsWith('.spec.ts')
          || !existsSync(resolve(frontend, 'e2e', file))) throw new Error('Browser case source is absent or outside the suite');
      cases.push(JSON.stringify({ file, line: spec.line, column: spec.column, title: spec.title }));
    }
    (suite.suites || []).forEach(visit);
  }
  report.suites.forEach(visit);
  if (!cases.length || new Set(cases).size !== cases.length) {
    throw new Error('Empty or duplicate browser inventory');
  }
  return cases.sort();
}

export function verifyPartition(baseline, groups) {
  if (!Array.isArray(baseline) || !baseline.length || new Set(baseline).size !== baseline.length
      || groups.length !== cohorts.length || groups.some(group => !Array.isArray(group) || !group.length)) {
    throw new Error('Incomplete browser cohort partition');
  }
  const combined = groups.flat().sort();
  if (new Set(combined).size !== combined.length
      || JSON.stringify([...baseline].sort()) !== JSON.stringify(combined)) {
    throw new Error('Browser partition has missing, substituted or duplicate cases');
  }
  return combined.length;
}

export function executionPassed(report, expectedCases, exitCode) {
  const actual = listedCases(report);
  if (!Array.isArray(expectedCases) || !expectedCases.length
      || JSON.stringify(actual) !== JSON.stringify([...expectedCases].sort())) {
    throw new Error('Browser execution omitted or substituted collected cases');
  }
  const counters = ['expected', 'unexpected', 'flaky', 'skipped'].map(key => report.stats?.[key]);
  if (counters.some(value => !Number.isInteger(value) || value < 0)
      || counters.reduce((sum, value) => sum + value, 0) !== actual.length
      || !Number.isInteger(exitCode) || exitCode < 0) {
    throw new Error('Invalid browser execution accounting');
  }
  const observed = { expected: 0, unexpected: 0, flaky: 0, skipped: 0 };
  function count(suite) {
    for (const spec of suite.specs) {
      const test = spec.tests[0];
      const result = test.results?.[0];
      if (!Object.hasOwn(observed, test.status) || test.results?.length !== 1
          || !['passed', 'failed', 'timedOut', 'skipped', 'interrupted'].includes(result?.status)
          || !['passed', 'failed', 'skipped'].includes(test.expectedStatus)
          || (test.status === 'expected' && result.status !== test.expectedStatus)
          || (test.status === 'expected' && result.status === 'skipped')
          || (test.status === 'skipped' && result.status !== 'skipped')
          || (['passed', 'skipped'].includes(result.status)
            && (result.error !== undefined || (result.errors !== undefined
              && (!Array.isArray(result.errors) || result.errors.length))))
          || typeof result.duration !== 'number' || !Number.isFinite(result.duration) || result.duration < 0) {
        throw new Error('Missing or malformed browser execution result');
      }
      observed[test.status]++;
    }
    (suite.suites || []).forEach(count);
  }
  report.suites.forEach(count);
  if (Object.keys(observed).some(key => observed[key] !== report.stats[key])) {
    throw new Error('Browser execution counters contradict case results');
  }
  return exitCode === 0 && report.stats.unexpected === 0 && report.stats.flaky === 0;
}
