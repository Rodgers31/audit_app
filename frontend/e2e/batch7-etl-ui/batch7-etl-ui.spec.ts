import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
const fixture = 'http://127.0.0.1:8162';
const actor = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const encode = (v:unknown) => Buffer.from(JSON.stringify(v)).toString('base64url');
const tokenFor=(uid:string)=>encode({alg:'none',typ:'JWT'})+'.'+encode({sub:uid,exp:4102444800,aud:'authenticated'})+'.inert-signature';
async function renew(page:Page,uid=actor) {
  await page.evaluate(async token=>{
    const client=(globalThis as unknown as {__KPM_SUPABASE_BROWSER_CLIENT__:{auth:{setSession:(v:unknown)=>Promise<unknown>}}}).__KPM_SUPABASE_BROWSER_CLIENT__;
    await client.auth.setSession({access_token:token,refresh_token:'inert-refresh'});
  },tokenFor(uid));
}
async function visibility(page:Page,shown:boolean) {
  await page.evaluate(value=>{
    Object.defineProperty(document,'visibilityState',{configurable:true,value:value?'visible':'hidden'});
    document.dispatchEvent(new Event('visibilitychange'));
  },shown);
}
test.beforeEach(async ({context,page,request}) => {
  await request.post(fixture+'/fixture/reset');
  const token=tokenFor(actor);
  const session={access_token:token,refresh_token:'inert-refresh',token_type:'bearer',expires_in:360000,expires_at:4102444800,user:{id:actor,email:'etl-ui@example.invalid',aud:'authenticated',role:'authenticated',app_metadata:{},user_metadata:{}}};
  await context.addCookies([{name:'sb-127-auth-token',value:'base64-'+encode(session),domain:'127.0.0.1',path:'/'}]);
  await page.route(/https:\/\//, route=>route.abort());
});
test('supported source confirmation accepts a queued receipt and opens detail', async ({page},info) => {
  await page.goto('/admin/etl');
  await expect(page.getByRole('button',{name:'Run Now · oag'})).toBeEnabled();
  await page.screenshot({path:info.outputPath('desktop-ready.png'),fullPage:true});
  await page.getByRole('button',{name:'Run Now · oag'}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'Confirm Run Now'}).click();
  await expect(page.getByText('Command accepted. Queued acceptance is not completed work.')).toBeVisible();
  await page.getByRole('link',{name:'View accepted command'}).click();
  await expect(page.getByRole('heading',{name:'Command receipt'})).toBeVisible();
  await expect(page.getByText('Queued — accepted, awaiting execution.')).toBeVisible();
  await page.screenshot({path:info.outputPath('desktop-queued.png'),fullPage:true});
});
for(const mode of ['unavailable','stale','malformed']) {
  test(mode+' capability is disabled and refresh recovers',async({page,request},info)=>{
    await request.post(fixture+'/fixture/config',{data:{mode}});
    await page.goto('/admin/etl');
    await expect(page.getByRole('button',{name:'Run Now · oag'})).toBeDisabled();
    await expect(page.getByText(mode==='unavailable'?'Dedicated worker dispatch is unavailable.':'Worker evidence unavailable or malformed. Controls are disabled.')).toBeVisible();
    await page.screenshot({path:info.outputPath(mode+'.png'),fullPage:true});
    await request.post(fixture+'/fixture/config',{data:{mode:'ready'}});
    await page.getByRole('button',{name:'Refresh worker evidence'}).click();
    await expect(page.getByRole('button',{name:'Run Now · oag'})).toBeEnabled();
    await expect(page.getByRole('button',{name:'Run Now · treasury'})).toBeDisabled();
  });
}
test('dry run lost response commits once, recovery retains key after worker expiry',async({page,request})=>{
  let lost=true;
  await page.route('**/api/v1/admin/etl/trigger/oag',async route=>{
    if(lost) {lost=false;await route.fetch();await route.abort();} else await route.continue();
  });
  await page.goto('/admin/etl');
  await page.getByRole('button',{name:'Dry Run · oag'}).click();
  await expect(page.getByRole('button',{name:'Recover same intent'})).toBeVisible();
  let requests=await (await request.get(fixture+'/fixture/requests')).json();
  expect(requests).toHaveLength(1);
  expect(requests[0].body.dry_run).toBe(true);
  await request.post(fixture+'/fixture/config',{data:{mode:'unavailable'}});
  await page.getByRole('button',{name:'Refresh worker evidence'}).click();
  await expect(page.getByRole('button',{name:'Run Now · oag'})).toBeDisabled();
  await page.getByRole('button',{name:'Recover same intent'}).click();
  await expect(page.getByText('Original receipt recovered. No second command was accepted.')).toBeVisible();
  await expect(page.getByText('oag · Dry Run — no publication',{exact:true})).toBeVisible();
  requests=await (await request.get(fixture+'/fixture/requests')).json();
  expect(requests).toHaveLength(2);
  expect(requests[1].key).toBe(requests[0].key);
  await expect(page.getByText('20 on this page · 46 commands matching')).toBeVisible();
});
test('history filters, page size, next/back, detail and safe return preserve navigation',async({page})=>{
  await page.goto('/admin/etl');
  await expect(page.getByText('20 on this page · 45 commands matching')).toBeVisible();
  await page.getByRole('button',{name:'Next commands'}).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByText('Page 2',{exact:true})).toBeVisible();
  await page.goBack();
  await expect(page.getByText('Page 1',{exact:true})).toBeVisible();
  await page.getByLabel('Command source',{exact:true}).selectOption('oag');
  await page.getByLabel('Command status',{exact:true}).selectOption('completed');
  await page.getByLabel('Commands per page',{exact:true}).selectOption('10');
  await expect(page.getByText('10 on this page · 45 commands matching')).toBeVisible();
  await page.getByRole('link',{name:/View command /}).first().click();
  await expect(page.getByText('Completed — recorded ingestion observation.')).toBeVisible();
  await expect(page.getByRole('link',{name:/View ingestion observation/})).toHaveAttribute('href',/\/admin\/ingestion\/[1-9]\d*/);
  await page.getByRole('link',{name:'Back to command history'}).click();
  await expect(page.getByLabel('Command status',{exact:true})).toHaveValue('completed');
  await expect(page.getByLabel('Commands per page',{exact:true})).toHaveValue('10');
  await page.getByRole('button',{name:'Clear command filters'}).click();
  await expect(page).toHaveURL(/\/admin\/etl$/);
});
test('hostile query canonicalizes and empty later page retains Previous',async({page})=>{
  await page.goto('/admin/etl?source=evil&status=unknown&page=10001&page_size=999');
  await expect(page).toHaveURL(/\/admin\/etl$/);
  await expect(page.getByText('20 on this page · 45 commands matching')).toBeVisible();
  await page.goto('/admin/etl?page=10');
  await expect(page.getByText('No commands match this page.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Previous commands'})).toBeEnabled();
});
test('malformed history and mismatched detail hide successful observation links',async({page})=>{
  await page.route('**/api/v1/admin/etl/commands?**',route=>route.fulfill({json:{entries:[],page:1,page_size:20,total:45,has_more:true}}));
  await page.goto('/admin/etl');
  await expect(page.getByText('Could not load command history. Refresh to retry.')).toBeVisible();
  expect(await page.getByRole('link',{name:/View command /}).count()).toBe(0);
  await page.unroute('**/api/v1/admin/etl/commands?**');
  await page.getByRole('button',{name:'Refresh command history'}).click();
  await expect(page.getByText('20 on this page · 45 commands matching')).toBeVisible();
  const link=page.getByRole('link',{name:/View command /}).first();
  const href=await link.getAttribute('href');
  await page.route('**/api/v1/admin/etl/commands/*',async route=>{
    const response=await route.fetch();const body=await response.json();
    await route.fulfill({json:{...body,id:'ffffffff-ffff-4fff-8fff-ffffffffffff'}});
  });
  await page.goto(href!);
  await expect(page.getByText('Could not verify this command receipt. Refresh to retry.')).toBeVisible();
  expect(await page.getByRole('link',{name:/View ingestion observation/}).count()).toBe(0);
});
for(const status of ['failed','interrupted']) {
  test(status+' terminal receipt has no automatic execution retry',async({page,request},info)=>{
    const id='00000000-0000-0000-0000-000000000001';
    await request.post(fixture+'/fixture/command/'+id+'/'+status);
    await page.goto('/admin/etl/commands/'+id);
    await expect(page.getByText(status==='failed'?'Failed — execution did not complete.':'Interrupted — execution unverified. Do not automatically repeat.')).toBeVisible();
    expect(await page.getByRole('button',{name:/Run Now|Recover same intent/}).count()).toBe(0);
    expect(await page.getByRole('link',{name:/View ingestion observation/}).count()).toBe(0);
    await page.screenshot({path:info.outputPath(status+'.png'),fullPage:true});
  });
}
test('visible active detail polls, pauses hidden, stops terminal and hides stale result on error',async({page,request})=>{
  await page.goto('/admin/etl');await page.getByRole('button',{name:'Dry Run · oag'}).click();
  await page.getByRole('link',{name:'View accepted command'}).click();
  await expect(page).toHaveURL(/\/admin\/etl\/commands\/[0-9a-f-]+$/);
  const id=page.url().split('/').pop()!;
  let reads=0;page.on('request',r=>{if(r.url().endsWith('/commands/'+id)) reads++;});
  await expect.poll(()=>reads,{timeout:8000}).toBeGreaterThan(0);
  await visibility(page,false);const hiddenReads=reads;
  await page.waitForTimeout(5500);expect(reads).toBe(hiddenReads);
  await request.post(fixture+'/fixture/command/'+id+'/completed');
  await visibility(page,true);
  await expect(page.getByText('Completed — recorded ingestion observation.')).toBeVisible();
  const terminal=reads;await page.waitForTimeout(5500);expect(reads).toBe(terminal);
  await page.route('**/api/v1/admin/etl/commands/'+id,r=>r.fulfill({status:503,json:{detail:'Unavailable.'}}));
  await page.getByRole('button',{name:'Refresh receipt'}).click();
  await expect(page.getByText('Could not verify this command receipt. Refresh to retry.')).toBeVisible();
  expect(await page.getByRole('link',{name:/View ingestion observation/}).count()).toBe(0);
});
test('initial hidden page waits before issuing dispatch/history reads',async({page})=>{
  await page.addInitScript(()=>Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'}));
  let reads=0;page.on('request',r=>{if(/\/admin\/etl\/(dispatch|commands)/.test(r.url())) reads++;});
  await page.goto('/admin/etl');
  await expect(page.getByText('Worker checks paused while this page is hidden.')).toBeVisible();
  expect(reads).toBe(0);
  await visibility(page,true);await expect(page.getByRole('button',{name:'Run Now · oag'})).toBeEnabled();
});
for(const transition of ['actor','renewal','role','hidden']) {
  test('deferred confirmation closes on '+transition+' change',async({page,request})=>{
    await page.goto('/admin/etl');await page.getByRole('button',{name:'Run Now · oag'}).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    if(transition==='actor') await renew(page,'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
    if(transition==='renewal') await renew(page);
    if(transition==='role') {await request.post(fixture+'/fixture/config',{data:{role:'citizen'}});await renew(page);}
    if(transition==='hidden') await visibility(page,false);
    await expect(page.getByRole('dialog')).toBeHidden();
    expect(await (await request.get(fixture+'/fixture/requests')).json()).toHaveLength(0);
  });
}
for(const status of [401,403]) {
  test(status+' mutation denies capability, cancels reads and hides private diagnostics',async({page,request})=>{
    await page.goto('/admin/etl');await expect(page.getByRole('button',{name:'Run Now · oag'})).toBeEnabled();
    await request.post(fixture+'/fixture/config',{data:{deny:status}});
    await page.getByRole('button',{name:'Dry Run · oag'}).click();
    await expect(page.getByText('Administrator access expired. Renew your session to verify access.')).toBeVisible();
    await expect(page.getByRole('button',{name:'Run Now · oag'})).toBeDisabled();
    expect(await page.getByRole('link',{name:/View command /}).count()).toBe(0);
  });
}
for(const transition of ['actor','renewal','role','hidden','unmount']) {
  test('committed in-flight acceptance cannot expose stale success after '+transition,async({page,request})=>{
    let release!:()=>void, committed!:()=>void;
    const gate=new Promise<void>(done=>release=done), acceptance=new Promise<void>(done=>committed=done);
    let hold=true;
    await page.route('**/api/v1/admin/etl/trigger/oag',async route=>{
      if(!hold) {await route.continue();return;}
      hold=false;const response=await route.fetch();committed();await gate;
      try {await route.fulfill({response});} catch {/* The originating lifetime cancelled transport. */}
    });
    await page.goto('/admin/etl');await page.getByRole('button',{name:'Dry Run · oag'}).click();
    await acceptance;
    const original=await (await request.get(fixture+'/fixture/requests')).json();
    expect(original).toHaveLength(1);
    if(transition==='actor') await renew(page,'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
    if(transition==='renewal') await renew(page);
    if(transition==='role') {await request.post(fixture+'/fixture/config',{data:{role:'citizen'}});await renew(page);await expect(page).toHaveURL(/\/$/);}
    if(transition==='hidden') await visibility(page,false);
    if(transition==='unmount') {await page.getByRole('link',{name:'Ingestion',exact:true}).click();await expect(page).toHaveURL(/\/admin\/ingestion$/);await expect(page.getByRole('button',{name:'Run Now · oag'})).toHaveCount(0);}
    release();
    await expect(page.getByText('Command accepted. Queued acceptance is not completed work.')).toHaveCount(0);
    expect(await (await request.get(fixture+'/fixture/requests')).json()).toHaveLength(1);
    if(transition==='hidden') await visibility(page,true);
    if(transition==='unmount') await page.getByRole('link',{name:'ETL Schedule',exact:true}).click();
    if(['renewal','hidden','unmount'].includes(transition)) {
      await page.getByRole('button',{name:'Recover same intent'}).click();
      await expect(page.getByText('Original receipt recovered. No second command was accepted.')).toBeVisible();
      const recovered=await (await request.get(fixture+'/fixture/requests')).json();
      expect(recovered).toHaveLength(2);expect(recovered[1].key).toBe(original[0].key);
    } else expect(await page.getByRole('button',{name:'Recover same intent'}).count()).toBe(0);
  });
}
test('mobile keyboard confirmation traps focus, Escape returns focus, and pages do not overflow',async({page},info)=>{
  await page.setViewportSize({width:375,height:812});
  await page.goto('/admin/etl');
  const run=page.getByRole('button',{name:'Run Now · oag'});
  await expect(run).toBeEnabled();
  await run.focus();await page.keyboard.press('Enter');
  const cancel=page.getByRole('button',{name:'Cancel',exact:true});
  await expect(cancel).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('button',{name:'Confirm Run Now'})).toBeFocused();
  await page.keyboard.press('Escape');await expect(run).toBeFocused();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('mobile-ready.png'),fullPage:true});
  await run.focus();await page.keyboard.press('Enter');await page.keyboard.press('Tab');await page.keyboard.press('Enter');
  await page.getByRole('link',{name:'View accepted command'}).click();
  await expect(page.getByRole('heading',{name:'Command receipt'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath('mobile-receipt.png'),fullPage:true});
});
