import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {gunzipSync} from 'node:zlib';
import {verifyPackage} from '/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app/docs/admin/implementation/batch10-scroll-evidence/verify.mjs';
import {executionPassed} from '/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app/frontend/scripts/ci-browser-cohorts.mjs';
const repo='/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app';
const root=resolve(repo,'docs/admin/implementation/batch10-scroll-evidence');
const out=dirname(fileURLToPath(import.meta.url));
const digest=x=>createHash('sha256').update(x).digest('hex');
const sources=['verify.mjs','verify.test.mjs','create_package.py','manifest.json'];
const sourceBefore=Object.fromEntries(sources.map(p=>[p,digest(readFileSync(resolve(root,p)))]));
const helperBefore=digest(readFileSync(resolve(repo,'frontend/scripts/ci-browser-cohorts.mjs')));
const rows=[];
async function control(name,fn,expected){let result,error;try{result=await fn();}catch(e){error=String(e.message).slice(0,800);}const actual=error||result===false?'rejected':'accepted';rows.push({name,expected,actual,result,error});console.log(JSON.stringify(rows.at(-1)));}
await control('valid sealed package',()=>verifyPackage(root,repo),'accepted');
for(const [label,args] of [
 ['null root',[null,repo]],['null repo',[root,null]],['empty root',['',repo]],
 ['missing root',[root+'/absent',repo]],['root bool',[true,repo]],['root number',[0,repo]],
 ['root object',[{},repo]],['repo bool',[root,true]],['repo object',[root,{}]],['repo empty',[root,'']],
])await control(label,()=>verifyPackage(...args),'rejected');
const archived=JSON.parse(gunzipSync(readFileSync(resolve(root,'data/public-full-report.json.gz'))));
const inventory=JSON.parse(gunzipSync(readFileSync(resolve(root,'data/inventory.json.gz'))));
const cases=inventory.cohorts.find(c=>c.name==='public').cases;
const report=structuredClone(archived);report.config.rootDir=resolve(repo,'frontend',relative('/app/frontend',report.config.rootDir));
const tests=r=>{const arr=[];const visit=s=>{for(const spec of s.specs)arr.push(...spec.tests);for(const c of s.suites??[])visit(c);};r.suites.forEach(visit);return arr;};
await control('real original execution parser baseline',()=>executionPassed(report,cases,0),'accepted');
for(const [label,value] of [['NaN',NaN],['+Inf',Infinity],['-Inf',-Infinity],['negative',-1],['zero',0],['bool',true],['null',null],['string','258'],['fraction',1.5]]){
 const mutated=structuredClone(report);mutated.stats.expected=value;
 await control('actual parser counter '+label,()=>executionPassed(mutated,cases,0),'rejected');
}
for(const [label,value] of [['NaN',NaN],['+Inf',Infinity],['negative',-1],['bool',true],['null',null],['failed',1]])
 await control('actual parser exit '+label,()=>executionPassed(report,cases,value),'rejected');
for(const [label,value] of [['NaN',NaN],['+Inf',Infinity],['negative',-1],['bool',true],['null',null],['zero',0]]){
 const mutated=structuredClone(report);tests(mutated)[0].results[0].duration=value;
 await control('actual parser duration '+label,()=>executionPassed(mutated,cases,0),label==='zero'?'accepted':'rejected');
}
for(const [label,value] of [['null',null],['empty',{}],['missing-errors',{config:report.config,suites:report.suites,stats:report.stats}],['zero-cases',{...report,suites:[]}],['unknown-shape',{schema:999,ok:true}]])
 await control('actual parser report '+label,()=>executionPassed(value,cases,0),'rejected');
const sourceAfter=Object.fromEntries(sources.map(p=>[p,digest(readFileSync(resolve(root,p)))]));
const receipt={exact_command:['node',fileURLToPath(import.meta.url)],cwd:process.cwd(),node:process.version,sourceBefore,sourceAfter,source_unchanged:JSON.stringify(sourceBefore)===JSON.stringify(sourceAfter),helperBefore,helperAfter:digest(readFileSync(resolve(repo,'frontend/scripts/ci-browser-cohorts.mjs'))),harness_sha256:digest(readFileSync(fileURLToPath(import.meta.url))),rows,unexpected:rows.filter(r=>r.expected!==r.actual)};
writeFileSync(resolve(out,'direct-controls-results.json'),JSON.stringify(receipt,null,2),{flag:'wx'});
console.log(JSON.stringify({count:rows.length,unexpected:receipt.unexpected,source_unchanged:receipt.source_unchanged}));
