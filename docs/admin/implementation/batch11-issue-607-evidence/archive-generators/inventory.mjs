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
const r={baseline,cohorts:groups,total};
fs.writeFileSync('/evidence/baseline-inventory.json',JSON.stringify(r,null,2),{flag:'wx'});
if(JSON.stringify(JSON.parse(fs.readFileSync('/evidence/baseline-inventory.json')))!==JSON.stringify(r))throw Error('readback');
console.log(JSON.stringify({total,cohorts:groups.map(c=>({name:c.name,count:c.cases.length}))}));
