'use strict';
// Direct RED/GREEN for a coherent hostile manifest+lock exclusion. All copies are owned.
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const Module=require('node:module');const {createHash}=require('node:crypto');
const frontend=path.resolve(process.argv[2]);const sourceFile=path.join(frontend,'scripts/apply-tooling-repairs.cjs');const source=fs.readFileSync(sourceFile,'utf8');const manifest=require(path.join(frontend,'scripts/tooling-repairs.json'));const {applyRepairs}=require(sourceFile);const hash=x=>createHash('sha256').update(x).digest('hex');
const root=fs.mkdtempSync(path.join(__dirname,'runs/exemption-'));
function compile(name,bytes,data){const dir=path.join(root,name);fs.mkdirSync(dir);fs.writeFileSync(path.join(dir,'tooling-repairs.json'),JSON.stringify(data));const file=path.join(dir,'apply-tooling-repairs.cjs');fs.writeFileSync(file,bytes);const loaded=require(file);return{loaded,file,sha256:hash(fs.readFileSync(file))};}
try{
 fs.copyFileSync(path.join(frontend,'package-lock.json'),path.join(root,'package-lock.json'));fs.mkdirSync(path.join(root,'node_modules'));
 for(const p of manifest.packages)for(const entry of p.entries){fs.mkdirSync(path.dirname(path.join(root,entry)),{recursive:true});fs.cpSync(path.join(frontend,entry),path.join(root,entry),{recursive:true});}
 assert.equal(applyRepairs(root,{check:true}).changedFiles,0);
 const entry='node_modules/@jest/core/node_modules/jest-config/node_modules/deepmerge';const nested=path.join(root,entry);fs.mkdirSync(path.dirname(nested),{recursive:true});fs.cpSync(path.join(root,'node_modules/deepmerge'),nested,{recursive:true});
 for(const p of manifest.patches.filter(p=>p.package==='deepmerge')){const file=path.join(nested,p.file);let text=fs.readFileSync(file,'utf8');for(const edit of [...p.edits].reverse())text=text.replace(edit.after,edit.before);assert.equal(hash(text),p.original_sha256);fs.writeFileSync(file,text);}
 const lockFile=path.join(root,'package-lock.json');const lock=JSON.parse(fs.readFileSync(lockFile));lock.packages[entry]={version:'4.3.1',dev:true};fs.writeFileSync(lockFile,JSON.stringify(lock));
 const metadata=path.join(path.dirname(nested),'package.json');fs.writeFileSync(metadata,JSON.stringify({name:'jest-config',version:'30.5.2',main:'index.js'}));
 const merge=Module.createRequire(metadata)('deepmerge');assert.equal(merge(Object.create(null),JSON.parse('{"__proto__":{"reviewUnpatched":true}}')).reviewUnpatched,true);
 const hostile=structuredClone(manifest);hostile.packages.find(p=>p.name==='deepmerge').otherEntries={[entry]:'4.3.1'};
 const before=source.indexOf('    // Only this exact, separately reviewed YAML4 CLI may remain outside repairs.');const after=source.indexOf('    for (const [entry, version] of Object.entries(otherEntries))',before);assert.ok(before>0&&after>before);
 const oldSource=source.slice(0,before)+"    // Prior generic exclusion reconstructed only for this RED control.\n    const otherEntries = inventory.otherEntries || {};\n    assert.ok(typeof otherEntries === 'object' && !Array.isArray(otherEntries), 'tooling repair: invalid excluded locations');\n"+source.slice(after);
 const old=compile('old-generic-exclusion',oldSource,hostile);const bad=old.loaded.applyRepairs(root,{check:true});assert.equal(bad.changedFiles,0);assert.ok(bad.packages.includes('node_modules/deepmerge'));assert.equal(merge(Object.create(null),JSON.parse('{"__proto__":{"reviewUnpatched":true}}')).reviewUnpatched,true);
 const current=compile('current-exact-exclusion',source,hostile);assert.equal(current.sha256,hash(source));assert.throws(()=>current.loaded.applyRepairs(root,{check:true}),/reviewed YAML4 exception/);
 let rejections=0;for(const name of ['braces','js-yaml','deepmerge'])for(const value of [false,0,'',null,[],{},17,'unexpected']){const mutated=structuredClone(manifest);mutated.packages.find(p=>p.name===name).otherEntries=value;const c=compile('malformed-'+rejections,source,mutated);assert.throws(()=>c.loaded.planRepairs(root,{check:true}),/reviewed YAML4 exception/);rejections++;}
 assert.equal(rejections,24);console.log(JSON.stringify({current_installer_sha256:current.sha256,old_reconstruction_sha256:old.sha256,nested_entry:entry,nested_exploit_alive:true,old_guard_false_success:bad,current_guard_rejected:true,malformed_manifest_rejections:rejections}));
}finally{fs.rmSync(root,{recursive:true,force:true});}
