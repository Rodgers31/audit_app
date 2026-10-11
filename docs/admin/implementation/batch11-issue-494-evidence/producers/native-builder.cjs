'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const crypto = require('node:crypto'), { spawnSync } = require('node:child_process');
const [root, output, cache] = process.argv.slice(2).map(p => path.resolve(p));
const frontend = path.join(root, 'frontend'), archived = path.join(root, 'docs/admin/implementation/batch10-dependencies-evidence');
const sha = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
assert.ok(!fs.existsSync(output), 'fresh output required');
assert.ok(!output.startsWith(root + path.sep) && !root.startsWith(output + path.sep), 'external output required');
fs.mkdirSync(output);
const fixture = path.join(output, 'builder'), data = path.join(fixture, 'public/data/constitution');
fs.mkdirSync(data, { recursive: true }); fs.mkdirSync(path.join(fixture, 'scripts'));
const originals = {};
for (const name of fs.readdirSync(path.join(frontend, 'public/data/constitution')).filter(n => /^chapter-\d+\.json$/.test(n))) {
 const source = path.join(frontend, 'public/data/constitution', name);
 fs.copyFileSync(source, path.join(data, name)); originals['public/data/constitution/'+name] = sha(source);
}
for (const name of ['package.json', 'scripts/build-embeddings.mjs']) {
 fs.copyFileSync(path.join(frontend, name), path.join(fixture, name)); originals[name] = sha(path.join(frontend, name));
}
fs.symlinkSync(path.join(frontend, 'node_modules'), path.join(fixture, 'node_modules'));
const revision = '751bff37182d3f1213fa05d7196b954e230abad9';
const models = path.join(output, 'models'), modelFiles = {};
for (const name of ['config.json','tokenizer.json','tokenizer_config.json','onnx/model_quantized.onnx']) {
 const source = path.join(cache, 'Xenova/all-MiniLM-L6-v2', revision, name), target = path.join(models, 'Xenova/all-MiniLM-L6-v2', name);
 assert.ok(fs.lstatSync(source).isFile()); fs.mkdirSync(path.dirname(target), { recursive: true }); fs.copyFileSync(source, target); modelFiles[name] = sha(source);
}
const env = { ...process.env, BATCH10_BUILDER_ROOT:fixture, BATCH10_BUILDER_MODELS:models, NATIVE_VERIFY_CACHE_DIR:cache };
console.log(JSON.stringify({check:'current-native-builder-inputs',runtime:{node:process.version,platform:process.platform,arch:process.arch},revision,originals,modelFiles,outputsInitiallyAbsent:!fs.existsSync(path.join(data,'embeddings.bin')),producer_sha256:sha(__filename),preloader_sha256:sha(path.join(archived,'builder-init.mjs')),native_control_sha256:sha(path.join(archived,'native-controls.mjs')),environment:env}));
function run(args,cwd) {
 const result = spawnSync(process.execPath,args,{cwd,env,encoding:'utf8',timeout:180000,maxBuffer:8*1024*1024});
 process.stdout.write(result.stdout || ''); process.stderr.write(result.stderr || '');
 assert.equal(result.error,undefined);assert.equal(result.signal,null);assert.equal(result.status,0);
}
run([path.join(archived,'native-controls.mjs'),frontend],frontend);
run(['--import',path.join(archived,'builder-init.mjs'),path.join(fixture,'scripts/build-embeddings.mjs')],fixture);
const index = JSON.parse(fs.readFileSync(path.join(data,'embeddings-index.json'))), bytes = fs.readFileSync(path.join(data,'embeddings.bin'));
const expected = [];
for (const name of fs.readdirSync(data).filter(n=>/^chapter-\d+\.json$/.test(n)).sort((a,b)=>Number(a.match(/\d+/)[0])-Number(b.match(/\d+/)[0]))) {
 const ch=JSON.parse(fs.readFileSync(path.join(data,name)));for(const a of ch.articles)expected.push({ch:ch.number,art:a.number,title:a.title});
}
assert.equal(index.model,'Xenova/all-MiniLM-L6-v2');assert.equal(index.dim,384);assert.equal(index.count,264);assert.deepEqual(index.articles,expected);assert.equal(bytes.length,264*384*4);
const vectors = new Float32Array(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));let maximumNormError=0;
assert.ok(vectors.every(Number.isFinite));
for(let i=0;i<264;i++){const vector=vectors.subarray(i*384,(i+1)*384);const error=Math.abs(Math.sqrt(vector.reduce((s,n)=>s+n*n,0))-1);assert.ok(error<0.0001);maximumNormError=Math.max(maximumNormError,error);}
for(const [name,digest] of Object.entries(originals))assert.equal(sha(path.join(frontend,name)),digest);
const record = {check:'actual-unchanged-embedding-builder',revision,count:264,dim:384,bytes:bytes.length,finite:true,exactArticleIdentity:true,maximumNormError,outputs:{'embeddings.bin':sha(path.join(data,'embeddings.bin')),'embeddings-index.json':sha(path.join(data,'embeddings-index.json'))},sourceUnchanged:true,originals,modelFiles};
fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(record,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(record));
