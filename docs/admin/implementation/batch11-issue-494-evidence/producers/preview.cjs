'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),net=require('node:net'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const [frontendArg,portArg,scratchArg]=process.argv.slice(2),frontend=fs.realpathSync(frontendArg),port=Number(portArg),scratch=path.resolve(scratchArg);
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
assert.equal(port,13033,'assigned lane UI port required');
assert.ok(!fs.existsSync(scratch),'fresh external scratch required');
assert.ok(!scratch.startsWith(path.dirname(frontend)+path.sep)&&!frontend.startsWith(scratch+path.sep),'external scratch required');
for(const dir of [path.dirname(frontend),frontend])assert.ok(!fs.readdirSync(dir).some(n=>n.startsWith('.env')&&!/\.(example|sample|template)$/.test(n)),'dotenv refused');
fs.mkdirSync(scratch);fs.mkdirSync(path.join(scratch,'home'));fs.mkdirSync(path.join(scratch,'tmp'));
const env={PATH:[path.dirname(process.execPath),'/usr/bin','/bin'].join(path.delimiter),HOME:path.join(scratch,'home'),TMPDIR:path.join(scratch,'tmp'),LANG:'C.UTF-8',NEXT_TELEMETRY_DISABLED:'1',PYTHON_DOTENV_DISABLED:'1',NEXT_PUBLIC_API_URL:'http://127.0.0.1:18033',INTERNAL_API_URL:'http://127.0.0.1:18033',NEXT_PUBLIC_SUPABASE_URL:'http://127.0.0.1:18033',NEXT_PUBLIC_SUPABASE_ANON_KEY:'batch11-inert-anon-key',NATIVE_VERIFY_CACHE_DIR:process.env.NATIVE_VERIFY_CACHE_DIR,PLAYWRIGHT_BROWSERS_PATH:process.env.PLAYWRIGHT_BROWSERS_PATH};
assert.ok(path.isAbsolute(env.NATIVE_VERIFY_CACHE_DIR)&&path.isAbsolute(env.PLAYWRIGHT_BROWSERS_PATH));
const base=`http://127.0.0.1:${port}`;
let server,serverClosed,log='';
function start(args){const child=spawn(process.execPath,args,{cwd:frontend,env,detached:true,stdio:['ignore','pipe','pipe']});let error;child.on('error',e=>{error=e;});const closed=new Promise(resolve=>child.once('close',(code,signal)=>resolve({code,signal,error})));return{child,closed};}
async function stop(owned){if(!owned?.child.pid)return;try{process.kill(-owned.child.pid,'SIGTERM');}catch(e){if(e.code!=='ESRCH')throw e;}const timer=setTimeout(()=>{try{process.kill(-owned.child.pid,'SIGKILL');}catch(e){if(e.code!=='ESRCH')throw e;}},10000);try{await owned.closed;}finally{clearTimeout(timer);}try{process.kill(-owned.child.pid,0);assert.fail('owned group survived cleanup');}catch(e){if(e.code!=='ESRCH')throw e;}}
async function main(){
 console.log(JSON.stringify({check:'current-owned-preview-inputs',runtime:{node:process.version,platform:process.platform,arch:process.arch},environment:env,producer_sha256:sha(__filename),browser_entry_sha256:sha(path.join(frontend,'tests/batch7DependencyBrowser.cjs')),buildId:fs.readFileSync(path.join(frontend,'.next/BUILD_ID'),'utf8')}));
 const reservation=net.createServer();await new Promise((resolve,reject)=>{reservation.once('error',reject);reservation.listen(port,'127.0.0.1',resolve);});await new Promise(resolve=>reservation.close(resolve));
 server=start(['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',String(port)]);server.child.stdout.on('data',b=>{log+=b;});server.child.stderr.on('data',b=>{log+=b;});
 try{
  let response;
  for(let i=0;i<100;i++){
   assert.equal(server.child.exitCode,null,log);
   try{response=await fetch(base+'/learn',{redirect:'error',signal:AbortSignal.timeout(1000)});break;}catch{await new Promise(r=>setTimeout(r,100));}
  }
  assert.ok(response,'preview readiness timeout');assert.equal(response.status,200);assert.equal(server.child.exitCode,null,log);
  const html=await response.text(),css={};const assets=[...html.matchAll(/href="([^\"]+\.css[^\"]*)"/g)].map(m=>m[1].replace(/&amp;/g,'&'));assert.ok(assets.length);
  for(const asset of assets){const url=new URL(asset,base);assert.equal(url.origin,base);const r=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(1000)});assert.equal(r.status,200);assert.match(r.headers.get('content-type'),/text\/css/);const body=await r.text();assert.ok(body.length>1000);css[asset]={bytes:Buffer.byteLength(body),sha256:crypto.createHash('sha256').update(body).digest('hex')};}
  console.log(JSON.stringify({check:'actual-production-preview',base,learnStatus:200,css}));
  const browserChild=spawn(process.execPath,['tests/batch7DependencyBrowser.cjs'],{cwd:frontend,env:{...env,DEPENDENCY_PREVIEW_URL:base},detached:true,stdio:'inherit'});
  const owned={child:browserChild,closed:new Promise(resolve=>{browserChild.once('error',e=>resolve({error:e}));browserChild.once('close',(code,signal)=>resolve({code,signal}));})};
  const timer=setTimeout(()=>{try{process.kill(-browserChild.pid,'SIGKILL');}catch(e){if(e.code!=='ESRCH')throw e;}},180000);
  try{const result=await owned.closed;assert.equal(result.error,undefined);assert.equal(result.signal,null);assert.equal(result.code,0);}finally{clearTimeout(timer);await stop(owned);}
 }finally{await stop(server);await assert.rejects(fetch(base+'/learn',{signal:AbortSignal.timeout(1000)}));fs.writeFileSync(path.join(scratch,'server.log'),log,{flag:'wx'});console.log(JSON.stringify({check:'owned-preview-cleanup',port,listenerAbsent:true,groupAbsent:true,serverLog:log}));}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
