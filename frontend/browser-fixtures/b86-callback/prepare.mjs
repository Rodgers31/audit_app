/** Generate a loopback-only fixture. Start Chrome only via the shared CUA lock. */
import {mkdir,writeFile,symlink,readFile,lstat,realpath} from 'node:fs/promises';
import {resolve,isAbsolute,dirname,sep} from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const output=process.argv[2],source=resolve('.'),root=process.env.B86_CALLBACK_EVIDENCE_ROOT;
const runtime=process.env.B86_CALLBACK_RUNTIME_IMAGE||'b86-callback-runtime:local';
if(!root||!output||!isAbsolute(root)||!isAbsolute(output)||resolve(root)!==root||resolve(output)!==output
  ||!output.startsWith(root+sep)||output.split(sep).includes('.git')||typeof process.getuid!=='function'
  ||!/^\w[\w./:-]*$/.test(runtime))throw Error('Explicit owned absolute evidence root and fresh output required');
for(const directory of new Set([root,dirname(output)])){
  const info=await lstat(directory);
  if(!info.isDirectory()||info.isSymbolicLink()||info.uid!==process.getuid()||await realpath(directory)!==directory)
    throw Error('Owned unsymlinked evidence directory required');
}
const checkouts=execFileSync('git',['worktree','list','--porcelain','-z'],{encoding:'utf8'}).split('\0').filter(row=>row.startsWith('worktree ')).map(row=>row.slice(9));
const git=execFileSync('git',['rev-parse','--path-format=absolute','--git-common-dir'],{encoding:'utf8'}).trim();
if([...checkouts,git].some(path=>output===path||output.startsWith(path+sep)))throw Error('Evidence must be outside Git metadata and every checkout');
await mkdir(output,{mode:0o700});
await mkdir(resolve(output,'app/api/v1/social/oauth/meta/callback'),{recursive:true});
await symlink(resolve(source,'node_modules'),resolve(output,'node_modules'));
await writeFile(resolve(output,'package.json'),'{"private":true}');
await writeFile(resolve(output,'tsconfig.json'),JSON.stringify({compilerOptions:{jsx:'preserve',target:'es2017',module:'esnext',moduleResolution:'bundler',esModuleInterop:true,baseUrl:source,paths:{'@/*':['./*']}}}));
const mock=resolve(source,'browser-fixtures/b86-callback/mocks.ts');
await writeFile(resolve(output,'next.config.js'),`module.exports={experimental:{externalDir:true,cpus:1},webpack(c,{webpack:w}){c.plugins.push(new w.NormalModuleReplacementPlugin(/(?:lib[/]auth[/]AuthProvider|lib[/]hooks[/]useSocial|lib[/]hooks[/]useSocialConnections)$/,${JSON.stringify(mock)}));return c;}};`);
await writeFile(resolve(output,'app/layout.tsx'),'export default function Layout({children}:any){return <html lang="en"><body>{children}</body></html>}');
await writeFile(resolve(output,'app/page.tsx'),`export {default} from ${JSON.stringify(resolve(source,'browser-fixtures/b86-callback/Harness'))};`);
// Generate the actual Python callback renderer in an isolated no-network runtime.
// This tests rendering/message/history only; ASGI tests separately cover real
// staging/auth/cookie transport under synthetic HTTPS. No TLS parity is claimed.
const rendered=JSON.parse(execFileSync('docker',['run','--rm','--pull','never','--network','none','--memory','512m','--cpus','.5','-v',resolve(source,'..')+':/work:ro','-w','/work','-e','PYTHONPATH=/work/backend','-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHON_DOTENV_DISABLED=1',runtime,'python','-c',`import json; from social.connections.direct_api import callback_html; r=callback_html('00000000-0000-4000-8000-000000000767','http://127.0.0.1:33667'); print(json.dumps({'body':r.body.decode(),'headers':dict(r.headers)}))`],{encoding:'utf8'}));
await writeFile(resolve(output,'app/api/v1/social/oauth/meta/callback/route.ts'),`import {appendFile} from 'node:fs/promises'; export const dynamic='force-dynamic';export async function GET(req:Request){await appendFile(${JSON.stringify(resolve(output,'synthetic-first-collector.jsonl'))},JSON.stringify({url:req.url,marker:'OWNED-INERT-COLLECTOR-CONTROL'})+'\\n');return new Response(${JSON.stringify(rendered.body)},{headers:${JSON.stringify(rendered.headers)}});}`);
const files=['components/admin/social/connections/MetaAccounts.tsx','components/admin/social/connections/callbackSecurity.ts','lib/api/socialConnections.ts','browser-fixtures/b86-callback/Harness.tsx','browser-fixtures/b86-callback/mocks.ts','browser-fixtures/b86-callback/prepare.mjs'];const hashes={};for(const p of files)hashes[p]=createHash('sha256').update(await readFile(resolve(source,p))).digest('hex');
await writeFile(resolve(output,'fixture-source.json'),JSON.stringify({source,hashes,scope:'Actual Accounts component with inert hooks; actual Python callback HTML and headers; HTTP loopback renderer only, no platform collector/TLS acceptance',runtime:{image:runtime,node:process.version,next:JSON.parse(await readFile(resolve(source,'node_modules/next/package.json'))).version}},null,2));
console.log(JSON.stringify({output,source}));
