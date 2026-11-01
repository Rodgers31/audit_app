/** Hydrated production social UI, contract API fixtures, inert auth; no external connections. */
import {mkdir,readFile,writeFile,symlink,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {chromium} from 'playwright';
import {expect} from '@playwright/test';
import ts from 'typescript';
const root=resolve('.manual-publication-browser'), base='http://127.0.0.1:33551', api='http://127.0.0.1:33552';
const report={boundary:'hydrated production components/hooks/decoders with contract API fixtures and inert auth',checks:[],requests:[],externalRequests:[],interceptedProviderNavigations:[],pageErrors:[]};
await mkdir(resolve(root,'app/[[...slug]]'),{recursive:true});
await writeFile(resolve(root,'package.json'),JSON.stringify({private:true}));
await symlink(resolve('node_modules'),resolve(root,'node_modules')).catch(e=>{if(e.code!=='EEXIST')throw e;});
await writeFile(resolve(root,'tsconfig.json'),JSON.stringify({compilerOptions:{strict:true,jsx:'preserve',target:'es2017',module:'esnext',moduleResolution:'bundler',esModuleInterop:true,baseUrl:'..',paths:{'@/*':['./*']}}}));
await writeFile(resolve(root,'next.config.js'),`module.exports={experimental:{externalDir:true,cpus:2},webpack(c,{webpack}){c.plugins.push(new webpack.NormalModuleReplacementPlugin(/(?:lib\\/auth\\/AuthProvider|lib\\/supabase\\/client)$/,${JSON.stringify(resolve('tests/socialRuntimeAuth.ts'))}));c.resolve.alias['@/lib/auth/AuthProvider']=${JSON.stringify(resolve('tests/socialRuntimeAuth.ts'))};c.resolve.alias['@/lib/supabase/client']=${JSON.stringify(resolve('tests/socialRuntimeAuth.ts'))};return c;}};`);
await writeFile(resolve(root,'app/layout.tsx'),`import { HISTORY_BRIDGE_BOOTSTRAP } from ${JSON.stringify(resolve("lib/navigation/historyBridge"))}; export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body><script dangerouslySetInnerHTML={{__html:HISTORY_BRIDGE_BOOTSTRAP}} />{children}</body></html>}`);
await writeFile(resolve(root,'app/[[...slug]]/page.tsx'),`export {default} from '../../../tests/socialRuntimeHarness';`);
await mkdir(resolve(root,'app/admin/social/accounts/callback'),{recursive:true});
await writeFile(resolve(root,'app/admin/social/accounts/callback/route.ts'),`import {GET as callback} from ${JSON.stringify(resolve('app/admin/social/accounts/callback/route'))}; export const dynamic='force-dynamic'; export const GET=callback;`);
await writeFile(resolve(root,'fixtures.mjs'),ts.transpileModule(await readFile(resolve('tests/socialFixtures.ts'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText);
const fx=await import(resolve(root,'fixtures.mjs'));
let current=fx.post(), status=fx.system, accountList=fx.accounts, libraryAvailable=true, failPublish=false, malformedReceipt=false;
const asset={id:fx.assetId,version:1,filename:'inert-evidence.png',state:'ready',mime_type:'image/png',byte_size:12345,sha256:'a'.repeat(64),width:1200,height:630,duration_ms:null,default_alt_text:'Inert evidence card',safe_error:null,created_at:'2026-10-03T12:00:00Z'};
const fixtureEnv={PATH:process.env.PATH,NODE_ENV:'production',NEXT_TELEMETRY_DISABLED:'1',NEXT_PUBLIC_API_URL:api};
const build=spawn(process.execPath,[resolve('node_modules/next/dist/bin/next'),'build',root,'--no-lint'],{env:fixtureEnv,stdio:['ignore','pipe','pipe']});
let buildLog='';build.stdout.on('data',d=>buildLog+=d);build.stderr.on('data',d=>buildLog+=d);
const [buildCode]=await once(build,'exit');if(buildCode!==0){await writeFile('/tmp/admin-manual-publication-build.log',buildLog);await rm(root,{recursive:true,force:true});throw new Error('Fixture production build failed');}
const server=spawn(process.execPath,[resolve('node_modules/next/dist/bin/next'),'start',root,'--hostname','127.0.0.1','--port','33551'],{env:fixtureEnv,stdio:['ignore','pipe','pipe']});
let logs='',browser,readyTimer;server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
try {
 await Promise.race([new Promise((done,reject)=>{server.stdout.on('data',d=>{if(String(d).includes('Ready in'))done();});server.once('exit',code=>reject(new Error('Fixture server exited '+code)));}),new Promise((_,reject)=>readyTimer=setTimeout(()=>reject(new Error('Startup timeout')),60000))]);
 browser=await chromium.launch({headless:true}); const context=await browser.newContext({viewport:{width:1440,height:1000}});
 context.on('page',p=>p.on('pageerror',e=>report.pageErrors.push(e.message)));
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url()); if(url.origin===base)return route.continue();
  if(url.origin!==api){report.externalRequests.push(url.origin);return route.abort();}
  if(req.method()==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':base,'Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}});
  const path=url.pathname.slice('/api/v1/admin/social'.length),method=req.method(),body=req.postDataJSON();
  report.requests.push({method,path,key:req.headers()['idempotency-key'],body}); let value,code=200;
  const error=(message)=>({detail:{code:'INVALID_RESPONSE',message,request_id:fx.actorId,retryable:false,field_errors:[],target_errors:[]}});
  if(path==='/system/status')value=status;
  else if(path==='/accounts')value={accounts:accountList};
  else if(path==='/media/capabilities')value={upload_available:false,library_available:libraryAvailable,allowed_mime_types:[],max_image_bytes:10485760,max_video_bytes:52428800,unavailable_reason:libraryAvailable?'Inert fixture: uploads paused; inspected library remains available.':'Inert fixture: uploads and library are unavailable.'};
  else if(path==='/media/assets')value={assets:[asset],total:1,page:1,page_size:20,has_more:false};
  else if(path.endsWith('/preview')){value=error('Inert preview intentionally unavailable.');code=503;}
  else if(path==='/posts'&&method==='POST'){current=fx.post(body);value=current;code=201;}
  else if(path.endsWith('/evidence'))value={post_id:current.id,revision_id:current.revision_id,source_event_id:null,generator_metadata:{template_version:'inert-v1'},evidence:{evidence_version:1,source:{source_type:'fixture',source_key:'inert',ingestion_id:'1',facts:[]}}};
  else if(path.endsWith('/validate'))value=fx.validation(current);
  else if(method==='PATCH'){current=fx.post({...current,...body,version:current.version+1,revision_id:'00000000-0000-4000-8000-'+String(40+current.version+1).padStart(12,'0')});value=current;}
  else if(path.endsWith('/publish')){
    if(failPublish){value=error('The publication response could not be confirmed. Refresh results before retrying this command.');code=502;}
    else {value=fx.publicationReceipt(current,{scheduled_for:new Date().toISOString()});if(malformedReceipt)value={...value,targets:[]};else current=fx.post({...current,version:current.version+1,editorial_state:'approved',targets:[{...fx.target('queued'),next_action_at:value.scheduled_for}],publication:{revision_id:current.revision_id,scheduled_for:value.scheduled_for,schedule_timezone:'UTC',requested_local_time:value.scheduled_for.slice(0,-1)},delivery_status:'queued'});code=202;}
  }
  else if(method==='GET'&&(path==='/posts/'+current.id||path==='/posts/'+current.id+'/status'))value=current;
  else throw new Error('Unexpected inert API request: '+method+' '+path);
  await route.fulfill({status:code,contentType:'application/json',headers:{'Cache-Control':'private, no-store','Access-Control-Allow-Origin':base},body:JSON.stringify(value)});
 });
 const page=await context.newPage();
 // Read-only off state: no mutation, no hidden enablement.
 status={...fx.system,publishing_enabled:false};accountList=[{...fx.accounts[0],publishing_enabled:false}];libraryAvailable=false;
 await page.goto(base+'/admin/social/'+fx.postId);
 await expect(page.getByRole('button',{name:'Publish now',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Publish now',exact:true})).toBeDisabled();
 await expect(page.getByText('Inert fixture: uploads and library are unavailable.')).toBeVisible();
 await expect(page.getByRole('button',{name:'Choose from library',exact:true})).toBeDisabled();
 await expect(page.getByRole('region',{name:'Publication readiness'})).toContainText('Publishing is paused at the system level');
 await expect(page.getByRole('region',{name:'Publication readiness'})).toContainText('account publishing is disabled');
 expect(report.requests.filter(r=>r.method!=='GET')).toEqual([]);report.checks.push('off controls + media unavailable render visible exact reasons with zero mutations');
 const shots=resolve('../docs/releases/admin-publish-workflow-20261101');await mkdir(shots,{recursive:true});await page.screenshot({path:resolve(shots,'manual-off-desktop.png'),fullPage:true});
 // Stale worker, otherwise valid revision.
 status={...fx.deliverySystem(),worker:{...fx.deliverySystem().worker,state:'stale'}};accountList=fx.accounts;libraryAvailable=true;
 await page.reload();await page.getByRole('button',{name:'Save & validate',exact:true}).click();
 await expect(page.getByText(/All selected destinations passed/)).toBeVisible();await expect(page.getByRole('button',{name:'Publish now',exact:true})).toBeDisabled();
 await expect(page.getByRole('region',{name:'Publication readiness'})).toContainText('Delivery worker status is stale');report.checks.push('valid saved revision + stale worker blocks immediate delivery');
 // Add inspected media and edit alt text; save must preserve exact media reference.
 status=fx.deliverySystem();current=fx.post();await page.goto(base+'/admin/social/new');
 await page.getByLabel('Post text',{exact:true}).fill('Inert manually reviewed evidence.');
 await page.getByRole('checkbox',{name:/Facebook · AuditGava test Page/}).check();
 await page.getByRole('button',{name:'Choose from library',exact:true}).click();await page.getByRole('button',{name:'Use inert-evidence.png'}).click();
 await page.getByLabel('Master media 1 alt text',{exact:true}).fill('Human reviewed evidence description');
 await page.getByRole('button',{name:'Save draft',exact:true}).click();await expect(page).toHaveURL(new RegExp(fx.postId));
 const created=report.requests.find(r=>r.method==='POST'&&r.path==='/posts');expect(created.body.document.master.media).toEqual([{asset_id:fx.assetId,alt_text:'Human reviewed evidence description',caption_asset_id:null}]);
 await page.getByRole('button',{name:'Save & validate',exact:true}).click();await expect(page.getByRole('button',{name:'Publish now',exact:true})).toBeEnabled();
 await expect(page.getByRole('region',{name:'Resolved post preview'})).toContainText('Inert manually reviewed evidence.');
 // Failed/ambiguous result preserves command identity; bad receipt never reports success.
 failPublish=true;await page.getByRole('button',{name:'Publish now',exact:true}).click();await expect(page.locator('article').getByRole('alert')).toContainText('could not be confirmed');
 await page.getByRole('button',{name:'Save & validate',exact:true}).click();await expect(page.getByRole('button',{name:'Publish now',exact:true})).toBeEnabled();
 failPublish=false;malformedReceipt=true;await page.getByRole('button',{name:'Publish now',exact:true}).click();await expect(page.locator('article').getByRole('alert')).toContainText('did not confirm the exact post');
 expect(report.requests.filter(r=>r.path.endsWith('/publish'))[0]).toEqual(report.requests.filter(r=>r.path.endsWith('/publish'))[1]);
 await expect(page.getByText(/Publication accepted/)).toHaveCount(0);report.checks.push('publication error and malformed receipt preserve key/body and never claim publication');
 malformedReceipt=false;await page.getByRole('button',{name:'Save & validate',exact:true}).click();await expect(page.getByRole('button',{name:'Publish now',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'Publish now',exact:true}).click();await expect(page.getByText(/Publication accepted for 1 destination/)).toBeVisible();
 await expect(page.getByText('approved · version '+current.version,{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Load current revision',exact:true})).toHaveCount(0);
 await expect(page.getByRole('link',{name:/View Facebook post/})).toHaveCount(0);expect(report.requests.filter(r=>r.path.endsWith('/publish'))[2]).toEqual(report.requests.filter(r=>r.path.endsWith('/publish'))[0]);
 report.checks.push('manual create + library media + alt text + save + validate + reviewed preview + human publish accepts queued receipt only');
 await page.screenshot({path:resolve(shots,'manual-queued-desktop.png'),fullPage:true});
 // Existing generated drafts start in Preview on mobile; media controls stay outside the hidden editor.
 current=fx.post({origin_type:'generated',editorial_state:'pending_review',references:[{url:'https://example.invalid/inert-source',label:'Inert source'}]});status=fx.deliverySystem();await page.setViewportSize({width:390,height:900});await page.goto(base+'/admin/social/'+fx.postId);
 await expect(page.getByRole('button',{name:'Preview',exact:true})).toHaveAttribute('aria-pressed','true');
 await expect(page.getByRole('button',{name:'Choose from library',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Choose from library',exact:true}).click();await page.getByRole('button',{name:'Use inert-evidence.png'}).click();
 await expect(page.getByRole('button',{name:'Publish now',exact:true})).toBeEnabled();
 await expect(page.getByRole('region',{name:'Resolved post preview'})).toContainText('Inert evidence card');
 await page.getByRole('checkbox',{name:/I checked the facts and sources/}).check();
 const generatedRevision=current.revision_id, generatedVersion=current.version;
 await page.getByRole('button',{name:'Publish now',exact:true}).click();await expect(page.getByText(/Publication accepted for 1 destination/)).toBeVisible();
 await expect(page.getByText('approved · version '+current.version,{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Load current revision',exact:true})).toHaveCount(0);await expect(page.getByRole('checkbox',{name:/I checked the facts and sources/})).toBeChecked();await expect(page.getByText('Publication was requested for this saved revision. Review the delivery results below.',{exact:true})).toBeVisible();await expect(page.getByText('Checking the saved revision…',{exact:true})).toHaveCount(0);
 expect(report.requests.filter(r=>r.path.endsWith('/publish')).at(-1).body).toMatchObject({expected_version:generatedVersion,revision_id:generatedRevision,review_attestation:{facts_checked:true,sources_checked:true}});
 await expect(page.getByRole('link',{name:/View Facebook post/})).toHaveCount(0);await page.screenshot({path:resolve(shots,'generated-queued-mobile.png'),fullPage:true});report.checks.push('generated mobile default preview + visible media + automatic saved revision validation + human reviewed Publish with exact revision attestation');
 for(const width of [390,320]){await page.setViewportSize({width,height:900});current=fx.post();status={...fx.system,publishing_enabled:false};await page.goto(base+'/admin/social/'+fx.postId);await expect(page.getByRole('button',{name:'Publish now',exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.getByRole('button',{name:'Preview',exact:true}).click();await expect(page.getByRole('region',{name:'Resolved post preview'})).toBeVisible();}
 await page.screenshot({path:resolve(shots,'manual-off-mobile.png'),fullPage:true});report.checks.push('390/320px visible publication control, preview interaction, no horizontal overflow');
 expect(report.externalRequests).toEqual([]);expect(report.pageErrors).toEqual([]);await writeFile('/tmp/admin-manual-publication-browser.json',JSON.stringify(report,null,2));console.log(JSON.stringify({...report,requests:report.requests.length},null,2));
} catch(error) { const failedPage=browser?.contexts()[0]?.pages()[0]; if(failedPage){await writeFile('/tmp/admin-manual-publication-failure.txt',await failedPage.locator('body').innerText());await failedPage.screenshot({path:'/tmp/admin-manual-publication-failure.png',fullPage:true});} await writeFile('/tmp/admin-manual-publication-failure-requests.json',JSON.stringify(report,null,2));throw error; } finally { clearTimeout(readyTimer);await writeFile('/tmp/admin-manual-publication-server.log',logs);await browser?.close();server.kill('SIGTERM');await Promise.race([once(server,'exit'),new Promise(done=>setTimeout(done,5000))]);await rm(root,{recursive:true,force:true}); }
