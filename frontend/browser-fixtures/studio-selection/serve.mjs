/** Owned local-only Next fixture: real Studio and API clients, inert HTTP data. */
import {mkdir,writeFile,symlink,readFile,cp} from 'node:fs/promises';
import {resolve} from 'node:path';
import {spawn,execFileSync} from 'node:child_process';
const packet=process.env.STUDIO_722_OUTPUT;
if(!packet?.startsWith('/Users/roger/.codex/visualizations/')||packet.includes('..'))throw Error('Owned output required');
const root=resolve(packet,'browser-app'),source=resolve('.');
await mkdir(resolve(root,'app/api/v1/admin/social/[...path]'),{recursive:true});
await symlink(resolve('node_modules'),resolve(root,'node_modules')).catch(e=>{if(e.code!=='EEXIST')throw e;});
await writeFile(resolve(root,'package.json'),'{"private":true}');
await writeFile(resolve(root,'tsconfig.json'),JSON.stringify({compilerOptions:{strict:true,jsx:'preserve',target:'es2017',module:'esnext',moduleResolution:'bundler',esModuleInterop:true,baseUrl:source,paths:{'@/*':['./*']}}}));
await writeFile(resolve(root,'next.config.js'),`module.exports={experimental:{externalDir:true,cpus:1},webpack(c){c.resolve.alias['@/lib/supabase/client']=${JSON.stringify(resolve('tests/socialRuntimeAuth.ts'))};return c;}};`);
await writeFile(resolve(root,'app/layout.tsx'),'export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}');
await writeFile(resolve(root,'app/page.tsx'),`export {default} from ${JSON.stringify(resolve('browser-fixtures/studio-selection/Harness'))};`);
// Pinned baseline route makes the same real Chrome regression reproducible.
await cp(resolve('components/admin/social'),resolve(root,'baseline-social'),{recursive:true});
await writeFile(resolve(root,'baseline-social/SocialStudio.tsx'),execFileSync('git',['show','5189675364648113c92b46b54d8f6a30b1bf00e2:frontend/components/admin/social/SocialStudio.tsx']));
await mkdir(resolve(root,'app/red'),{recursive:true});
const harness=await readFile(resolve('browser-fixtures/studio-selection/Harness.tsx'),'utf8');
await writeFile(resolve(root,'app/red/page.tsx'),harness.replace('@/components/admin/social/SocialStudio',resolve(root,'baseline-social/SocialStudio')));

await writeFile(resolve(root,'app/api/v1/admin/social/[...path]/route.ts'),`
import {post} from ${JSON.stringify(resolve('tests/socialFixtures'))};
import {appendFile} from 'node:fs/promises';
const id=(n:number)=>'00000000-0000-4000-8000-'+String(n).padStart(12,'0'),sha='a'.repeat(64);
const source=post({id:id(21),title:'Older eligible source',version:7});let current=source;
const composition={schema_version:1,template:'new_report',template_version:1,kind:'graphic',revision_id:source.revision_id,title:'Existing older render',facts:['report','publisher','publication_date'].map(id=>({id,text:'Verified report fact',source_url:'https://example.org/report'})),scenes:[{fact_id:'report',seconds:15}]};
const job={id:id(90),revision_id:source.revision_id,state:'ready',version:3,composition,input_hash:sha,runtime_hash:sha,sha256:sha,inspection:{sha256:sha,mime_type:'image/png',byte_size:4,width:720,height:1280,duration_ms:null},approved_sha256:sha,safe_error:null,cancel_requested:false,attempt:1,retry_of_id:null};
const asset=(n:number)=>({id:id(100+n),version:2,filename:'inspected-'+n+'.png',state:'ready',mime_type:'image/png',byte_size:4,sha256:n===21?sha:'b'.repeat(64),width:720,height:1280,duration_ms:null,default_alt_text:'Evidence',safe_error:null,created_at:'2026-10-18T00:00:00Z'});
export async function GET(req:Request){const u=new URL(req.url),path=u.pathname.split('/social')[1],page=Number(u.searchParams.get('page')||1);await appendFile(${JSON.stringify(resolve(packet,'http.jsonl'))},JSON.stringify({method:'GET',path,page})+'\\n');let data;
if(path==='/studio/capabilities')data={rendering_available:false,unavailable_reason:'Fixture rendering off',templates:['new_report'],template_version:1,analytics_collection_available:false,analytics_reason:'Fixture off',uploads_enabled:false};
else if(path==='/studio/jobs')data={jobs:[job],page,has_more:false};
else if(path==='/studio/calendar')data={items:[],page,has_more:false};
else if(path==='/posts')data={posts:page===1?Array.from({length:20},(_,i)=>post({id:id(i+1),title:'Newer source '+(i+1)})):[source],total:21,page,page_size:20,has_more:page===1};
else if(path==='/media/assets')data={assets:page===1?Array.from({length:20},(_,i)=>asset(i+1)):[asset(21)],total:21,page,page_size:20,has_more:page===1};
else if(path==='/posts/'+source.id)data=current;else return Response.json({error:'Unexpected fixture path'},{status:404});
return Response.json(data,{headers:{'Cache-Control':'private, no-store'}});}
export async function POST(req:Request){const path=new URL(req.url).pathname.split('/social')[1],body=await req.json(),key=req.headers.get('idempotency-key');await appendFile(${JSON.stringify(resolve(packet,'http.jsonl'))},JSON.stringify({method:'POST',path,body,key})+'\\n');if(path!='/studio/jobs/'+job.id+'/attach'||body.expected_version!==current.version||current.revision_id!==job.revision_id||body.asset_id!==asset(21).id||!key)return Response.json({code:'FIXTURE_REFUSAL',message:'Exact fixture binding required'},{status:409});current=post({...source,version:8,revision_id:id(88)});return Response.json(current);}
`);
const server=spawn(process.execPath,[resolve('node_modules/next/dist/bin/next'),'dev',root,'--hostname','127.0.0.1','--port','33522'],{env:{PATH:process.env.PATH,NEXT_TELEMETRY_DISABLED:'1',NEXT_PUBLIC_API_URL:'http://127.0.0.1:33522',NODE_ENV:'development'},stdio:'inherit'});
process.on('SIGTERM',()=>server.kill('SIGTERM'));process.on('SIGINT',()=>server.kill('SIGTERM'));
