import { createHash } from 'node:crypto';
import { cpSync, readFileSync, writeFileSync, rmSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { gunzipSync, gzipSync } from 'node:zlib';
const repo = '/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app';
const pkg = resolve(repo, 'docs/admin/implementation/batch10-scroll-evidence');
const own = '/Users/roger/.codex/visualizations/2026/10/10/01a123ab-8dbe-78d1-9583-521af8091fa1/batch10-scroll-evidence/review-spec';
const {verifyPackage} = await import(pathToFileURL(resolve(pkg, 'verify.mjs')).href);
const {executionPassed, verifyPartition} = await import(pathToFileURL(resolve(repo, 'frontend/scripts/ci-browser-cohorts.mjs')).href);
const sha = b => createHash('sha256').update(b).digest('hex');
const rootManifest = JSON.parse(readFileSync(resolve(pkg, 'manifest.json')));
const decode = p => JSON.parse(gunzipSync(readFileSync(resolve(pkg, p))));
const inventory = decode(rootManifest.inventory);
const valid = decode(rootManifest.cohorts[0].report);
valid.config.rootDir = resolve(repo, 'frontend/e2e');
const expected = inventory.cohorts[0].cases;
const events=[];
const baseline = await verifyPackage(pkg, repo);
if(baseline.issue_601 !== 'unresolved' || baseline.passed !==312 || baseline.existing_fixmes!==11)throw Error('Bad positive package diagnostic');
events.push({kind:'package-positive',diagnostic:baseline});
const fixtures = resolve(own,'fixtures');mkdirSync(fixtures);
async function packageCase(name, mutate, shouldReject=true){
 const dst=resolve(fixtures,name); cpSync(pkg,dst,{recursive:true});
 const m=JSON.parse(readFileSync(resolve(dst,'manifest.json')));
 mutate(m,dst);writeFileSync(resolve(dst,'manifest.json'),JSON.stringify(m));
 let rejected=false,diagnostic;
 try{diagnostic=await verifyPackage(dst,repo);}catch(e){rejected=true;diagnostic=e.message;}
 if(rejected!==shouldReject)throw Error('Unexpected package result: '+name+' '+JSON.stringify(diagnostic));
 events.push({kind:'package-control',name,expected_reject:shouldReject,rejected,diagnostic});
}
await packageCase('missing-target',m=>m.targets.pop());
await packageCase('false-green-pagination',m=>m.targets.at(-1).role='positive-diagnostic');
await packageCase('truncated-sources',m=>m.sources=Object.fromEntries(Object.entries(m.sources).slice(0,8)));
await packageCase('historical-trace-substitution',m=>m.historical_trace=m.targets[0].report);
await packageCase('zero-count',m=>m.targets[0].count=0);
await packageCase('duplicate-cohort',m=>m.cohorts[5]=m.cohorts[0]);
await packageCase('claimed-resolution',m=>m.status='resolved');
await packageCase('recompressed-equivalent',(m,d)=>{const e=m.files[0];const b=gzipSync(gunzipSync(readFileSync(resolve(d,e.path))),{level:1});writeFileSync(resolve(d,e.path),b);e.sha256=sha(b);},false);
function parserCase(name,mutate,exit=0){
 const r=structuredClone(valid), cases=structuredClone(expected);mutate(r,cases);
 let rejected=false,diagnostic;
 try{const result=executionPassed(r,cases,exit);rejected=result===false;diagnostic=result;}catch(e){rejected=true;diagnostic=e.message;}
 if(!rejected)throw Error('Parser false success: '+name);
 events.push({kind:'parser-control',name,rejected,diagnostic});
}
if(executionPassed(valid,expected,0)!==true)throw Error('Valid original parser control failed');
events.push({kind:'parser-positive',passed:true,count:expected.length});
const first=r=>r.suites[0].suites[0].specs[0].tests[0];
parserCase('empty-suites',r=>{r.suites=[];r.stats.expected=0;});
parserCase('infrastructure-error',r=>r.errors=[{message:'browser executable missing'}]);
parserCase('absent-source',r=>r.suites[0].suites[0].specs[0].file='unexecuted.spec.ts');
parserCase('boolean-counter',r=>r.stats.expected=true);
parserCase('nonzero-child',()=>{},1);
parserCase('missing-result',r=>first(r).results=[]);
parserCase('error-on-pass',r=>first(r).results[0].error={message:'contradiction'});
parserCase('omitted-case',(_r,c)=>c.pop());
parserCase('case-status-contradiction',r=>first(r).results[0].status='failed');
for(const [name,groups]of [['missing-cohort',inventory.cohorts.slice(1).map(c=>c.cases)],['duplicate-partition',inventory.cohorts.map((c,i)=>i===5?inventory.cohorts[0].cases:c.cases)]]){
 let diagnostic;try{verifyPartition(inventory.baseline_cases,groups);throw Error('False partition success');}catch(e){if(e.message==='False partition success')throw e;diagnostic=e.message;}
 events.push({kind:'partition-control',name,rejected:true,diagnostic});
}
rmSync(fixtures,{recursive:true});
console.log(JSON.stringify({source_verifier_sha256:sha(readFileSync(resolve(pkg,'verify.mjs'))),source_parser_sha256:sha(readFileSync(resolve(repo,'frontend/scripts/ci-browser-cohorts.mjs'))),events},null,2));
