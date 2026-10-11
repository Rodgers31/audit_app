'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),{spawn}=require('node:child_process');
const [rootArg,...command]=process.argv.slice(2),root=path.resolve(rootArg),hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
assert.ok(command.length&&path.isAbsolute(command[0]));
function measure(){const files={};function walk(rel){for(const d of fs.readdirSync(path.join(root,rel),{withFileTypes:true})){if(rel===''&&['node_modules','.next'].includes(d.name))continue;const p=path.join(rel,d.name),s=fs.lstatSync(path.join(root,p));assert.ok(!s.isSymbolicLink(),'baseline source link refused');if(s.isDirectory())walk(p);else{assert.ok(s.isFile());files[p]=hash(path.join(root,p));}}}walk('');return files;}
const before=measure();console.log(JSON.stringify({check:'actual-baseline-inputs',files:before,producer_sha256:hash(__filename),runtime:{node:process.version,platform:process.platform,arch:process.arch},command,environment:process.env}));
const child=spawn(command[0],command.slice(1),{cwd:root,env:process.env,detached:true,stdio:'inherit'});let timedOut=false;
const timer=setTimeout(()=>{timedOut=true;process.kill(-child.pid,'SIGKILL');},180000);
child.on('error',e=>{clearTimeout(timer);console.error(e);process.exitCode=1;});
child.on('close',(code,signal)=>{clearTimeout(timer);try{const after=measure();assert.deepEqual(after,before);console.log(JSON.stringify({check:'actual-baseline-readback',sourceStable:true,exit:code,signal,timedOut,files:after}));process.exitCode=code===0&&!signal&&!timedOut?0:1;}catch(e){console.error(e);process.exitCode=1;}});
