'use strict';

// Bounded run-report consumer and cache preflight. It cannot admit or start ingestion writers.
const JOBS = [
  ['source_plan', 'Source plan'], ['healthcheck', 'Health check execution'],
  ['migrate', 'Database admission'], ['seed', 'Seeding'], ['bootstrap', 'Bootstrap'],
  ['validate', 'Validation'], ['revalidate', 'Cache / page refresh'],
];
const STATES = new Set(['success', 'failure', 'cancelled', 'skipped']);
const INCIDENT = '<!-- seed-pipeline-incident:v1 -->';

const DOMAINS = new Set(['audits','counties_budget','county_officials','debt_timeline','economic_indicators',
  'fiscal_summary','imf_weo','learning_hub','national_budget','national_debt','national_gdp','pending_bills',
  'population','revenue_by_source','stalled_projects','cra','opendata','county_borrowing']);
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const count = v => Number.isSafeInteger(v) && v >= 0 && v < 1e18;
const keys = (v, names) => object(v) && Object.keys(v).sort().join('|') === names.slice().sort().join('|');
const hex = (v,n) => typeof v === 'string' && new RegExp(`^[0-9a-f]{${n}}$`).test(v);

function validRetention(t) {
  if (!object(t)) return false;
  if (t.state === 'unverified') return keys(t,['state']);
  const names=['state','observed','retained','missing','recovered','retry_requests'];
  if (!keys(t,names) && !keys(t,[...names,'diagnostics'])) return false;
  if (![t.observed,t.retained,t.missing,t.recovered,t.retry_requests].every(v=>count(v) && v<=1000000) ||
      t.observed !== t.retained+t.missing || t.recovered>Math.min(t.retained,t.retry_requests) ||
      t.state !== (t.missing ? 'missing_bytes' : t.observed ? 'confirmed' : 'not_observed') ||
      !t.observed && t.retry_requests || t.retry_requests && !t.missing && !t.recovered) return false;
  if ('diagnostics' in t) {
    const vocabulary={retained_pdf_restore:['matched','unconfirmed','context_refused','source_refused','origin_missing','origin_invalid','origin_stale','origin_changed','edition_changed','destination_changed','readback_mismatch','authority_refused_unknown','storage_failed','unexpected_error'],
      local_pdf_fallback:['bytes_retained','bytes_missing','metadata_conflict']};
    if (!object(t.diagnostics) || Object.keys(t.diagnostics).length===0) return false;
    let total=0,failures=0;
    for (const [phase,reasons] of Object.entries(t.diagnostics)) {
      if (!Object.hasOwn(vocabulary,phase) || !object(reasons) || !Object.keys(reasons).length) return false;
      for (const [reason,n] of Object.entries(reasons)) {
        if (!vocabulary[phase].includes(reason) || !count(n) || n<1 || n>1000000) return false;
        total+=n;
        if (reason !== (phase==='retained_pdf_restore' ? 'matched' : 'bytes_retained')) failures+=n;
      }
    }
    if (total>t.observed || failures>t.missing) return false;
  }
  return true;
}

function currentRun(needs, context) {
  const raw = needs.seed?.outputs?.report;
  if (typeof raw !== 'string' || raw.length > 60000) return null;
  let r;
  try { r = JSON.parse(raw); } catch { return null; }
  if (!keys(r,['version','generator_sha256','source_sha','schema_head','plan_sha256','selected_domains','dry_run','bootstrap_selected','job_floor','run_id','run_attempt','cli_executed','cli_exit_zero','cli_exit','classification','cache_eligible','refusals','jobs']) || r.version !== 1 || !hex(r.generator_sha256,64) || !hex(r.source_sha,40) || !hex(r.plan_sha256,64) ||
      r.schema_head !== 'a756b20a0001' || typeof r.dry_run !== 'boolean' ||
      typeof r.bootstrap_selected !== 'boolean' || !count(r.job_floor) ||
      typeof r.cli_executed !== 'boolean' || typeof r.cli_exit_zero !== 'boolean' ||
      !(r.cli_exit === null || count(r.cli_exit) && r.cli_exit <= 255) || r.cli_exit_zero !== (r.cli_exit === 0) ||
      typeof r.cache_eligible !== 'boolean' || !['complete','required_source_incomplete','unsafe'].includes(r.classification) ||
      typeof r.run_id !== 'string' || r.run_id !== String(context.runId) ||
      typeof r.run_attempt !== 'string' || !/^[1-9][0-9]{0,4}$/.test(r.run_attempt) || r.run_attempt !== context.runAttempt ||
      !Array.isArray(r.selected_domains) || r.selected_domains.length < 1 || r.selected_domains.length > 18 ||
      !r.selected_domains.every(d=>DOMAINS.has(d)) || new Set(r.selected_domains).size !== r.selected_domains.length ||
      !Array.isArray(r.refusals) || r.classification !== 'unsafe' && r.refusals.length !== 0 ||
      !Array.isArray(r.jobs) || r.jobs.length !== r.selected_domains.length) return null;
  const p = needs.source_plan?.outputs, s = needs.seed?.outputs, m = needs.migrate?.outputs;
  if (r.source_sha !== p?.source_sha || r.source_sha !== m?.source_sha || r.source_sha !== s?.source_sha ||
      r.plan_sha256 !== p?.plan_sha256 || r.plan_sha256 !== s?.plan_sha256 ||
      r.schema_head !== m?.schema_head || r.schema_head !== s?.schema_head ||
      String(r.dry_run) !== p?.dry_run || String(r.bootstrap_selected) !== p?.bootstrap ||
      r.classification !== s?.classification || String(r.cache_eligible) !== s?.cache_eligible) return null;
  let planned;
  try { planned = JSON.parse(p.domains); } catch { return null; }
  if (!Array.isArray(planned) || JSON.stringify(planned) !== JSON.stringify(r.selected_domains)) return null;
  const seenDomains = new Set(), seenIds = new Set();
  for (const j of r.jobs) {
    if (!keys(j,['domain','job_id','status','source_mode','processed','created','updated','error_count','required_completion','document_count','accepted_documents','held_proposals','retention']) || !r.selected_domains.includes(j.domain) || seenDomains.has(j.domain) ||
        !count(j.job_id) || j.job_id <= r.job_floor || seenIds.has(j.job_id) ||
        !['completed','completed_with_errors'].includes(j.status) || !['live','partial','fixture','unknown'].includes(j.source_mode) ||
        ![j.processed,j.created,j.updated,j.error_count].every(count) || j.processed < 1 ||
        j.created+j.updated>j.processed || !['complete','incomplete','not_required','unknown'].includes(j.required_completion) ||
        !(j.document_count === null || count(j.document_count)) || !(j.accepted_documents === null || count(j.accepted_documents)) ||
        !Array.isArray(j.held_proposals) || j.held_proposals.length > 2000 || !object(j.retention)) return null;
    seenDomains.add(j.domain); seenIds.add(j.job_id);
    const seenHolds = new Set();
    for (const h of j.held_proposals) {
      if (!keys(h,['document_id','source_sha256','candidate_sha256','previous_sha256','retirements','revisions']) || seenHolds.has(h.document_id) || !count(h.document_id) || h.document_id < 1 || !count(h.retirements) || !count(h.revisions) ||
          ![h.source_sha256,h.candidate_sha256,h.previous_sha256].every(v=>hex(v,64)) || h.retirements+h.revisions===0) return null;
      seenHolds.add(h.document_id);
    }
    if (!validRetention(j.retention)) return null;
    const isRequired = ['audits','fiscal_summary','pending_bills'].includes(j.domain);
    if (j.required_completion === 'complete' && (j.status !== 'completed' || j.error_count !== 0 ||
        j.source_mode !== 'live' || j.held_proposals.length !== 0)) return null;
    if (j.domain === 'audits' && j.required_completion === 'complete' &&
        (!count(j.accepted_documents) || j.accepted_documents < 1 || !count(j.document_count) ||
         j.document_count < j.accepted_documents)) return null;
    if (j.held_proposals.length && (j.domain !== 'audits' || j.required_completion !== 'incomplete' || j.source_mode !== 'partial')) return null;
    if (r.classification === 'complete' && (isRequired && j.required_completion !== 'complete' ||
        !isRequired && j.required_completion !== 'not_required')) return null;
    if (r.cache_eligible) {
      const editorial=j.domain === 'learning_hub' && j.source_mode === 'fixture' &&
        j.status === 'completed_with_errors' && j.error_count === 1 && j.required_completion === 'not_required';
      const held=j.domain === 'audits' && j.required_completion === 'incomplete' && j.source_mode === 'partial' &&
        j.status === 'completed_with_errors' && j.held_proposals.length > 0 && j.held_proposals.length <= 16 &&
        j.error_count === j.held_proposals.length && count(j.accepted_documents) && j.accepted_documents > 0 &&
        count(j.document_count) && j.document_count >= j.accepted_documents+j.held_proposals.length;
      if (!editorial && !held && (j.status !== 'completed' || j.error_count !== 0 || !['live','partial'].includes(j.source_mode))) return null;
      if (isRequired && j.required_completion === 'incomplete' && !held &&
          !(j.domain === 'fiscal_summary' && j.status === 'completed' && j.error_count === 0 && j.source_mode === 'partial')) return null;
      if (['fiscal_summary','pending_bills'].includes(j.domain) && j.created+j.updated !== j.processed) return null;
    }
  }
  const incomplete = r.jobs.some(j=>j.required_completion === 'incomplete');
  const required = new Set(['audits','fiscal_summary','pending_bills']);
  if (r.classification === 'complete' && incomplete || r.classification === 'required_source_incomplete' && !incomplete) return null;
  if (r.cache_eligible !== (!r.dry_run && r.classification !== 'unsafe')) return null;
  if (r.cache_eligible && (!r.cli_executed || !r.cli_exit_zero || r.jobs.some(j=>
      j.source_mode === 'unknown' || j.required_completion === 'unknown' ||
      (required.has(j.domain) ? j.required_completion === 'not_required' : j.required_completion !== 'not_required')))) return null;
  return r;
}


function verifyRefresh(needs, context) {
  const r=currentRun(needs, context);
  return !!(r && ['complete','required_source_incomplete'].includes(r.classification) && r.cache_eligible &&
    hex(context.sha,40) && r.source_sha === context.sha && hex(context.expectedGenerator,64) && r.generator_sha256 === context.expectedGenerator &&
    ['source_plan','migrate','validate'].every(k=>needs[k]?.result === 'success') &&
    needs.source_plan.outputs.dry_run === 'false' && needs.seed.outputs.cache_eligible === 'true' && needs.seed.outputs.report_version === '1' &&
    (needs.seed.result === 'success' && r.classification === 'complete' || needs.seed.result === 'failure' && r.classification === 'required_source_incomplete') &&
    (needs.source_plan.outputs.bootstrap === 'true' && needs.bootstrap?.result === 'success' ||
     needs.source_plan.outputs.bootstrap === 'false' && needs.bootstrap?.result === 'skipped'));
}

function runDescription(r, needs) {
  const acknowledgements = needs.revalidate?.outputs || {};
  const backend = acknowledgements.backend === 'true' ? 'acknowledged' : 'unverified';
  const pages = acknowledgements.pages === 'true' && backend === 'acknowledged' ? 'acknowledged' : 'unverified';
  let text = `**Refresh receipts:** backend ${backend}; pages ${pages}. Integrity job: ${STATES.has(needs.validate?.result) ? needs.validate.result : 'unknown'}.\n\n`;
  if (!r) return text + '**Current-run report:** unverified (missing, malformed or mismatched identity).\n';
  text += `**Current-run report v1:** ${r.classification}; source \`${r.source_sha}\`; schema \`${r.schema_head}\`; plan \`${r.plan_sha256}\`.\n` +
    `Run ${r.run_id}:${r.run_attempt}; job floor ${r.job_floor}; CLI executed=${r.cli_executed}, exit=${r.cli_exit ?? 'unknown'}; dry run=${r.dry_run}; bootstrap selected=${r.bootstrap_selected}.\n\n` +
    '| Domain | Job | Mode | Processed / created / updated | Required completion | Errors | Documents accepted / seen | Retention retained / observed / missing |\n' +
    '| --- | --- | --- | --- | --- | --- | --- | --- |\n';
  for (const j of r.jobs) {
    const t = j.retention;
    text += `| ${j.domain} | ${j.job_id} | ${j.source_mode} | ${j.processed} / ${j.created} / ${j.updated} | ${j.required_completion} | ${j.error_count} | ${j.accepted_documents ?? 'unknown'} / ${j.document_count ?? 'unknown'} | ${t.state === 'unverified' ? 'unverified' : `${t.retained} / ${t.observed} / ${t.missing}`} |\n`;
    for (const h of j.held_proposals) text += `\nHeld document ${h.document_id}: ${h.retirements} retirements, ${h.revisions} revisions; source \`${h.source_sha256}\`; candidate \`${h.candidate_sha256}\`; previous \`${h.previous_sha256}\`.\n`;
  }
  return text;
}

function assess(needs, inputs, receipt = null) {
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
    if (key === 'seed' && ['success','failure'].includes(result)) {
      if (!receipt) { detail += ' — current-run report unverified'; problem = true; }
      else if (receipt.classification !== 'complete') { detail += ' — required source evidence incomplete or execution unsafe'; problem = true; }
    }
    if (key === 'revalidate' && result === 'success' &&
        (needs.revalidate?.outputs?.backend !== 'true' || needs.revalidate?.outputs?.pages !== 'true')) {
      detail = 'success — refresh acknowledgements unverified'; problem = true;
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
  const receipt = currentRun(needs, {...context, runAttempt:env.PIPELINE_RUN_ATTEMPT});
  const diagnostics = runDescription(receipt, needs);
  const result = assess(needs, inputs, receipt);
  const health = healthDescription(needs);
  const outcome = result.problems.length ? '⚠️ Pipeline completion not verified' : '✅ Pipeline jobs completed as planned';
  const table = '| Job | Result | Interpretation |\n| --- | --- | --- |\n' +
    result.rows.map(row => `| ${row.label} (\`${row.key}\`) | ${row.result} | ${row.detail} |`).join('\n');
  await core.summary.addRaw(`\n### Pipeline outcome\n\n**${outcome}**\n\n${table}\n\n` +
    `**Health Check:** ${health}\n\n${diagnostics}\nJob success confirms execution only; source transport, extraction, freshness and publication require their own receipts.\n`).write();
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
    `**Run:** ${runUrl}\n**Attempt:** ${attempt}\n**Triggered by:** ${event}\n**Domain:** ${domain}\n\n${table}\n\n${diagnostics}\n` +
    `### Action Required\n1. Inspect the [workflow run logs](${runUrl}) and admission/source-plan diagnostics before considering any write.\n` +
    `2. If seeding ran, inspect ingestion job and source receipts for domain-level failures.\n` +
    `3. Keep the accepted source revision guard unchanged; a reporting failure never authorizes a retry or activation.\n\n` +
    `This managed incident records the latest unsuccessful run attempt. A repeated attempt adds no duplicate issue or comment. Review recovery before closing it.\n`;
  const title = `Data pipeline failed: ${failed}`.slice(0, 240);
  if (managed.length) await github.rest.issues.update({...scope, issue_number: managed[0].number, title, body});
  else await github.rest.issues.create({...scope, title, body, labels: ['bug', 'data-pipeline', 'automated']});
}

module.exports = {assess, healthDescription, currentRun, validRetention, verifyRefresh, runDescription, report};

if (require.main === module) {
  try {
    if (process.argv.slice(2).join(' ') !== '--verify-refresh') throw new Error('mode');
    const expectedGenerator=require('node:crypto').createHash('sha256').update(require('node:fs').readFileSync('backend/seeding/current_run.py')).digest('hex');
    if (!verifyRefresh(JSON.parse(process.env.REFRESH_NEEDS), {sha:process.env.GITHUB_SHA,runId:process.env.GITHUB_RUN_ID,
        runAttempt:process.env.GITHUB_RUN_ATTEMPT,expectedGenerator})) throw new Error('refused');
    process.stdout.write('Typed current-run inventory and refresh eligibility verified.\n');
  } catch {
    process.stderr.write('Typed current-run refresh eligibility refused.\n'); process.exitCode=1;
  }
}
