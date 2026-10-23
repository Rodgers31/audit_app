// Small, credential-free Next fixture for the real PageShell and stylesheet.
import { mkdir, readFile, writeFile, symlink } from 'node:fs/promises';
import { dirname, isAbsolute, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const [destination, selectedSource] = process.argv.slice(2);
if (!destination || !isAbsolute(destination)) throw new Error('Fresh absolute fixture directory required');
const source = resolve(selectedSource ?? dirname(fileURLToPath(import.meta.url)), ...(selectedSource ? [] : ['../..']));
const output = resolve(destination);
await mkdir(output); // Refuse an existing destination, including links.
await mkdir(resolve(output, 'app/[[...slug]]'), { recursive: true });
await symlink(resolve(source, 'node_modules'), resolve(output, 'node_modules'));
await writeFile(resolve(output, 'package.json'), JSON.stringify({ private: true }));
await writeFile(resolve(output, 'tsconfig.json'), JSON.stringify({ compilerOptions: {
  jsx: 'preserve', target: 'es2017', module: 'esnext', moduleResolution: 'bundler', esModuleInterop: true,
  baseUrl: source, paths: { '@/*': ['./*'] },
} }));
await writeFile(resolve(output, 'next.config.js'), 'module.exports={experimental:{externalDir:true,cpus:2}};');
await writeFile(resolve(output, 'postcss.config.js'), `module.exports={plugins:{tailwindcss:{config:${JSON.stringify(resolve(output, 'tailwind.config.js'))}},autoprefixer:{}}};`);
await writeFile(resolve(output, 'tailwind.config.js'), `const c=require(${JSON.stringify(resolve(source, 'tailwind.config.js'))});module.exports={...c,content:[${JSON.stringify(resolve(source, 'components/layout/PageShell.tsx'))},${JSON.stringify(output + '/app/**/*.tsx')}]};`);
await writeFile(resolve(output, 'app/layout.tsx'), `import ${JSON.stringify(resolve(source, 'app/globals.css'))};export default function Root({children}:any){return <html lang="en"><head><style>{'.ledger-enter{animation-play-state:paused!important;animation-delay:0s!important}'}</style></head><body suppressHydrationWarning><p>INERT COMPONENT FIXTURE · animations held at their first frame</p>{children}</body></html>}`);
await writeFile(resolve(output, 'app/[[...slug]]/page.tsx'), `import PageShell from ${JSON.stringify(resolve(source, 'components/layout/PageShell'))};export default function Fixture(){return <PageShell title="Critical admin heading" subtitle="No authentication, API, provider or storage connection."><p>Critical working content</p><label>Search fixture<input placeholder="Fixture input"/></label></PageShell>}`);
const files = ['components/layout/PageShell.tsx', 'app/globals.css', 'tailwind.config.js'];
const hashes = {};
for (const file of files) hashes[file] = createHash('sha256').update(await readFile(resolve(source, file))).digest('hex');
await writeFile(resolve(output, 'fixture-source.json'), JSON.stringify({
  scope: 'component-only; animation timeline deliberately frozen; no field-performance verdict',
  generator_sha256: createHash('sha256').update(await readFile(fileURLToPath(import.meta.url))).digest('hex'),
  source, files: hashes,
}, null, 2));
console.log(JSON.stringify({ output, source }));
