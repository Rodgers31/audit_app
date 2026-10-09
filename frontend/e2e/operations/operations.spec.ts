import {test,expect, type BrowserContext} from '@playwright/test';
const adminId='00000000-0000-4000-8000-000000000001';
const viewerId='00000000-0000-4000-8000-000000000002';
function session(id=adminId) {
  const exp=Math.floor(Date.now()/1000)+3600;
  const encoded=(v:unknown)=>Buffer.from(JSON.stringify(v)).toString('base64url');
  const access_token=`${encoded({alg:'HS256',typ:'JWT'})}.${encoded({sub:id,aud:'authenticated',exp,email:'operations@example.invalid'})}.inert-signature`;
  return {access_token,refresh_token:'inert-refresh-token',token_type:'bearer',expires_in:3600,expires_at:exp,
    user:{id,aud:'authenticated',role:'authenticated',email:'operations@example.invalid',app_metadata:{},user_metadata:{},created_at:'2026-01-01T00:00:00Z'}};
}
async function signIn(context:BrowserContext,id=adminId) {
  const value='base64-'+Buffer.from(JSON.stringify(session(id))).toString('base64url');
  await context.addCookies([{name:'sb-127-auth-token',value,domain:'127.0.0.1',path:'/'}]);
}
test.beforeEach(async ({context}) => {
  await signIn(context);
  await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    return ['127.0.0.1','localhost'].includes(url.hostname) ? route.continue() : route.abort();
  });
});
test('real list filters, pagination, history and keyboard detail navigation',async ({page})=>{
  await page.goto('/admin/ingestion');
  await expect(page.getByText('45 jobs in the last 7 days.')).toBeVisible();
  await page.getByRole('button',{name:'Next',exact:true}).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByText('Page 2',{exact:true})).toBeVisible();
  await page.getByLabel('Status',{exact:true}).selectOption('failed');
  await expect(page).toHaveURL(/status=failed/);
  await expect(page).not.toHaveURL(/page=/);
  await expect(page.getByText('15 jobs in the last 7 days.')).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/page=2/);
  const link=page.getByRole('link',{name:'View job #21',exact:true});
  await link.focus(); await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/admin\/ingestion\/21$/);
  await expect(page.getByText('Ingestion job #21',{exact:true})).toBeVisible();
  await expect(page.getByText(/safe operational fields/)).toBeVisible();
  await expect(page.getByText('PRIVATE_DIAGNOSTIC')).toHaveCount(0);
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await page.getByRole('link',{name:'Back to ingestion jobs'}).click();
  await expect(page).toHaveURL(/\/admin\/ingestion\?page=2$/);
  await expect(page.getByText('Page 2',{exact:true})).toBeVisible();
  await page.getByLabel('Domain',{exact:true}).fill('audits');
  await expect(page).toHaveURL(/domain=audits/);
  await expect(page).not.toHaveURL(/page=/);
  await expect(page.getByText('22 jobs in the last 7 days.')).toBeVisible();
  await page.getByLabel('Time window',{exact:true}).selectOption('30');
  await expect(page).toHaveURL(/days=30/);
  await expect(page.getByText('22 jobs in the last 30 days.')).toBeVisible();
  await page.getByRole('button',{name:'Clear filters',exact:true}).click();
  await expect(page).toHaveURL(/\/admin\/ingestion$/);
  await expect(page.getByText('45 jobs in the last 7 days.')).toBeVisible();
});
test('bad URL values are canonicalized, empty later pages can recover, missing IDs are distinct',async ({page})=>{
  const requests:string[]=[];page.on('request',request=>{if(request.url().includes('/api/v1/admin/ingestion-jobs')) requests.push(request.url());});
  await page.goto('/admin/ingestion?days=NaN&page=-2&status=alien');
  await expect(page).toHaveURL(/\/admin\/ingestion$/);
  await expect(page.getByText('45 jobs in the last 7 days.')).toBeVisible();
  expect(requests.some(url=>url.includes('NaN') || url.includes('alien') || url.includes('page=-2'))).toBe(false);
  await page.goto('/admin/ingestion?page=4');
  await expect(page.getByText('No jobs on this page.')).toBeVisible();
  await page.getByRole('button',{name:'Prev',exact:true}).click();
  await expect(page.getByText('Page 3',{exact:true})).toBeVisible();
  await page.goto('/admin/ingestion/999');
  await expect(page.getByText('Job not found.',{exact:true})).toBeVisible();
  await page.goto('/admin/ingestion/invalid');
  await expect(page.getByRole('heading',{name:'Invalid job ID'})).toBeVisible();
});
test('calendar plan and disabled execution controls agree with real rejection',async ({page,request})=>{
  await page.goto('/admin/etl');
  await expect(page.getByText('Planned today',{exact:true})).toBeVisible();
  await expect(page.getByText(/^unverified$/i)).toBeVisible();
  await expect(page.getByText(/The calendar controls below are not connected to worker dispatch\./)).toBeVisible();
  for(const control of ['Trigger','Dry-run']) {
    const buttons=page.getByRole('button',{name:control,exact:true});
    await expect(buttons).toHaveCount(6);
    for(const button of await buttons.all()) await expect(button).toBeDisabled();
  }
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  const token=session().access_token;
  for(const dry_run of [true,false]) {
    const response=await request.post('http://127.0.0.1:8152/api/v1/admin/etl/trigger/oag',
      {headers:{Authorization:`Bearer ${token}`},data:{dry_run}});
    expect(response.status()).toBe(503);
    expect((await response.json()).detail.code).toBe('manual_dispatch_unavailable');
  }
});
test('mobile job cards preserve dry-run and navigation without horizontal overflow',async ({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/admin/ingestion');
  await expect(page.getByText('45 jobs in the last 7 days.')).toBeVisible();
  const mobile=page.locator('main').getByRole('link').filter({hasText:'counties_budget'}).first();
  await expect(mobile).toBeVisible();
  await expect(mobile.getByText('dry-run',{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await mobile.click();
  await expect(page.getByText('Ingestion job #1',{exact:true})).toBeVisible();
});
test('malformed API refreshes fail safely and retry recovers',async ({page})=>{
  await page.goto('/admin/ingestion');
  await expect(page.getByText('45 jobs in the last 7 days.')).toBeVisible();
  await page.route('**/api/v1/admin/ingestion-jobs?*',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({jobs:null,total:true})}));
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await expect(page.getByText('Could not load jobs.')).toBeVisible();
  await expect(page.getByText('45 jobs in the last 7 days.')).toHaveCount(0);
  await page.unroute('**/api/v1/admin/ingestion-jobs?*');
  await page.getByRole('button',{name:'Retry',exact:true}).click();
  await expect(page.getByText('45 jobs in the last 7 days.')).toBeVisible();
});
test('middleware and real route admin guards reject inert viewer and anonymous access',async ({page,context,request})=>{
  await context.clearCookies();await signIn(context,viewerId);
  await page.goto('/admin/ingestion');
  await expect(page).toHaveURL(/unauthorized=1/);
  const response=await request.get('http://127.0.0.1:8152/api/v1/admin/ingestion-jobs',
    {headers:{Authorization:`Bearer ${session(viewerId).access_token}`}});
  expect(response.status()).toBe(403);
  await context.clearCookies();await page.goto('/admin/etl');
  await expect(page).toHaveURL(/authRequired=1/);
});
