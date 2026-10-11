'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const crypto = require('node:crypto'), { spawn } = require('node:child_process');
const [root, manifestPath, mode, ...command] = process.argv.slice(2);
assert.ok(['unit','build','plain','native'].includes(mode));
assert.ok(command.length && path.isAbsolute(command[0]));
const manifest = JSON.parse(fs.readFileSync(manifestPath));
const sha = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function measure() {
 const files = {};
 for (const p of Object.keys(manifest.files)) files[p] = sha(path.join(root, p));
 assert.deepEqual(files, manifest.files, 'Linux source must match imported lane bytes');
 return files;
}
for (const folder of [root, path.join(root, 'frontend')]) assert.ok(!fs.readdirSync(folder).some(p=>p.startsWith('.env') && !/\.(example|sample|template)$/.test(p)), 'dotenv refused');
const before = measure();
const env = { PATH:'/usr/local/bin:/usr/bin:/bin',HOME:'/owned/home',TMPDIR:'/owned/tmp',LANG:'C.UTF-8',PYTHON_DOTENV_DISABLED:'1',NEXT_TELEMETRY_DISABLED:'1',ONNXRUNTIME_NODE_INSTALL:'skip',npm_config_cache:'/owned/npm-cache',npm_config_userconfig:'/owned/user-npmrc',npm_config_globalconfig:'/owned/global-npmrc',npm_config_engine_strict:'true',NATIVE_VERIFY_CACHE_DIR:'/owned/model-cache',PLAYWRIGHT_BROWSERS_PATH:'/owned/browsers'};
if(mode==='build')Object.assign(env,{NEXT_PUBLIC_API_URL:'http://127.0.0.1:18033',INTERNAL_API_URL:'http://127.0.0.1:18033',NEXT_PUBLIC_SUPABASE_URL:'http://127.0.0.1:18033',NEXT_PUBLIC_SUPABASE_ANON_KEY:'batch11-inert-anon-key'});
console.log(JSON.stringify({check:'linux-command-source-environment',source:manifest,sourceMeasured:before,generator_sha256:sha(__filename),command,mode,env,runtime:{node:process.version,platform:process.platform,arch:process.arch}}));
const child=spawn(command[0],command.slice(1),{cwd:path.join(root,'frontend'),env,detached:true,stdio:'inherit'});
let timeout=false;
const timer=setTimeout(()=>{timeout=true;process.kill(-child.pid,'SIGKILL');},1100000);
child.on('error',error=>{console.error(error);clearTimeout(timer);process.exitCode=1;});
child.on('close',(code,signal)=>{clearTimeout(timer);try{const after=measure();assert.deepEqual(after,before);console.log(JSON.stringify({check:'linux-command-readback',exit:code,signal,timeout,sourceStable:true,sourceAfter:after}));process.exitCode=code===0&&!signal&&!timeout?0:1;}catch(error){console.error(error);process.exitCode=1;}});
