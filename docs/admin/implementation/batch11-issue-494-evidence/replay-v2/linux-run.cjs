'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const crypto = require('node:crypto'), { spawn } = require('node:child_process');
const boundary=require('./boundary.cjs');
const [rootArg,manifestArg,scratchArg,mode,...command]=process.argv.slice(2);
const root=boundary.realPath(rootArg),manifestPath=boundary.realPath(manifestArg),scratch=boundary.externalFresh(root,scratchArg);
assert.ok(['unit','build','plain','native'].includes(mode));
assert.ok(command.length && path.isAbsolute(command[0]));
const manifest = JSON.parse(fs.readFileSync(manifestPath));
assert.ok(manifest&&typeof manifest.files==='object'&&!Array.isArray(manifest.files)&&Object.keys(manifest.files).length,'nonempty imported source manifest required');
for(const [name,digest] of Object.entries(manifest.files)){boundary.sourceFile(root,name);assert.match(digest,/^[a-f0-9]{64}$/);}
const sha = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function measure() {
 const files = {};
 for (const p of Object.keys(manifest.files)) files[p] = sha(boundary.sourceFile(root,p));
 assert.deepEqual(files, manifest.files, 'Linux source must match imported lane bytes');
 return files;
}
for (const folder of [root, path.join(root, 'frontend')]) assert.ok(!fs.readdirSync(folder).some(p=>p.startsWith('.env') && !/\.(example|sample|template)$/.test(p)), 'dotenv refused');
const before = measure();
fs.mkdirSync(scratch);
const env={...boundary.environment(scratch),NATIVE_VERIFY_CACHE_DIR:path.join(scratch,'models'),PLAYWRIGHT_BROWSERS_PATH:path.join(scratch,'browsers')};
fs.mkdirSync(env.NATIVE_VERIFY_CACHE_DIR);fs.mkdirSync(env.PLAYWRIGHT_BROWSERS_PATH);
if(mode==='build')Object.assign(env,{NEXT_PUBLIC_API_URL:'http://127.0.0.1:18048',INTERNAL_API_URL:'http://127.0.0.1:18048',NEXT_PUBLIC_SUPABASE_URL:'http://127.0.0.1:18048',NEXT_PUBLIC_SUPABASE_ANON_KEY:'batch11-review-inert-anon-key'});
console.log(JSON.stringify({check:'linux-command-source-environment',source:manifest,sourceMeasured:before,generator_sha256:sha(__filename),boundary_sha256:sha(require.resolve('./boundary.cjs')),current_checkout_acceptance:false,command,mode,env,runtime:{node:process.version,platform:process.platform,arch:process.arch}}));
const child=spawn(command[0],command.slice(1),{cwd:path.join(root,'frontend'),env,detached:true,stdio:'inherit'});
let timeout=false;
const timer=setTimeout(()=>{timeout=true;process.kill(-child.pid,'SIGKILL');},1100000);
child.on('error',error=>{console.error(error);clearTimeout(timer);process.exitCode=1;});
child.on('close',async(code,signal)=>{clearTimeout(timer);try{const cleanup=await boundary.cleanupGroup(child.pid);const after=measure();assert.deepEqual(after,before);console.log(JSON.stringify({check:'linux-command-readback',exit:code,signal,timeout,cleanup,sourceStable:true,sourceAfter:after}));process.exitCode=code===0&&!signal&&!timeout&&!cleanup.survivorsDetected&&cleanup.groupAbsent?0:1;}catch(error){console.error(error);process.exitCode=1;}});
