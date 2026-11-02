'use strict';

// This module only reports terminal job results. It cannot admit or start writers.
const JOBS = [
  ['source_plan', 'Source plan'], ['healthcheck', 'Health check execution'],
  ['migrate', 'Database admission'], ['seed', 'Seeding'], ['bootstrap', 'Bootstrap'],
  ['validate', 'Validation'], ['revalidate', 'Cache / page refresh'],
];
const STATES = new Set(['success', 'failure', 'cancelled', 'skipped']);
const INCIDENT = '<!-- seed-pipeline-incident:v1 -->';

function assess(needs, inputs) {
  const state = key => STATES.has(needs[key]?.result) ? needs[key].result : 'unknown';
  const plan = needs.source_plan?.outputs;
  const plannedBootstrap = state('source_plan') === 'success' && ['true', 'false'].includes(plan?.bootstrap)
    ? plan.bootstrap : null;
  const rows = JOBS.map(([key, label]) => {
    const result = state(key);
    let detail = result;
    let problem = result !== 'success';
    if (result === 'skipped') {
      // Explicit exclusions take precedence over blocked prerequisites. They
      // describe work that was never requested, even on an unsuccessful run.
      let excluded;
      if (key === 'bootstrap' && plannedBootstrap === 'false') excluded = 'not selected by source plan';
      if (key === 'validate' && inputs.run_validation === 'false') excluded = 'validation explicitly disabled';
      if (key === 'revalidate' && inputs.dry_run === 'true') excluded = 'dry run excludes page refresh';
      if (key === 'revalidate' && inputs.run_validation === 'false') excluded = 'validation disabled; page refresh excluded';
      const dependencies = {
        migrate: ['source_plan'], seed: ['migrate'], bootstrap: ['migrate', 'seed'],
        // Validation deliberately uses !cancelled(): seed failure does not
        // excuse a missing validation after admission succeeded.
        validate: ['migrate'], revalidate: ['seed', 'validate'],
      }[key] || [];
      const blocked = dependencies.filter(dep => state(dep) !== 'success');
      if (excluded) { detail = `skipped — intentional: ${excluded}`; problem = false; }
      else if (key === 'bootstrap' && plannedBootstrap === null) detail = 'skipped — unverified plan';
      else if (blocked.length) detail = `skipped — blocked by ${blocked.join(', ')}`;
      else detail = 'skipped — unexpectedly skipped';
    }
    if (key === 'source_plan' && result === 'success' && plannedBootstrap === null) {
      detail = 'success — unverified plan (bootstrap output missing or malformed)'; problem = true;
    }
    return {key, label, result, detail, problem};
  });
  return {rows, problems: rows.filter(row => row.problem)};
}

function healthDescription(needs) {
  const check = needs.healthcheck;
  const outputs = check?.outputs || {};
  if (check?.result !== 'success') {
    const result = STATES.has(check?.result) ? check.result : 'no result';
    return `❔ Unknown — the health check did not finish (${result})`;
  }
  // A partial probe is a measured outcome, not a fallback for missing or
  // malformed outputs. Validate the verdict before interpreting its count.
  if (!['true', 'false'].includes(outputs.has_failures)) return '❔ Unknown — missing or malformed health-check verdict';
  if (outputs.has_failures === 'true') return '⚠️ Some sources were unreachable (may be related)';
  if (typeof outputs.unprobed !== 'string' || !/^(0|[1-9][0-9]{0,4})$/.test(outputs.unprobed)) {
    return '❔ Unknown — missing or malformed unprobed source count';
  }
  if (outputs.unprobed !== '0') {
    return `❔ Partial — ${outputs.unprobed} source(s) not probed before the health-check budget ran out`;
  }
  return '✅ No critical source failures (warnings, if any, are in the health-check job)';
}

async function report({github, context, core, env = process.env}) {
  // Invalid JSON is a reporting failure; never replace it with a healthy run.
  const needs = JSON.parse(env.PIPELINE_NEEDS);
  const suppliedInputs = JSON.parse(env.PIPELINE_INPUTS || '{}');
  // Scheduled events have no event.inputs; toJSON serializes that as null.
  const inputs = suppliedInputs === null ? {} : suppliedInputs;
  if (!needs || Array.isArray(needs) || typeof needs !== 'object' ||
      !inputs || Array.isArray(inputs) || typeof inputs !== 'object') throw new Error('Invalid notification inputs');
  const result = assess(needs, inputs);
  const health = healthDescription(needs);
  const outcome = result.problems.length ? '⚠️ Pipeline completion not verified' : '✅ Pipeline jobs completed as planned';
  const table = '| Job | Result | Interpretation |\n| --- | --- | --- |\n' +
    result.rows.map(row => `| ${row.label} (\`${row.key}\`) | ${row.result} | ${row.detail} |`).join('\n');
  await core.summary.addRaw(`\n### Pipeline outcome\n\n**${outcome}**\n\n${table}\n\n` +
    `**Health Check:** ${health}\n\nJob success confirms execution only; source transport, extraction, freshness and publication require their own receipts.\n`).write();
  if (!result.problems.length) return;
  core.setFailed('Pipeline completion not verified; review the job results in the summary.');

  const scope = {owner: context.repo.owner, repo: context.repo.repo};
  // One managed open incident, updated once per run attempt. Never append a
  // nightly comment stream or close an incident solely from job success.
  // A full first page is ambiguous: fail visibly instead of creating noise.
  const existing = await github.rest.issues.listForRepo({
    ...scope, labels: 'data-pipeline,automated', state: 'open', per_page: 100,
  });
  if (!Array.isArray(existing.data) || existing.data.length >= 100) throw new Error('Pipeline incident lookup exceeded its bounded page');
  const managed = existing.data.filter(issue => !issue.pull_request && typeof issue.body === 'string' && issue.body.startsWith(INCIDENT));
  if (managed.length > 1) throw new Error('Pipeline incident lookup found multiple managed open incidents');
  const attempt = /^\d{1,5}$/.test(env.PIPELINE_RUN_ATTEMPT) ? env.PIPELINE_RUN_ATTEMPT : 'unknown';
  const observation = `<!-- seed-pipeline-observation:${context.runId}:${attempt} -->`;
  if (managed[0]?.body.includes(observation)) return;
  const runUrl = `${context.serverUrl}/${scope.owner}/${scope.repo}/actions/runs/${context.runId}`;
  // The source-plan whitelist is the shell boundary. Reporting also excludes
  // arbitrary dispatch values so refused input cannot inject issue Markdown.
  const rawDomain = inputs.domain || 'all';
  const domain = typeof rawDomain === 'string' && /^[a-z][a-z_]{0,63}$/.test(rawDomain) ? rawDomain : 'unverified selection';
  const event = ['schedule', 'workflow_dispatch'].includes(context.eventName) ? context.eventName : 'unknown';
  const failed = result.problems.map(row => row.label).join(', ');
  const body = `${INCIDENT}\n${observation}\n## Automated Data Pipeline Failure\n\n` +
    `**Failed Steps:** ${failed}\n**Health Check:** ${health}\n` +
    `**Run:** ${runUrl}\n**Attempt:** ${attempt}\n**Triggered by:** ${event}\n**Domain:** ${domain}\n\n${table}\n\n` +
    `### Action Required\n1. Inspect the [workflow run logs](${runUrl}) and admission/source-plan diagnostics before considering any write.\n` +
    `2. If seeding ran, inspect ingestion job and source receipts for domain-level failures.\n` +
    `3. Keep the accepted source revision guard unchanged; a reporting failure never authorizes a retry or activation.\n\n` +
    `This managed incident records the latest unsuccessful run attempt. A repeated attempt adds no duplicate issue or comment. Review recovery before closing it.\n`;
  const title = `Data pipeline failed: ${failed}`.slice(0, 240);
  if (managed.length) await github.rest.issues.update({...scope, issue_number: managed[0].number, title, body});
  else await github.rest.issues.create({...scope, title, body, labels: ['bug', 'data-pipeline', 'automated']});
}

module.exports = {assess, healthDescription, report};
