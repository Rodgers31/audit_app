// Actual rendered components, isolated loopback files, no application/network APIs.
import { createServer } from 'node:http';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';
const directory=resolve('.media-preview'), allowed=new Set(['library.html','upload.html']);
const server=createServer(async(request,response)=>{
  const file=new URL(request.url,'http://localhost').pathname.slice(1);
  if(!allowed.has(file)){ response.writeHead(404); response.end(); return; }
  response.writeHead(200,{ 'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store' }); response.end(await readFile(resolve(directory,file)));
});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
const base=`http://127.0.0.1:${server.address().port}`; let browser; const report=[];
try{
  browser=await chromium.launch({ headless:true }); const page=await browser.newPage();
  await page.route('**/*',route=>route.request().url().startsWith(base+'/')?route.continue():route.abort());
  for(const width of [1440,768,390,320]) for(const view of ['library','upload']){
    await page.setViewportSize({ width,height:1000 }); await page.goto(`${base}/${view}.html`);
    const metrics=await page.evaluate(()=>({ width:innerWidth,scrollWidth:document.documentElement.scrollWidth,smallButtons:[...document.querySelectorAll('button')].filter(b=>b.getBoundingClientRect().height<43.5).map(b=>b.textContent),unlabeledInputs:[...document.querySelectorAll('input,select')].filter(i=>!i.labels?.length&&!i.getAttribute('aria-label')).length }));
    if(metrics.scrollWidth>width||metrics.smallButtons.length||metrics.unlabeledInputs) throw new Error(JSON.stringify(metrics));
    await page.keyboard.press('Tab'); const focus=await page.evaluate(()=>({ style:getComputedStyle(document.activeElement).outlineStyle,width:getComputedStyle(document.activeElement).outlineWidth }));
    if(focus.style==='none'||parseFloat(focus.width)<2) throw new Error('Invisible keyboard focus');
    await page.screenshot({ path:resolve(directory,`${view}-${width}.png`),fullPage:true }); report.push({ view,...metrics,focus });
  }
  await writeFile(resolve(directory,'browser-report.json'),JSON.stringify({ results:report,externalRequests:'blocked',scope:'Rendered component markup; interaction tests run in Jest.' },null,2));
  console.log(JSON.stringify(report));
}finally{ await browser?.close(); await new Promise(done=>server.close(done)); }
