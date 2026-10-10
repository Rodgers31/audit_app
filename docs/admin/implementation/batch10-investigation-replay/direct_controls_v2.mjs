// Current portable controls. Original producer and receipts remain archival-only.
import { createHash } from 'node:crypto';
import { cpSync, readFileSync, writeFileSync, rmSync, mkdirSync, lstatSync, realpathSync, readdirSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { gunzipSync, gzipSync } from 'node:zlib';
const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '../../../..');
const pkg = resolve(repo, 'docs/admin/implementation/batch10-scroll-evidence');
if (process.argv.length !== 3 || !isAbsolute(process.argv[2])) throw Error('EXTERNAL_OUTPUT required');
if (lstatSync(process.argv[2]).isSymbolicLink() || !lstatSync(process.argv[2]).isDirectory()) throw Error('Owned regular output directory required');
const own = realpathSync(process.argv[2]);
if (readdirSync(own).length) throw Error('Fresh empty output required');
const rel = relative(repo, own), inverse = relative(own, repo);
if (!(rel.startsWith('../') || isAbsolute(rel)) || !(inverse.startsWith('../') || isAbsolute(inverse))) throw Error('External output required');
// The unchanged original parser resolves its frontend from the import-time cwd.
// Keep that real prerequisite explicit; all imported package paths are absolute.
process.chdir(resolve(repo, 'frontend'));
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
console.log(JSON.stringify({classification:'CURRENT_OFFLINE_ARCHIVE_CONTROLS',current_checkout_acceptance:false,runtime:{node:process.version,platform:process.platform,architecture:process.arch},generator_sha256:sha(readFileSync(fileURLToPath(import.meta.url))),source_verifier_sha256:sha(readFileSync(resolve(pkg,'verify.mjs'))),source_parser_sha256:sha(readFileSync(resolve(repo,'frontend/scripts/ci-browser-cohorts.mjs'))),events},null,2));
