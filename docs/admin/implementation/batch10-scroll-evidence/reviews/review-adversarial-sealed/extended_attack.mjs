import {createHash} from 'node:crypto';
import {cpSync,mkdtempSync,readFileSync,writeFileSync,rmSync,unlinkSync,symlinkSync,mkdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,dirname} from 'node:path';
import {gzipSync,gunzipSync} from 'node:zlib';
import {pathToFileURL,fileURLToPath} from 'node:url';

const repo='/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app';
const root=resolve(repo,'docs/admin/implementation/batch10-scroll-evidence');
const out=dirname(fileURLToPath(import.meta.url));
const {verifyPackage}=await import(pathToFileURL(resolve(root,'verify.mjs')));
const sha=x=>createHash('sha256').update(x).digest('hex');
const sourcePaths=['verify.mjs','verify.test.mjs','create_package.py','manifest.json'];
const sourceBefore=Object.fromEntries(sourcePaths.map(p=>[p,sha(readFileSync(resolve(root,p)))]));
const harnessBefore=sha(readFileSync(fileURLToPath(import.meta.url)));
const records=[];
const work=mkdtempSync(resolve(tmpdir(),'batch10-scroll-independent-attack-'));
function fixture(name){
 const directory=resolve(work,name); cpSync(root,directory,{recursive:true});
 const manifest=JSON.parse(readFileSync(resolve(directory,'manifest.json')));
 const save=()=>writeFileSync(resolve(directory,'manifest.json'),JSON.stringify(manifest));
 function raw(path,value){
  const bytes=Buffer.isBuffer(value)?value:Buffer.from(value);
  const entry=manifest.files.find(e=>e.path===path); const encoded=gzipSync(bytes);
  writeFileSync(resolve(directory,path),encoded);entry.sha256=sha(encoded);entry.input_sha256=sha(bytes);save();
 }
 function json(path,change){const value=JSON.parse(gunzipSync(readFileSync(resolve(directory,path))));change(value);raw(path,JSON.stringify(value));}
 const tests=report=>{const result=[];function visit(s){for(const p of s.specs??[])for(const t of p.tests??[])result.push(t);for(const c of s.suites??[])visit(c);}report.suites.forEach(visit);return result;};
 return {directory,manifest,save,raw,json,tests};
}
async function attack(name,mutate,expect='reject'){
 const f=fixture(name);let verdict,error;
 try{await mutate(f);if(!f.skipSave)f.save();verdict=await verifyPackage(f.directory,repo);}
 catch(e){error=String(e.message).slice(0,800);}
 const record={name,expect,actual:verdict?'verified':'rejected',...(verdict?{verdict}:{error})};
 records.push(record);console.log(JSON.stringify(record));
}

console.log(JSON.stringify({node:process.version,root,repo,sourceBefore,harnessBefore}));
await attack('extended-valid-baseline',()=>{},'verify');
for (const [label,value] of [['absent',undefined],['empty',[]],['wrong',['node','--version']],['null',null]]) {
 await attack('target-command-'+label,f=>{f.json(f.manifest.targets[0].receipt,r=>{r.command=value;});});
}
await attack('inventory-command-wrong',f=>f.json('data/original-inventory.json.gz',r=>{r.command=['node','--version'];}));
await attack('cohort-command-wrong',f=>f.json(f.manifest.cohorts[0].receipt,r=>{r.command=['node','--version'];}));
await attack('full-command-changed-but-source-key-valid',f=>f.json('data/full-original-chromium.json.gz',r=>{r.command[0]='echo';r.command.push('--no-browser');}));
await attack('probe-source-byte-drift',f=>f.raw('data/probe.spec.ts.gz','// All scroll assertions removed\n'));
await attack('probe-hook-byte-drift',f=>f.raw('data/probe-hooks.ts.gz','// No measurements executed\n'));
await attack('probe-hook-v1-byte-drift',f=>f.raw('data/probe-hooks-v1.ts.gz','// No measurements executed\n'));
await attack('probe-config-byte-drift',f=>f.raw('data/probe.config.ts.gz','// Browser server dependency removed\n'));
await attack('target-generator-conflicts-consumed-source',f=>{
 const generator='data/run_record_v2.py.gz';f.raw(generator,'# invalid or unrelated command\n');const hash=f.manifest.files.find(e=>e.path===generator).input_sha256;
 for(const t of f.manifest.targets.filter(t=>t.generator===generator))f.json(t.receipt,r=>{r.generator_sha256=hash;});
 f.json('data/original-inventory.json.gz',r=>{r.generator_sha256=hash;});
});
await attack('remove-required-runtime-inputs',f=>{
 for(const path of ['data/python-runtime.txt.gz','data/resolved-runtime.json.gz','data/node22-runtime.json.gz','data/launch.json.gz']){
  unlinkSync(resolve(f.directory,path));f.manifest.files=f.manifest.files.filter(e=>e.path!==path);
 }
});
await attack('negative-error-is-unrelated-location',f=>{const t=f.manifest.targets.find(t=>t.role==='negative-detector');f.json(t.report,r=>{const e=f.tests(r)[0].results[0].error;e.location={file:'unrelated.ts',line:1,column:1};e.stack='unrelated()';});});
await attack('negative-diagnostic-observed-events-empty',f=>{const t=f.manifest.targets.find(t=>t.role==='negative-detector');f.json(t.report,r=>{const a=f.tests(r)[0].results[0].attachments.find(a=>a.name==='scroll-events');const data=JSON.parse(Buffer.from(a.body,'base64'));data.events=[];a.body=Buffer.from(JSON.stringify(data)).toString('base64');});});
await attack('negative-capture-absent',f=>{const t=f.manifest.targets.find(t=>t.role==='negative-detector');f.json(t.report,r=>{f.tests(r)[0].results[0].attachments=[];});});
await attack('positive-probe-capture-absent',f=>{const t=f.manifest.targets.find(t=>t.name==='probe-linux-cpu1');f.json(t.report,r=>{for(const test of f.tests(r))test.results[0].attachments=[];});});
await attack('full-existing-fixmes-relabelled-runtime-skips',f=>{f.json(f.manifest.cohorts[0].report,r=>{for(const t of f.tests(r).filter(t=>t.status==='skipped'))t.annotations=[{type:'skip',description:'browser prerequisite missing; runtime not executed'}];});});
await attack('positive-contradictory-spec-status',f=>{f.json(f.manifest.targets[0].report,r=>{const visit=s=>{for(const p of s.specs??[])p.ok=false;for(const c of s.suites??[])visit(c);};r.suites.forEach(visit);});});
await attack('negative-contradictory-spec-status',f=>{const t=f.manifest.targets.find(t=>t.role==='negative-detector');f.json(t.report,r=>{const visit=s=>{for(const p of s.specs??[])p.ok=true;for(const c of s.suites??[])visit(c);};r.suites.forEach(visit);});});
await attack('missing-optional-positive-record',f=>{f.manifest.targets=f.manifest.targets.filter(t=>t.name!=='probe-chunk-delay1000');});
const sourceAfter=Object.fromEntries(sourcePaths.map(p=>[p,sha(readFileSync(resolve(root,p)))]));
const receipt={node:process.version,platform:process.platform,arch:process.arch,exact_command:['node',fileURLToPath(import.meta.url)],sourceBefore,sourceAfter,source_unchanged:JSON.stringify(sourceBefore)===JSON.stringify(sourceAfter),harnessBefore,harnessAfter:sha(readFileSync(fileURLToPath(import.meta.url))),records,unexpected_successes:records.filter(r=>r.expect==='reject'&&r.actual==='verified'),unexpected_rejections:records.filter(r=>r.expect==='verify'&&r.actual==='rejected')};
writeFileSync(resolve(out,'extended-results.json'),JSON.stringify(receipt,null,2),{flag:'wx'});
rmSync(work,{recursive:true});
console.log(JSON.stringify({attempts:records.length,false_successes:receipt.unexpected_successes.map(r=>r.name),unexpected_rejections:receipt.unexpected_rejections.map(r=>r.name),source_unchanged:receipt.source_unchanged}));
