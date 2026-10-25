/** Standalone local fixture project. No browser or product route is created. */
import { mkdir, mkdtemp, symlink, writeFile } from 'node:fs/promises';
import { resolve, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const source = fileURLToPath(new URL('../../', import.meta.url));
const output = process.env.B86_GENERATION_BROWSER_OUTPUT;
const backend = process.env.B86_GENERATION_FIXTURE_API;
const port = Number(process.env.B86_GENERATION_BROWSER_PORT ?? '33586');
if (!output || !isAbsolute(output) || !Number.isInteger(port) || port < 1024 || port > 65535) {
  throw Error('Absolute owned output and bounded local port required');
}
if (!/^http:\/\/127\.0\.0\.1:[0-9]{1,5}$/.test(backend ?? '')) {
  throw Error('Explicit loopback fixture API required');
}
const api = new URL(backend);
if (Number(api.port) < 1024 || Number(api.port) > 65535) throw Error('Bounded local API port required');
await mkdir(output, { recursive: true });
const root = await mkdtemp(resolve(output, 'browser-app-'));
await mkdir(resolve(root, 'app/api/v1/admin/social/[...path]'), { recursive: true });
await symlink(resolve(source, 'node_modules'), resolve(root, 'node_modules'));
await writeFile(resolve(root, 'package.json'), '{"private":true}');
await writeFile(resolve(root, 'tsconfig.json'), JSON.stringify({ compilerOptions: {
  strict: true, jsx: 'preserve', target: 'es2017', module: 'esnext', moduleResolution: 'bundler',
  esModuleInterop: true, baseUrl: source, paths: { '@/*': ['./*'] },
} }));
// Auth aliases exist only in this generated project. The product provider and
// axios continue unchanged; axios receives an inert, sessionless client here.
const inertAuth = resolve(source, 'tests/socialRuntimeAuth.ts');
await writeFile(resolve(root, 'next.config.js'), `module.exports={experimental:{externalDir:true,cpus:1},webpack(c,{webpack:w}){c.plugins.push(new w.NormalModuleReplacementPlugin(/(?:lib\\/auth\\/AuthProvider|lib\\/supabase\\/client)$/,${JSON.stringify(inertAuth)}));c.resolve.alias['@/lib/auth/AuthProvider']=${JSON.stringify(inertAuth)};c.resolve.alias['@/lib/supabase/client']=${JSON.stringify(inertAuth)};return c;}};`);
await writeFile(resolve(root, 'app/layout.tsx'), 'export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}');
await writeFile(resolve(root, 'app/page.tsx'), `export {default} from ${JSON.stringify(resolve(source, 'browser-fixtures/b86-generation/Harness'))};`);
await writeFile(resolve(root, 'app/api/v1/admin/social/[...path]/route.ts'), `
const reads=new Set(['/generation/capabilities','/generation/controls','/automation/rules','/automation/decisions','/accounts']);
const commands=new Set(['/generation/preview','/generation/detect-reports']);
async function forward(req:Request){
  const url=new URL(req.url),prefix='/api/v1/admin/social',path=url.pathname.slice(prefix.length);
  if(!url.pathname.startsWith(prefix+'/')||!(req.method==='GET'?reads.has(path):req.method==='POST'&&commands.has(path)))return new Response('Fixture boundary',{status:403});
  const body=req.method==='POST'?await req.text():undefined;
  if(body&&body.length>10000)return new Response('Fixture byte bound',{status:413});
  const response=await fetch(${JSON.stringify(backend)}+url.pathname+url.search,{method:req.method,headers:{'Content-Type':'application/json',...(req.headers.get('Idempotency-Key')?{'Idempotency-Key':req.headers.get('Idempotency-Key')!}:{})},body,cache:'no-store',redirect:'error',signal:AbortSignal.timeout(25000)});
  return new Response(await response.text(),{status:response.status,headers:{'Content-Type':'application/json','Cache-Control':'private,no-store'}});
}
export const GET=forward;export const POST=forward;
`);
await writeFile(resolve(output, 'fixture-launch.json'), JSON.stringify({ root, source, backend, port, auth: inertAuth }, null, 2));
const server = spawn(process.execPath, [resolve(source, 'node_modules/next/dist/bin/next'), 'dev', root, '--hostname', '127.0.0.1', '--port', String(port)], {
  env: { PATH: process.env.PATH, NEXT_TELEMETRY_DISABLED: '1', NEXT_PUBLIC_API_URL: `http://127.0.0.1:${port}`, NODE_ENV: 'development' },
  stdio: 'inherit',
});
process.on('SIGTERM', () => server.kill('SIGTERM'));
process.on('SIGINT', () => server.kill('SIGTERM'));
server.on('exit', code => { process.exitCode = code ?? 1; });
