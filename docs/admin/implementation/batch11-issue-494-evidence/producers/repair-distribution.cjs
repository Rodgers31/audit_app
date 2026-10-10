'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const [frontend,out]=process.argv.slice(2).map(p=>path.resolve(p));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const manifestPath=path.join(frontend,'scripts/tooling-repairs.json'), bytes=fs.readFileSync(manifestPath),manifest=JSON.parse(bytes);
fs.writeFileSync(path.join(out,'pre-distribution-tooling-repairs.json'),bytes,{flag:'wx'});
const terserPath=require.resolve(path.join(frontend,'node_modules/next/dist/compiled/terser'));
const source=fs.readFileSync(path.join(frontend,'node_modules/sprintf-js/src/sprintf.js'),'utf8');
assert.equal(sha(source),manifest.patches.find(p=>p.package==='sprintf-js').repaired_sha256);
const result=require(terserPath).minify_sync({'../src/sprintf.js':source},{sourceMap:{filename:'sprintf.min.js',url:'sprintf.min.map',includeSources:true},format:{comments:/sprintf-js/}});
assert.equal(result.error,undefined);
for(const file of ['dist/sprintf.min.js','dist/sprintf.min.map','dist/sprintf.min.js.map']){
 const before=fs.readFileSync(path.join(out,'canonical-upstream/sprintf-js',file),'utf8');
 const after=(file.endsWith('.js')?result.code:result.map)+'\n';
 const patch={package:'sprintf-js',version:'1.0.3',file,original_sha256:sha(before),repaired_sha256:sha(after),edits:[{before,after}],addition:null};
 manifest.patches.push(patch);manifest.packages.find(p=>p.name==='sprintf-js').files[file]={original_sha256:patch.original_sha256,repaired_sha256:patch.repaired_sha256};
}
fs.writeFileSync(manifestPath,JSON.stringify(manifest,null,2)+'\n');
fs.writeFileSync(path.join(out,'distribution-generation.json'),JSON.stringify({producer_sha256:sha(fs.readFileSync(__filename)),input_manifest_sha256:sha(bytes),source_sha256:sha(source),terser_path:terserPath,terser_sha256:sha(fs.readFileSync(terserPath)),runtime:{node:process.version,platform:process.platform,arch:process.arch},output_manifest_sha256:sha(fs.readFileSync(manifestPath)),patches:manifest.patches.length},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({patches:manifest.patches.length}));
