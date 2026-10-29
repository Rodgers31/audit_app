/** Offline, loopback-only preview of actual components. No product auth bypass. */
import {mkdir, writeFile, symlink, readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {spawn} from 'node:child_process';
const source=resolve('.'),root='/evidence/browser-app',port=33549;
await mkdir(root,{recursive:true});
await symlink(resolve('node_modules'),resolve(root,'node_modules')).catch(e=>{if(e.code!=='EEXIST')throw e;});
await writeFile(resolve(root,'package.json'),'{"private":true}');
await writeFile(resolve(root,'tsconfig.json'),JSON.stringify({compilerOptions:{strict:true,jsx:'preserve',target:'es2017',module:'esnext',moduleResolution:'bundler',esModuleInterop:true,baseUrl:source,paths:{'@/*':['./*']}}}));
const auth=resolve('tests/socialRuntimeAuth.ts');
await writeFile(resolve(root,'next.config.js'),`module.exports={experimental:{externalDir:true,cpus:1},webpack(c,{webpack:w}){c.plugins.push(new w.NormalModuleReplacementPlugin(/(?:lib\\/auth\\/AuthProvider|lib\\/supabase\\/client)$/,${JSON.stringify(auth)}));c.resolve.alias['@/lib/auth/AuthProvider']=${JSON.stringify(auth)};c.resolve.alias['@/lib/supabase/client']=${JSON.stringify(auth)};return c;}};`);
await mkdir(resolve(root,'app'),{recursive:true});
await writeFile(resolve(root,'app/globals.css'),(await readFile(resolve('app/globals.css'),'utf8')).split('\n').filter(line=>!line.startsWith('@import url(')).join('\n'));
await writeFile(resolve(root,'postcss.config.js'),`module.exports={plugins:{tailwindcss:{config:${JSON.stringify(resolve(root,'tailwind.config.js'))}},autoprefixer:{}}};`);
await writeFile(resolve(root,'tailwind.config.js'),`const base=require(${JSON.stringify(resolve('tailwind.config.js'))});module.exports={...base,content:[${JSON.stringify(resolve('components/**/*.{tsx,ts}'))},${JSON.stringify(resolve('app/admin/**/*.{tsx,ts}'))},${JSON.stringify(resolve('app/status/**/*.{tsx,ts}'))}]};`);
await writeFile(resolve(root,'app/layout.tsx'),`import './globals.css';import Harness from ${JSON.stringify(resolve('browser-fixtures/admin-redesign/Harness'))};export default function Layout({children}:{children:React.ReactNode}){return <html lang='en'><body><Harness>{children}</Harness></body></html>}`);
await mkdir(resolve(root,'app/admin'),{recursive:true});
await writeFile(resolve(root,'app/admin/layout.tsx'),`export {default} from ${JSON.stringify(resolve('app/admin/layout'))};`);
await writeFile(resolve(root,'app/admin/page.tsx'),`export {default} from ${JSON.stringify(resolve('app/admin/page'))};`);
for(const route of ['social','social/new','social/[postId]']){await mkdir(resolve(root,'app/admin',route),{recursive:true});await writeFile(resolve(root,'app/admin',route,'page.tsx'),`export {default} from ${JSON.stringify(resolve('app/admin',route,'page'))};`);}
await mkdir(resolve(root,'app/api/v1/admin/social/[...path]'),{recursive:true});
await writeFile(resolve(root,'app/api/v1/admin/social/[...path]/route.ts'),`export {GET,POST,PATCH} from ${JSON.stringify(resolve('browser-fixtures/admin-redesign/api'))};`);
const server=spawn(process.execPath,[resolve('node_modules/next/dist/bin/next'),'dev',root,'--hostname','0.0.0.0','--port',String(port)],{env:{PATH:process.env.PATH,NEXT_TELEMETRY_DISABLED:'1',NEXT_PUBLIC_API_URL:'http://127.0.0.1:'+port,NODE_ENV:'development'},stdio:'inherit'});
process.on('SIGTERM',()=>server.kill('SIGTERM'));process.on('SIGINT',()=>server.kill('SIGTERM'));
