'use strict';
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');const {createHash}=require('node:crypto');
const frontend=path.resolve(process.argv[2]);const manifest=require(path.join(frontend,'scripts/tooling-repairs.json'));
const {applyRepairs,planRepairs}=require(path.join(frontend,'scripts/apply-tooling-repairs.cjs'));
const hash=x=>createHash('sha256').update(x).digest('hex');const measured=[];
function fixture(){const root=fs.mkdtempSync(path.join(__dirname,'runs/deepmerge-install-'));fs.copyFileSync(path.join(frontend,'package-lock.json'),path.join(root,'package-lock.json'));fs.mkdirSync(path.join(root,'node_modules'));for(const p of manifest.packages)for(const entry of p.entries){fs.mkdirSync(path.dirname(path.join(root,entry)),{recursive:true});fs.cpSync(path.join(frontend,entry),path.join(root,entry),{recursive:true});}
 for(const p of manifest.patches){const packageRecord=manifest.packages.find(x=>x.name===p.package);for(const entry of packageRecord.entries){const file=path.join(root,entry,p.file);if(p.original_sha256===null){fs.unlinkSync(file);continue;}let source=fs.readFileSync(file,'utf8');for(const edit of [...p.edits].reverse()){assert.equal(source.split(edit.after).length,2);source=source.replace(edit.after,edit.before);}assert.equal(hash(source),p.original_sha256,'baseline reconstruction did not match reviewed upstream hash');fs.writeFileSync(file,source);}}
 return root;}
function files(root){const result={};function walk(dir){for(const x of fs.readdirSync(dir)){if(x==='.tooling-repair-lock')continue;const file=path.join(dir,x),st=fs.lstatSync(file);if(st.isSymbolicLink())result[path.relative(root,file)]='symlink:'+fs.readlinkSync(file);else if(st.isDirectory())walk(file);else result[path.relative(root,file)]=hash(fs.readFileSync(file));}}walk(root);return result;}
function withFixture(fn){const root=fixture();try{return fn(root);}finally{fs.rmSync(root,{recursive:true,force:true});}}
function variants(root){const p=path.join(root,'node_modules/deepmerge');const cjs=require(path.join(p,'dist/cjs.js'));const umd=require(path.join(p,'dist/umd.js'));const browser={};vm.runInNewContext(fs.readFileSync(path.join(p,'dist/umd.js'),'utf8'),browser);return[['cjs',cjs],['umd-cjs',umd],['umd-browser',browser.deepmerge]];}
let securityCases=0;
withFixture(root=>{
 const baselines=variants(root);for(const[name,merge]of baselines){const result=merge(Object.create(null),JSON.parse('{"__proto__":{"reviewInjected":true},"safe":7}'));assert.equal(Object.getPrototypeOf(result).reviewInjected,true,'baseline exploit must be alive');measured.push({name:'baseline-'+name,prototypeInjected:true});}
 assert.throws(()=>planRepairs(root,{check:true}),/unpatched/);
 const before=files(root),first=applyRepairs(root);assert.equal(first.changedFiles,10);assert.equal(first.packages.length,3);assert.equal(first.absentPackages.length,0);assert.equal(applyRepairs(root).changedFiles,0);assert.equal(planRepairs(root,{check:true}).operations.length,0);
 const after=files(root);assert.equal(Object.keys(after).filter(file=>before[file]!==after[file]).length,10);assert.equal(fs.existsSync(path.join(root,'node_modules/.tooling-repair-lock')),false);
 for(const file of ['dist/cjs.js','dist/umd.js'])delete require.cache[require.resolve(path.join(root,'node_modules/deepmerge',file))];
 for(const[name,merge]of variants(root)){
  for(const seed of [Object.create(null),{},JSON.parse('{"__proto__":{"old":true}}'),{nested:undefined},{nested:null},{nested:false}]){
   const result=merge(seed,JSON.parse('{"__proto__":{"reviewInjected":true},"safe":7,"nested":{"__proto__":{"reviewInjected":true},"ok":9}}'));
   for(const object of [result,result.nested]){assert.equal(object.reviewInjected,undefined);assert.equal(Object.hasOwn(object,'__proto__'),false);assert.equal(Object.hasOwn(Object.getPrototypeOf(object),'reviewInjected'),false);}assert.equal(result.safe,7);assert.equal(result.nested.ok,9);securityCases++;
  }
  const target=Object.create(null),source=Object.create(null);Object.defineProperty(target,'__proto__',{enumerable:true,get(){throw Error('target getter executed');}});Object.defineProperty(source,'__proto__',{enumerable:true,get(){throw Error('source getter executed');}});assert.equal(merge(target,source).reviewInjected,undefined);securityCases++;
  const symbol=Symbol('__proto__');const result=merge({[symbol]:{a:1},constructor:{a:1},prototype:{a:1}},{[symbol]:{b:2},constructor:{b:2},prototype:{b:2}});assert.equal(result[symbol].a,1);assert.equal(result[symbol].b,2);assert.equal(result.constructor.a,1);assert.equal(result.constructor.b,2);assert.equal(result.prototype.a,1);assert.equal(result.prototype.b,2);assert.equal(({}).reviewInjected,undefined);securityCases++;
  measured.push({name:'repaired-'+name,securityCases:8});
 }
 measured.push({name:'cold-and-repeat',changed:first.changedFiles,repeatChanged:0,actualByteChanges:10});
});
const mutations=[
 ['unknown-deepmerge-cjs',root=>fs.appendFileSync(path.join(root,'node_modules/deepmerge/dist/cjs.js'),'\n// unknown'),/upstream bytes changed/],
 ['missing-deepmerge-umd',root=>fs.unlinkSync(path.join(root,'node_modules/deepmerge/dist/umd.js')),/absent path/],
 ['unexpected-deepmerge-file',root=>fs.writeFileSync(path.join(root,'node_modules/deepmerge/unexpected.js'),'throw 7;'),/unexpected package file/],
 ['changed-deepmerge-main',root=>{const p=path.join(root,'node_modules/deepmerge/package.json');const d=JSON.parse(fs.readFileSync(p));d.main='index.js';fs.writeFileSync(p,JSON.stringify(d));},/upstream bytes changed/],
 ['wrong-installed-deepmerge-version',root=>{const p=path.join(root,'node_modules/deepmerge/package.json');const d=JSON.parse(fs.readFileSync(p));d.version='4.3.2';fs.writeFileSync(p,JSON.stringify(d));},/incompatible installed/],
 ['source-symlink',root=>{const p=path.join(root,'node_modules/deepmerge/dist/cjs.js');fs.renameSync(p,p+'.owned');fs.symlinkSync(p+'.owned',p);},/symlink refused/],
 ['new-nested-deepmerge',root=>{const p=path.join(root,'package-lock.json');const d=JSON.parse(fs.readFileSync(p));d.packages['node_modules/extra/node_modules/deepmerge']={version:'4.3.1',dev:true};fs.writeFileSync(p,JSON.stringify(d));},/unexpected locked locations/],
 ['deepmerge-not-dev',root=>{const p=path.join(root,'package-lock.json');const d=JSON.parse(fs.readFileSync(p));d.packages['node_modules/deepmerge'].dev=false;fs.writeFileSync(p,JSON.stringify(d));},/incompatible locked/],
 ['missing-deepmerge',root=>fs.rmSync(path.join(root,'node_modules/deepmerge'),{recursive:true}),/absent installed/],
 ['invalid-late-umd',root=>fs.writeFileSync(path.join(root,'node_modules/deepmerge/dist/umd.js'),'{}'),/upstream bytes changed/]
];
for(const[name,mutate,diagnostic]of mutations)withFixture(root=>{mutate(root);const before=files(root);assert.throws(()=>applyRepairs(root),diagnostic);assert.deepEqual(files(root),before,'late validation must not publish earlier repairs');assert.equal(fs.existsSync(path.join(root,'node_modules/.tooling-repair-lock')),false);measured.push({name,rejected:true,allFixtureBytesUnchanged:true});});
withFixture(root=>{
 for(const production of ['false',1,0,null,NaN,Infinity]){const before=files(root);assert.throws(()=>applyRepairs(root,{production}),/boolean modes/);assert.deepEqual(files(root),before);}
 measured.push({name:'direct-production-types',rejectedCases:6});
 fs.rmSync(path.join(root,'node_modules/deepmerge'),{recursive:true});const result=applyRepairs(root,{production:true});assert.deepEqual(result.absentPackages,['node_modules/deepmerge']);assert.equal(result.changedFiles,7);assert.equal(result.packages.length,2);assert.throws(()=>applyRepairs(root,{check:true}),/absent installed/);measured.push({name:'omit-dev-explicit-coverage',...result});
});
assert.equal(securityCases,24);assert.equal(measured.length,19);console.log(JSON.stringify({securityCases,measurements:measured}));
