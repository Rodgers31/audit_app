import { mkdir, readFile, writeFile, symlink, copyFile } from 'node:fs/promises';
import { resolve, dirname, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, '../..');
const [output, variant] = process.argv.slice(2);
if (variant !== undefined && variant !== 'frozen') throw new Error('Only the declared frozen baseline is supported');
const frozen = '924f1a4f27e1952f97d2291d8878d88603132237';
if (!output || !isAbsolute(output)) throw new Error('Fresh absolute fixture directory required');
await mkdir(output);
for (const directory of ['app/admin/etl', 'fixture']) await mkdir(resolve(output, directory), { recursive: true });
await symlink(resolve(source, 'node_modules'), resolve(output, 'node_modules'));
for (const name of ['Harness.tsx', 'auth.tsx', 'api.ts']) await copyFile(resolve(here, name), resolve(output, 'fixture', name));
await writeFile(resolve(output, 'fixture/supabase.ts'), 'export const createClient=()=>({auth:{onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}})}});');
await writeFile(resolve(output, 'package.json'), '{"private":true}');
await writeFile(resolve(output, 'tsconfig.json'), JSON.stringify({ compilerOptions: {
  jsx: 'preserve', target: 'es2017', module: 'esnext', moduleResolution: 'bundler', esModuleInterop: true,
  baseUrl: source, paths: { '@/*': ['./*'] },
} }));
const replacements = [
  ['lib/auth/AuthProvider', 'auth.tsx'], ['lib/api/axios', 'api.ts'], ['lib/supabase/client', 'supabase.ts'],
].map(([suffix, file]) => `new w.NormalModuleReplacementPlugin(/[/]${suffix.replaceAll('/', '[/]')}(?:[.]tsx?)?$/,${JSON.stringify(resolve(output, 'fixture', file))})`).join(',');
await writeFile(resolve(output, 'next.config.js'), `module.exports={experimental:{externalDir:true,cpus:2,optimizePackageImports:['lucide-react','framer-motion']},webpack(c,{webpack:w}){c.plugins.push(${replacements});return c}};`);
await writeFile(resolve(output, 'postcss.config.js'), `module.exports={plugins:{tailwindcss:{config:${JSON.stringify(resolve(output, 'tailwind.config.js'))}},autoprefixer:{}}};`);
await writeFile(resolve(output, 'tailwind.config.js'), `const c=require(${JSON.stringify(resolve(source, 'tailwind.config.js'))});module.exports={...c,content:[${JSON.stringify(source + '/app/admin/**/*.tsx')},${JSON.stringify(source + '/components/layout/PageShell.tsx')},${JSON.stringify(source + '/lib/auth/admin.tsx')}]};`);
await writeFile(resolve(output, 'app/layout.tsx'), `import ${JSON.stringify(resolve(source, 'app/globals.css'))};import Harness from '../fixture/Harness';export default function Root({children}:any){return <html lang="en"><body><Harness>{children}</Harness></body></html>}`);
await writeFile(resolve(output, 'app/admin/layout.tsx'), `export {default} from ${JSON.stringify(resolve(source, 'app/admin/layout'))};`);
const selectedPages = {};
for (const path of ['app/admin/page.tsx', 'app/admin/etl/page.tsx']) {
  const bytes = variant === 'frozen'
    ? execFileSync('git', ['show', `${frozen}:frontend/${path}`], { cwd: source })
    : await readFile(resolve(source, path));
  selectedPages[path] = bytes;
  // Only this relative dependency changes location when transplanting the
  // actual page module. Its implementation is shared unchanged by both arms.
  const content = bytes.toString().replace("from './DispatchPanel'", `from ${JSON.stringify(resolve(source, 'app/admin/etl/DispatchPanel'))}`);
  await writeFile(resolve(output, path), content);
}
await writeFile(resolve(output, 'app/page.tsx'), 'export default function Home(){return <p>Inert access refusal destination</p>}');
const paths = ['app/admin/page.tsx', 'app/admin/etl/page.tsx', 'app/admin/layout.tsx', 'components/layout/PageShell.tsx', 'lib/auth/admin.tsx', 'app/globals.css'];
const hashes = {};
for (const path of paths) hashes[path] = createHash('sha256').update(selectedPages[path] ?? await readFile(resolve(source, path))).digest('hex');
const fixtureHashes = {};
for (const name of ['prepare.mjs', 'Harness.tsx', 'auth.tsx', 'api.ts']) fixtureHashes[name] = createHash('sha256').update(await readFile(resolve(here, name))).digest('hex');
await writeFile(resolve(output, 'fixture-source.json'), JSON.stringify({ source, variant: variant ?? 'working-tree', frozenBase: frozen,
  runtime: { node: process.version, next: JSON.parse(await readFile(resolve(source, 'node_modules/next/package.json'))).version },
  files: hashes, producer: fixtureHashes,
  scope: 'Actual route/guard/layout/motion; inert auth/API; production build; local paint diagnostics only',
}, null, 2));
console.log(JSON.stringify({ output, source }));
