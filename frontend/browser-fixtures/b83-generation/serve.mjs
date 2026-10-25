/** CUA Chrome fixture server only. No browser/profile/automation is launched. */
import { mkdir, writeFile, symlink, readFile } from 'node:fs/promises';
import { resolve, isAbsolute } from 'node:path';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
const packet = process.env.B83_GENERATION_BROWSER_OUTPUT;
if (!packet || !isAbsolute(packet) || !packet.startsWith('/Users/roger/.codex/visualizations/') || packet.includes('..')) throw Error('Owned absolute output required');
const root=resolve(packet,'browser-app'), source=resolve('.');
await mkdir(resolve(root,'app/api/v1/admin/social/[...path]'),{recursive:true});
await symlink(resolve(source,'node_modules'),resolve(root,'node_modules'));
await writeFile(resolve(root,'package.json'),'{"private":true}');
await writeFile(resolve(root,'tsconfig.json'),JSON.stringify({compilerOptions:{strict:true,jsx:'preserve',target:'es2017',module:'esnext',moduleResolution:'bundler',esModuleInterop:true,baseUrl:source,paths:{'@/*':['./*']}}}));
await writeFile(resolve(root,'next.config.js'),`module.exports={experimental:{externalDir:true,cpus:1},webpack(c,{webpack:w}){c.plugins.push(new w.NormalModuleReplacementPlugin(/(?:lib\\/auth\\/AuthProvider|lib\\/supabase\\/client)$/,${JSON.stringify(resolve(source,'tests/socialRuntimeAuth.ts'))}));c.resolve.alias['@/lib/auth/AuthProvider']=${JSON.stringify(resolve(source,'tests/socialRuntimeAuth.ts'))};c.resolve.alias['@/lib/supabase/client']=${JSON.stringify(resolve(source,'tests/socialRuntimeAuth.ts'))};return c;}};`);
await writeFile(resolve(root,'app/layout.tsx'),'export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}');
await writeFile(resolve(root,'app/page.tsx'),`export {default} from ${JSON.stringify(resolve(source,'browser-fixtures/b83-generation/Harness'))};`);
await writeFile(resolve(root,'app/api/v1/admin/social/[...path]/route.ts'),`
import {appendFile} from 'node:fs/promises';
const caps=[{domain:'counties_budget',financial:true,reports:true,reason:'qualified_cob_adapter'},{domain:'opendata',financial:false,reports:false,reason:'source_extracted_not_publication_qualified'},{domain:'cra',financial:false,reports:false,reason:'recommendation_date_authority_unavailable'},{domain:'county_borrowing',financial:false,reports:false,reason:'report_date_authority_unavailable'}];
const headers={'Cache-Control':'private, no-store'};
export async function GET(req:Request){if(!new URL(req.url).pathname.endsWith('/generation/capabilities'))return Response.json({error:'Unexpected fixture read'},{status:404});return Response.json(caps,{headers});}
export async function POST(req:Request){const body=await req.json(),path=new URL(req.url).pathname;await appendFile(${JSON.stringify(resolve(packet,'http.jsonl'))},JSON.stringify({method:'POST',path,body})+'\\n');if(!path.endsWith('/generation/preview'))return Response.json({error:'Mutations forbidden in inert fixture'},{status:403});if(!Array.isArray(body.record_ids)||body.record_ids.length<1||body.record_ids.length>25)return Response.json({error:'Fixture bound'},{status:422});return Response.json({drafts_enabled:false,results:body.record_ids.map((record_id:number)=>({record_id,status:body.domain==='opendata'||body.domain==='cra'||body.domain==='county_borrowing'?'unsupported_source':record_id===2?'refused':record_id===3?'unchanged':body.backfill||record_id===4?'eligible_change':'baseline',reason:body.domain==='county_borrowing'?'report_date_authority_unavailable':body.domain==='opendata'?'source_extracted_not_publication_qualified':body.domain==='cra'?'recommendation_date_authority_unavailable':record_id===2?'publisher_date_receipt_unavailable':record_id===3?'semantic_evidence_unchanged':body.backfill?'explicit_backfill':record_id===4?'semantic_evidence_changed':'first_observation',source_document_id:body.domain==='counties_budget'&&record_id!==2?10:null}))},{headers});}
`);
const paths=['components/admin/social/GenerationPreview.tsx','components/admin/social/GenerationOutcomes.tsx','lib/api/socialGeneration.ts','lib/admin/ingestion.ts','lib/socialGenerationReasons.ts','browser-fixtures/b83-generation/Harness.tsx','browser-fixtures/b83-generation/serve.mjs'];
const hashes={};for(const p of paths)hashes[p]=createHash('sha256').update(await readFile(resolve(source,p))).digest('hex');
await writeFile(resolve(packet,'fixture-source.json'),JSON.stringify({source,hashes,scope:'Actual production components/decoders; inert auth/HTTP; CUA logged-in Chrome; no production acceptance'},null,2));
const server=spawn(process.execPath,[resolve(source,'node_modules/next/dist/bin/next'),'dev',root,'--hostname','127.0.0.1','--port','33583'],{env:{PATH:process.env.PATH,NEXT_TELEMETRY_DISABLED:'1',NEXT_PUBLIC_API_URL:'http://127.0.0.1:33583',NODE_ENV:'development'},stdio:'inherit'});
process.on('SIGTERM',()=>server.kill('SIGTERM'));process.on('SIGINT',()=>server.kill('SIGTERM'));
