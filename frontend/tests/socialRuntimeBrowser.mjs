/** Hydrated production social UI, contract API fixtures, inert auth; no external connections. */
import {mkdir,readFile,writeFile,symlink,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {chromium} from 'playwright';
import {expect} from '@playwright/test';
import ts from 'typescript';
const root=resolve('.social-runtime-browser'), base='http://127.0.0.1:3154', api='http://127.0.0.1:8154';
const report={boundary:'hydrated production components/hooks/decoders with contract API fixtures and inert auth',checks:[],requests:[],externalRequests:[],interceptedProviderNavigations:[],pageErrors:[]};
await mkdir(resolve(root,'app/[[...slug]]'),{recursive:true});
await writeFile(resolve(root,'package.json'),JSON.stringify({private:true}));
await symlink(resolve('node_modules'),resolve(root,'node_modules')).catch(e=>{if(e.code!=='EEXIST')throw e;});
await writeFile(resolve(root,'tsconfig.json'),JSON.stringify({compilerOptions:{strict:true,jsx:'preserve',target:'es2017',module:'esnext',moduleResolution:'bundler',esModuleInterop:true,baseUrl:'..',paths:{'@/*':['./*']}}}));
await writeFile(resolve(root,'next.config.js'),`module.exports={experimental:{externalDir:true,cpus:2},webpack(c,{webpack}){c.plugins.push(new webpack.NormalModuleReplacementPlugin(/(?:lib\\/auth\\/AuthProvider|lib\\/supabase\\/client)$/,${JSON.stringify(resolve('tests/socialRuntimeAuth.ts'))}));c.resolve.alias['@/lib/auth/AuthProvider']=${JSON.stringify(resolve('tests/socialRuntimeAuth.ts'))};c.resolve.alias['@/lib/supabase/client']=${JSON.stringify(resolve('tests/socialRuntimeAuth.ts'))};return c;}};`);
await writeFile(resolve(root,'app/layout.tsx'),`export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}`);
await writeFile(resolve(root,'app/[[...slug]]/page.tsx'),`export {default} from '../../../tests/socialRuntimeHarness';`);
await mkdir(resolve(root,'app/admin/social/accounts/callback'),{recursive:true});
await writeFile(resolve(root,'app/admin/social/accounts/callback/route.ts'),`import {GET as callback} from ${JSON.stringify(resolve('app/admin/social/accounts/callback/route'))}; export const dynamic='force-dynamic'; export const GET=callback;`);
await writeFile(resolve(root,'fixtures.mjs'),ts.transpileModule(await readFile(resolve('tests/socialFixtures.ts'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText);
const fx=await import(resolve(root,'fixtures.mjs'));
let current=fx.post(), failMutation=false, denyApi=false, malformed=false, connectionAvailable=false, accountList=fx.accounts;
const oauthState='a'.repeat(43), flowId=fx.actorId;
const nativeAccount={...fx.accounts[0],publishing_enabled:false,profile_url:'https://www.facebook.com/901'};
const health={account_id:fx.facebookId,external_account_id:'901',api_product:'facebook_pages',connection_method:'facebook_login',connection_state:'connected',credential_kind:'facebook_page',credential_id:flowId,credential_version:1,key_version:'inert-v1',access_expires_at:null,data_access_expires_at:null,parent_access_expires_at:null,parent_data_access_expires_at:null,parent_grant_reconnect_required:false,granted_scopes:['pages_show_list'],missing_scopes:[],checked_at:null,last_api_success_at:null,reconnect_required:false,publishing_enabled:false,renewal_strategy:'facebook_login_reconnect',provider_revocation_confirmed:false};
const asset={id:fx.assetId,version:1,filename:'inert-evidence.png',state:'ready',mime_type:'image/png',byte_size:12345,sha256:'a'.repeat(64),width:1200,height:630,duration_ms:null,default_alt_text:'Inert evidence card',safe_error:null,created_at:'2026-10-03T12:00:00Z'};
const fixtureEnv={PATH:process.env.PATH,NODE_ENV:'production',NEXT_TELEMETRY_DISABLED:'1',NEXT_PUBLIC_API_URL:api};
const build=spawn(process.execPath,[resolve('node_modules/next/dist/bin/next'),'build',root,'--no-lint'],{env:fixtureEnv,stdio:['ignore','pipe','pipe']});
let buildLog='';build.stdout.on('data',d=>buildLog+=d);build.stderr.on('data',d=>buildLog+=d);
const [buildCode]=await once(build,'exit');if(buildCode!==0){await writeFile('/tmp/admin-social-batch6-browser-server.log',buildLog);await rm(root,{recursive:true,force:true});throw new Error('Fixture production build failed');}
const server=spawn(process.execPath,[resolve('node_modules/next/dist/bin/next'),'start',root,'--hostname','127.0.0.1','--port','3154'],{env:fixtureEnv,stdio:['ignore','pipe','pipe']});
let logs='',browser,readyTimer;server.stdout.on('data',d=>logs+=d);server.stderr.on('data',d=>logs+=d);
try{
 await Promise.race([new Promise((done,reject)=>{server.stdout.on('data',d=>{if(String(d).includes('Ready in'))done();});server.once('exit',code=>reject(new Error('Fixture server exited '+code)));}),new Promise((_,reject)=>readyTimer=setTimeout(()=>reject(new Error('Startup timeout')),60000))]);
 browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1440,height:1000}});context.on('page',p=>p.on('pageerror',e=>report.pageErrors.push(e.message)));
 context.on('response',async response=>{if(new URL(response.url()).pathname==='/admin/social/accounts/callback')report.callbackHeaders=await response.allHeaders();});
 const page=await context.newPage();
 const routeRequest=async route=>{
  const req=route.request(),url=new URL(req.url());if(url.origin===base)return route.continue();
  if(req.method()==='GET'&&url.origin==='https://www.facebook.com'&&connectionAvailable&&url.pathname==='/v26.0/dialog/oauth'&&!url.username&&!url.password&&!url.hash&&url.searchParams.get('state')===oauthState&&url.searchParams.get('response_type')==='code'&&url.searchParams.get('redirect_uri')===base+'/admin/social/accounts/callback'&&!['access_token','refresh_token','client_secret','code'].some(key=>url.searchParams.has(key))){report.interceptedProviderNavigations.push({origin:url.origin,path:url.pathname});return route.fulfill({status:302,headers:{Location:base+'/admin/social/accounts/callback?code=inert-browser-code&state='+oauthState}});}
  if(url.origin!==api){report.externalRequests.push(url.origin);return route.abort();}
  const prefix='/api/v1/admin/social';
  if(!url.pathname.startsWith(prefix+'/'))throw new Error('Unexpected fixture API prefix');
  const path=url.pathname.slice(prefix.length),method=req.method();
  if(method==='OPTIONS')return route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':base,'Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}});
  const supported=new Set(['GET /system/status','GET /accounts','GET /connections/meta/status','POST /connections/meta/start','POST /connections/meta/complete','POST /connections/meta/flows/'+flowId+'/select','GET /accounts/'+fx.facebookId+'/health','POST /accounts/'+fx.facebookId+'/disconnect','GET /media/capabilities','GET /media/assets','GET /media/assets/'+fx.assetId+'/preview','GET /posts','POST /posts','GET /posts/'+current.id,'GET /posts/'+current.id+'/status','GET /posts/'+current.id+'/history','PATCH /posts/'+current.id,...['validate','submit','approve','schedule'].map(action=>'POST /posts/'+current.id+'/'+action)]);
  if(!supported.has(method+' '+path))throw new Error('Unexpected fixture contract: '+method+' '+path);
  const body=req.postDataJSON();report.requests.push({method,pathname:url.pathname,path,key:req.headers()['idempotency-key'],body});
  let value,status=200;const error=(code,message,http)=>{status=http;return {detail:{code,message,request_id:fx.actorId,retryable:false,field_errors:[],target_errors:[]}};};
  if(denyApi)value=error('PERMISSION_DENIED','Fixture administrator permission denied.',403);
  else if(malformed&&path==='/system/status')value={publishing_enabled:true};
  else if(path==='/system/status')value=fx.system;
  else if(path==='/accounts')value={accounts:accountList};
  else if(path==='/connections/meta/status')value={provider:'meta',available:connectionAvailable,access_mode:connectionAvailable?'owned_standard':'unverified',scopes:connectionAvailable?['pages_show_list']:[],blockers:connectionAvailable?[]:['CONNECTIONS_DISABLED'],publishing_adapter_available:false};
  else if(path==='/connections/meta/start')value={flow_id:flowId,expires_at:new Date(Date.now()+600000).toISOString(),authorize_url:'https://www.facebook.com/v26.0/dialog/oauth?response_type=code&state='+oauthState+'&redirect_uri='+encodeURIComponent(base+'/admin/social/accounts/callback')};
  else if(path==='/connections/meta/complete')value={flow_id:flowId,expires_at:new Date(Date.now()+600000).toISOString(),granted_scopes:['pages_show_list'],choices:[{page_id:'901',display_name:'Inert Page',tasks:['CREATE_CONTENT'],instagram_id:'801',instagram_name:'Inert IG',instagram_handle:'inert',page_eligible:true,instagram_eligible:false,missing_page_scopes:[],missing_instagram_scopes:['instagram_content_publish']}]};
  else if(path==='/connections/meta/flows/'+flowId+'/select'){accountList=[nativeAccount];value={flow_id:flowId,accounts:accountList};}
  else if(path==='/accounts/'+fx.facebookId+'/health')value=health;
  else if(path==='/accounts/'+fx.facebookId+'/disconnect'){health.connection_state='disconnected';accountList=[{...nativeAccount,connection_state:'disconnected'}];value=health;}
  else if(path==='/media/capabilities')value={upload_available:false,library_available:true,allowed_mime_types:[],max_image_bytes:10485760,max_video_bytes:52428800,unavailable_reason:'Contract fixture: upload remains disabled.'};
  else if(path==='/media/assets'){const empty=url.searchParams.get('q')==='missing';value={assets:empty?[]:[asset],total:empty?0:1,page:1,page_size:20,has_more:false};}
  else if(path.endsWith('/preview'))value=error('MEDIA_UNAVAILABLE','Preview intentionally unavailable in this inert fixture.',503);
  else if(path==='/posts'&&method==='GET')value={posts:[current],total:1,page:1,page_size:20,has_more:false};
  else if(path==='/posts'&&method==='POST'){current=fx.post(body);value=current;status=201;}
  else if(path.endsWith('/validate'))value=fx.validation(current);
  else if(path.endsWith('/history'))value={post_id:current.id,targets:current.historical_targets,total:current.historical_target_count,page:1,page_size:20,has_more:false};
  else if(method==='PATCH'){if(failMutation)value=error('VERSION_CONFLICT','A newer revision exists. Refresh before saving.',409);else{current={...current,...body,version:current.version+1};delete current.expected_version;value=current;}}
  else if(path.endsWith('/submit')){current={...current,version:current.version+1,editorial_state:'pending_review',delivery_status:'pending_review'};value=current;}
  else if(path.endsWith('/approve')){current=fx.post({...current,version:current.version+1,editorial_state:'approved',delivery_status:'ready',publication:{}});current.targets=[fx.target('ready')];value=current;}
  else if(path.endsWith('/schedule')){const local=body.schedule.local_time;current.publication={...current.publication,scheduled_for:local+'Z',requested_local_time:local,schedule_timezone:body.schedule.timezone};current.targets=[{...fx.target('queued'),next_action_at:local+'Z'}];current.delivery_status='scheduled';value=fx.publicationReceipt(current);status=202;}
  else if(method==='GET'&&(path==='/posts/'+current.id||path==='/posts/'+current.id+'/status'))value=current;
  else throw new Error('Unexpected fixture contract: '+method+' '+path);
  await route.fulfill({status,contentType:'application/json',headers:{'Cache-Control':'private, no-store','Access-Control-Allow-Origin':base},body:JSON.stringify(value)});
 };
 await context.route('**/*',routeRequest);
 await page.goto(base+'/admin/social/new');
 await page.getByLabel('Internal title').fill('Rendered manual fixture');await page.getByLabel('Master text',{exact:true}).fill('Reviewed fixture evidence only.');
 await page.getByRole('checkbox',{name:/Facebook · AuditGava test Page/}).check();await page.getByRole('button',{name:'Save draft',exact:true}).click();
 await expect(page).toHaveURL(new RegExp(fx.postId));await expect(page.getByLabel('Internal title')).toHaveValue('Rendered manual fixture');
 await page.getByRole('button',{name:'Save & validate',exact:true}).click();await expect(page.getByRole('region',{name:'Backend validation'})).toBeVisible();
 await page.getByRole('button',{name:'Submit for review',exact:true}).click();await expect(page.getByRole('button',{name:'Approve revision'})).toBeVisible();
 await page.getByRole('button',{name:'Save & validate',exact:true}).click();await page.getByRole('button',{name:'Approve revision'}).click();await expect(page.getByText(/approved · revision/)).toBeVisible();
 await page.getByRole('button',{name:'Save & validate',exact:true}).click();await page.getByRole('button',{name:'Schedule',exact:true}).click();
 await page.getByLabel('Local publish time',{exact:true}).fill('2027-01-08T12:00');await page.getByLabel('IANA timezone',{exact:true}).fill('UTC');await page.getByRole('button',{name:'Confirm schedule',exact:true}).click();
 await expect(page.getByText(/Schedule accepted for 1 destination/)).toBeVisible();report.checks.push('manual draft/validation/submit/review/approval/schedule');
 await page.goto(base+'/admin/social');await page.getByRole('button',{name:'Scheduled',exact:true}).click();await page.getByRole('button',{name:/Rendered manual fixture/}).click();await expect(page.getByRole('region',{name:'Schedule management'})).toBeVisible();
 current.targets=[{...fx.target('published'),published_at:'2026-10-08T12:00:00Z',remote_url:'https://example.invalid/inert-post'}];current.historical_targets=current.targets.map(t=>({...t,publication_id:current.publication.id,revision_id:current.revision_id,approved_at:current.publication.approved_at,approved_by:fx.actorId,scheduled_for:current.publication.scheduled_for,cancel_requested_at:null,revoked_at:null,updated_at:current.updated_at}));current.historical_target_count=1;
 await page.getByRole('button',{name:'History',exact:true}).click();await expect(page.getByRole('link',{name:'View Facebook published post'})).toHaveAttribute('href','https://example.invalid/inert-post');await page.getByRole('button',{name:/Rendered manual fixture/}).click();await expect(page.getByRole('region',{name:'Delivery history'})).toBeVisible();report.checks.push('scheduled queue and independent confirmed history');
 await page.goto(base+'/admin/social/accounts');await expect(page.getByRole('button',{name:'Connect owned Meta accounts'})).toBeDisabled();report.checks.push('accounts operational connection gate');
 connectionAvailable=true;await page.getByRole('button',{name:'Refresh accounts'}).click();await expect(page.getByRole('button',{name:'Connect owned Meta accounts'})).toBeEnabled();
 await page.getByRole('button',{name:'Connect owned Meta accounts'}).click();await expect(page.getByRole('heading',{name:'Confirm account identities'})).toBeVisible();
 await page.getByRole('combobox').selectOption('901');await expect(page.getByRole('checkbox',{name:/Also connect Inert IG/})).toBeDisabled();await page.getByRole('button',{name:'Confirm selected identities'}).click();
 await expect(page.getByText('Selected accounts connected. Publishing remains disabled.')).toBeVisible();await expect(page.getByText('Publishing disabled. Publishing adapter registered; delivery gates still apply.',{exact:true})).toBeVisible();
 const selected=report.requests.find(r=>r.path.endsWith('/select'));expect(selected.body.page_id).toBe('901');expect(selected.body.instagram_id).toBeNull();expect(report.requests.filter(r=>r.path==='/connections/meta/complete')).toHaveLength(1);
 expect(report.interceptedProviderNavigations).toHaveLength(1);expect(report.callbackHeaders['cache-control']).toBe('private, no-store');expect(report.callbackHeaders['referrer-policy']).toBe('no-referrer');expect(report.callbackHeaders['content-security-policy']).toContain("default-src 'none'");
 await page.getByRole('button',{name:'Connection details',exact:true}).click();await expect(page.getByText('Account ID: 901',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Disable local connection',exact:true}).click();await expect(page.getByRole('button',{name:'Disable local connection',exact:true})).toBeDisabled();await expect(page.getByText(/· disconnected/)).toBeVisible();
 report.checks.push('inert intercepted OAuth callback/discovery/exact selection/native metadata/health/local disconnect');connectionAvailable=false;accountList=fx.accounts;

 current=fx.post();await page.goto(base+'/admin/social/'+fx.postId);await page.getByRole('button',{name:'Choose from library',exact:true}).first().click();await expect(page.getByText('inert-evidence.png',{exact:true})).toBeVisible();
 await page.getByLabel('Search filenames').fill('missing');await page.getByRole('button',{name:'Search library'}).click();await expect(page.getByText('No ready media matches these filters.')).toBeVisible();
 await page.getByLabel('Search filenames').fill('');await page.getByRole('button',{name:'Search library'}).click();await page.getByRole('button',{name:'Use inert-evidence.png'}).click();await expect(page.getByLabel('Master media 1 alt text')).toHaveValue('Inert evidence card');await expect(page.getByRole('button',{name:'Upload media',exact:true}).first()).toBeDisabled();report.checks.push('media search/empty/select/alt text and upload gate');
 await page.getByLabel('Internal title').fill('Unsaved fixture edits');failMutation=true;await page.getByRole('button',{name:'Save draft',exact:true}).click();await expect(page.getByText(/A newer revision exists/)).toBeVisible();await page.getByRole('button',{name:'Save draft',exact:true}).click();
 await expect.poll(()=>report.requests.filter(r=>r.method==='PATCH').length).toBe(2);const commands=report.requests.filter(r=>r.method==='PATCH');expect(commands[0]).toEqual(commands[1]);await expect(page.getByLabel('Internal title')).toHaveValue('Unsaved fixture edits');report.checks.push('stale/repeated command preserves key/body/local edits');
 failMutation=false;denyApi=true;await page.goto(base+'/admin/social');await expect(page.getByText('Fixture administrator permission denied.').first()).toBeVisible();report.checks.push('API permission error rendered');
 denyApi=false;malformed=true;await page.goto(base+'/admin/social');await expect(page.getByText('Publishing status unavailable',{exact:true})).toBeVisible();report.checks.push('malformed status fails closed');malformed=false;
 for(const width of [390,320]){await page.setViewportSize({width,height:900});await page.goto(base+'/admin/social/new');await page.getByRole('button',{name:'Preview',exact:true}).click();await expect(page.getByRole('region',{name:'Resolved post preview'})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
 await page.keyboard.press('Tab');const focus=await page.evaluate(()=>({style:getComputedStyle(document.activeElement).outlineStyle,width:getComputedStyle(document.activeElement).outlineWidth}));expect(focus.style).not.toBe('none');expect(parseFloat(focus.width)).toBeGreaterThanOrEqual(2);report.checks.push('320/390 mobile panel, overflow, visible keyboard focus');
 denyApi=true;
 for(const role of ['editor','signed-out']){const roleContext=await browser.newContext();roleContext.on('page',p=>p.on('pageerror',e=>report.pageErrors.push(e.message)));await roleContext.addInitScript(value=>{window.__SOCIAL_FIXTURE_ROLE__=value;},role);await roleContext.route('**/*',routeRequest);const rolePage=await roleContext.newPage();const before=report.requests.filter(r=>r.method!=='GET').length;await rolePage.goto(base+'/admin/social/new');await expect(rolePage.getByRole('heading',{name:'Access Restricted'})).toBeVisible();await expect(rolePage.getByText(role==='editor'?'This page is restricted to administrators.':'You must be signed in to view this page.')).toBeVisible();await expect(rolePage).toHaveURL(base+'/');await expect(rolePage.getByRole('button',{name:'Save draft',exact:true})).toHaveCount(0);expect(report.requests.filter(r=>r.method!=='GET').length).toBe(before);await roleContext.close();}
 report.checks.push('production client AdminGuard redirects editor/signed-out without mutations');

 expect(report.externalRequests).toEqual([]);expect(report.pageErrors).toEqual([]);await writeFile('/tmp/admin-social-batch6-browser.json',JSON.stringify(report,null,2));console.log(JSON.stringify({...report,requests:report.requests.length},null,2));
}catch(error){await writeFile('/tmp/admin-social-batch6-browser-server.log',logs);throw error;}
finally{clearTimeout(readyTimer);await browser?.close();server.kill('SIGTERM');await Promise.race([once(server,'exit'),new Promise(done=>setTimeout(done,5000))]);await rm(root,{recursive:true,force:true});}
