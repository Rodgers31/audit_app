import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
import {cohorts, cohortEnvironment, listedCases, verifyPartition} from '/app/frontend/scripts/ci-browser-cohorts.mjs';
import {legacyEnvironment} from '/app/frontend/scripts/legacy-e2e-env.mjs';
const list=(config,env)=>{
 const child=spawnSync(process.execPath,['node_modules/@playwright/test/cli.js','test','--config',config,'--project=chromium','--list','--reporter=json'],{env,encoding:'utf8',timeout:60000,maxBuffer:16*1024*1024});
 if(child.status!==0)throw Error(child.stderr||child.stdout);
 return listedCases(JSON.parse(child.stdout));
};
const baseline=list('playwright.config.ts',legacyEnvironment());
const groups=cohorts.map(c=>({name:c.name,cases:list('playwright.ci-cohorts.config.ts',cohortEnvironment(c))}));
const total=verifyPartition(baseline,groups.map(c=>c.cases));
const prior=JSON.parse(fs.readFileSync('/evidence/baseline-inventory.json'));
if(prior.baseline.some(c=>!baseline.includes(c)))throw Error('Original case omitted');
const added=baseline.filter(c=>!prior.baseline.includes(c));
if(added.length!==6||added.some(c=>!JSON.parse(c).file.startsWith('county-pagination-')))throw Error('Unexpected inventory change');
fs.writeFileSync('/evidence/current-inventory.json',JSON.stringify({baseline,cohorts:groups,total,originalTotal:prior.total,added},null,2),{flag:'wx'});
console.log(JSON.stringify({total,original:prior.total,added:added.length,cohorts:groups.map(c=>({name:c.name,count:c.cases.length}))}));
