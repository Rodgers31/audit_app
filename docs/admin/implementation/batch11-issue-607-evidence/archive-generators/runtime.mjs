import {chromium} from '/app/frontend/node_modules/playwright-core/index.mjs';
import fs from 'node:fs';import os from 'node:os';import crypto from 'node:crypto';
const browser=await chromium.launch();const context=await browser.newContext({viewport:{width:1280,height:720}});const page=await context.newPage();
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const r={node:process.version,nodeExecutableSha256:sha(process.execPath),execArgv:process.execArgv,platform:process.platform,arch:process.arch,kernel:os.release(),cpus:os.cpus().length,playwright:JSON.parse(fs.readFileSync('/app/frontend/node_modules/@playwright/test/package.json')).version,chromium:browser.version(),chromiumExecutableSha256:sha(chromium.executablePath()),viewport:page.viewportSize(),fixtureScope:'synthetic production-config local Linux AMD64 under macOS ARM64 Docker emulation; no hosted or production acceptance'};
fs.writeFileSync('/evidence/runtime.json',JSON.stringify(r,null,2),{flag:'wx'});
if(JSON.stringify(JSON.parse(fs.readFileSync('/evidence/runtime.json')))!==JSON.stringify(r))throw Error('runtime readback');console.log(JSON.stringify(r,null,2));await browser.close();
