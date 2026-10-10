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
console.log(JSON.stringify({node:process.version,root,repo,direct_call:'await verifyPackage(isolatedCopy, repo)',sourceBefore,harnessBefore}));
await attack('valid-baseline',()=>{},'verify');
await attack('manifest-absent',f=>{unlinkSync(resolve(f.directory,'manifest.json'));f.skipSave=true;});
await attack('manifest-empty',f=>{writeFileSync(resolve(f.directory,'manifest.json'),'');f.skipSave=true;});
await attack('manifest-malformed',f=>{writeFileSync(resolve(f.directory,'manifest.json'),'{');f.skipSave=true;});
for(const v of [null,{},[],true,2,'1'])await attack('unknown-schema-'+String(v),f=>{f.manifest.schema=v;});
for(const v of [null,[],{},'files'])await attack('files-shape-'+String(v),f=>{f.manifest.files=v;});
await attack('archive-byte-tamper',f=>writeFileSync(resolve(f.directory,f.manifest.files[0].path),'tampered'));
await attack('archive-file-absent',f=>unlinkSync(resolve(f.directory,f.manifest.files[0].path)));
await attack('archive-path-traversal',f=>{f.manifest.files[0].path='data/../verify.mjs';});
await attack('archive-file-symlink',f=>{const p=resolve(f.directory,f.manifest.files[0].path);unlinkSync(p);symlinkSync(resolve(root,f.manifest.files[0].path),p);});
await attack('archive-data-root-symlink',f=>{rmSync(resolve(f.directory,'data'),{recursive:true});symlinkSync(resolve(root,'data'),resolve(f.directory,'data'));});
await attack('archive-duplicate',f=>f.manifest.files.push(f.manifest.files[0]));
await attack('empty-targets',f=>{f.manifest.targets=[];});
await attack('missing-negative-name',f=>{f.manifest.targets=f.manifest.targets.filter(t=>t.name!=='probe-native-absent-negative');});
await attack('negative-name-now-positive',f=>{const t=f.manifest.targets.find(t=>t.name==='probe-native-absent-negative');const pos=f.manifest.targets[0];Object.assign(t,pos,{name:'probe-native-absent-negative'});});
await attack('negative-result-counter-contradiction',f=>{const t=f.manifest.targets.find(t=>t.role==='negative-detector');f.json(t.report,r=>{r.stats.skipped=1;r.stats.unexpected=0;});});
await attack('negative-assertion-error-missing',f=>{const t=f.manifest.targets.find(t=>t.role==='negative-detector');f.json(t.report,r=>{delete f.tests(r)[0].results[0].error;});});
await attack('positive-report-zero-cases',f=>{f.json(f.manifest.targets[0].report,r=>{r.suites=[];r.stats.expected=0;});});
await attack('positive-report-wrong-case',f=>{f.json(f.manifest.targets[0].report,r=>{const visit=s=>{for(const p of s.specs??[]){p.file='totally-different.spec.ts';p.title='wrong behavior';p.line=999;p.column=0;}for(const c of s.suites??[])visit(c);};r.suites.forEach(visit);});});
await attack('positive-result-error',f=>{f.json(f.manifest.targets[0].report,r=>{f.tests(r)[0].results[0].errors=[{message:'failure'}];});});
await attack('positive-result-retry',f=>{f.json(f.manifest.targets[0].report,r=>{f.tests(r)[0].results[0].retry=1;});});
await attack('positive-source-drift',f=>{f.json(f.manifest.targets[0].receipt,r=>{r.source_changed_during_run=['frontend/e2e/smart-back.spec.ts'];});});
await attack('positive-generator-mismatch',f=>{f.json(f.manifest.targets[0].receipt,r=>{r.generator_sha256='0'.repeat(64);});});
await attack('positive-source-hashes-wrong',f=>{f.json(f.manifest.targets[0].receipt,r=>{r.source_hashes['frontend/e2e/smart-back.spec.ts']='0'.repeat(64);});});
await attack('positive-receipt-commit-wrong',f=>{f.json(f.manifest.targets[0].receipt,r=>{r.target_commit='0'.repeat(40);r.target_tree='0'.repeat(40);});});
await attack('positive-log-hash-wrong',f=>{f.json(f.manifest.targets[0].receipt,r=>{r.log_sha256='0'.repeat(64);});});
await attack('manifest-target-identity-wrong',f=>{f.manifest.target_commit='0'.repeat(40);f.manifest.target_tree=null;});
await attack('manifest-sources-omit-scroll',f=>{f.manifest.sources=Object.fromEntries(Object.entries(f.manifest.sources).slice(0,8));});
await attack('full-receipt-child-fails',f=>{f.json(f.manifest.cohorts[0].receipt,r=>{r.child_exit=1;});});
await attack('full-parent-receipt-drift',f=>{f.json('data/full-original-chromium.json.gz',r=>{r.child_exit=1;r.verification_exit=1;r.timeout=true;r.generator_unchanged=false;r.source_changed_during_run=['frontend/e2e/smart-back.spec.ts'];});});
await attack('full-generator-source-mismatch',f=>{f.json('data/full-original-chromium.json.gz',r=>{r.generator_sha256='0'.repeat(64);r.source_hashes['frontend/e2e/smart-back.spec.ts']='0'.repeat(64);});});
await attack('full-receipt-error',f=>{f.json(f.manifest.cohorts[0].receipt,r=>{r.error='infrastructure failed';r.readback='';});});
await attack('full-retry',f=>{f.json(f.manifest.cohorts[0].report,r=>{const t=f.tests(r).find(t=>t.status==='expected');t.results[0].retry=100;});});
await attack('full-inventory-empty',f=>{f.json(f.manifest.inventory,r=>{r.baseline_cases=[];});});
await attack('full-inventory-generator-wrong',f=>{f.json(f.manifest.inventory,r=>{r.generator_sha256='0'.repeat(64);r.target_commit='0'.repeat(40);});});
await attack('full-inventory-substituted-consistently',f=>{
 const c=f.manifest.cohorts[0];let oldCase,newCase;
 f.json(c.report,r=>{const spec=r.suites[0].suites[0].specs[0];oldCase=JSON.stringify({file:spec.file,line:spec.line,column:spec.column,title:spec.title});spec.title='never executed substituted case';spec.line=100000;newCase=JSON.stringify({file:spec.file,line:spec.line,column:spec.column,title:spec.title});});
 f.json(f.manifest.inventory,i=>{for(const arr of [i.baseline_cases,...i.cohorts.map(c=>c.cases)]){const idx=arr.indexOf(oldCase);if(idx>=0)arr[idx]=newCase;}});
});
await attack('unknown-archive-compression',f=>{const e=f.manifest.files.find(e=>e.path==='data/python-runtime.txt.gz');e.compression='unknown';e.input_sha256=e.sha256;});
await attack('publisher-generator-hash-wrong',f=>{f.manifest.generator_sha256='0'.repeat(64);});
for(const [label,value] of [['NaN',NaN],['Inf',Infinity],['NegInf',-Infinity],['negative',-1],['zero',0],['bool',true],['null',null],['string','20']]){
 await attack('target-count-'+label,f=>{f.manifest.targets[0].count=value;});
 await attack('positive-duration-'+label,f=>{f.json(f.manifest.targets[0].report,r=>{f.tests(r)[0].results[0].duration=value;});},label==='zero'?'verify':'reject');
 await attack('full-counter-'+label,f=>{f.json(f.manifest.cohorts[0].report,r=>{r.stats.expected=value;});});
}
const sourceAfter=Object.fromEntries(sourcePaths.map(p=>[p,sha(readFileSync(resolve(root,p)))]));
const receipt={node:process.version,platform:process.platform,arch:process.arch,exact_command:['node',fileURLToPath(import.meta.url)],sourceBefore,sourceAfter,source_unchanged:JSON.stringify(sourceBefore)===JSON.stringify(sourceAfter),harnessBefore,harnessAfter:sha(readFileSync(fileURLToPath(import.meta.url))),records,unexpected_successes:records.filter(r=>r.expect==='reject'&&r.actual==='verified'),unexpected_rejections:records.filter(r=>r.expect==='verify'&&r.actual==='rejected')};
writeFileSync(resolve(out,'attack-results.json'),JSON.stringify(receipt,null,2),{flag:'wx'});
rmSync(work,{recursive:true});
console.log(JSON.stringify({attempts:records.length,false_successes:receipt.unexpected_successes.map(r=>r.name),unexpected_rejections:receipt.unexpected_rejections.map(r=>r.name),source_unchanged:receipt.source_unchanged}));
