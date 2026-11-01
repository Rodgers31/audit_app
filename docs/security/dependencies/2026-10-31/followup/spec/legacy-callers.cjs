'use strict';
// Executable observation of installed legacy callers. Does not modify exports or package files.
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const os=require('node:os');
const Module=require('node:module');const {createRequire}=Module;const {createHash}=require('node:crypto');
const frontend=path.resolve(process.argv[2]);const req=createRequire(path.join(frontend,'package.json'));
const legacy=req('minimatch');const entry=req.resolve('minimatch');assert.equal(req('minimatch/package.json').version,'3.1.5');
const events=[];const originalLoad=Module._load;const wrappers=new Map();
function record(kind,args,parent,result){const pattern=kind==='call'?args[1]:args[0],options=kind==='call'?args[2]:args[1];events.push({kind,parent:path.relative(frontend,parent||''),pattern,options:options||{},rows:result&&Array.isArray(result.set)?result.set.length:undefined});}
function getWrapper(parent){
 if(wrappers.has(parent))return wrappers.get(parent);
 const ctor=new Proxy(legacy.Minimatch,{construct(target,args,newTarget){const result=Reflect.construct(target,args,newTarget);record('constructor',args,parent,result);return result;},apply(target,thisArg,args){const result=Reflect.apply(target,thisArg,args);record('constructor-call',args,parent,result);return result;}});
 const wrapper=new Proxy(legacy,{apply(target,thisArg,args){const result=Reflect.apply(target,thisArg,args);record('call',args,parent,result);return result;},get(target,key,receiver){if(key==='Minimatch')return ctor;if(key==='makeRe')return(...args)=>{const result=legacy.makeRe(...args);record('makeRe',args,parent,result);return result;};return Reflect.get(target,key,receiver);}});
 wrappers.set(parent,wrapper);return wrapper;
}
Module._load=function(request,parent,isMain){const loaded=originalLoad.apply(this,arguments);return request==='minimatch'&&loaded===legacy?getWrapper(parent&&parent.filename):loaded;};
(async()=>{
 const {ESLint}=req('eslint');
 const normal=new ESLint({cwd:frontend,cache:false});const normalResults=await normal.lintFiles(['app/page.*']);assert.equal(normalResults.length,1);assert.equal(normalResults[0].fatalErrorCount,0);
 const custom=new ESLint({cwd:frontend,useEslintrc:false,cache:false,baseConfig:{parserOptions:{ecmaVersion:2022,sourceType:'module'},plugins:['import'],rules:{'import/no-internal-modules':['error',{forbid:['blocked/**']}]}}});
 const blocked=await custom.lintText("import x from './blocked/private/module';\n",{filePath:'review-spec.js'});assert.equal(blocked[0].messages.some(m=>m.ruleId==='import/no-internal-modules'),true);
 const allowed=await custom.lintText("import x from './allowed/private/module';\n",{filePath:'review-spec.js'});assert.equal(allowed[0].messages.some(m=>m.ruleId==='import/no-internal-modules'),false);
 const root=fs.mkdtempSync(path.join(__dirname,'runs/legacy-glob-'));
 let traversal;
 try{
  for(const name of ['a/b/one.txt','a/b/two.js','x/a/b/three.txt']){const file=path.join(root,name);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,'owned');}
  const glob=req('glob');assert.equal(req('glob/package.json').version,'7.2.3');assert.equal(typeof glob,'function');
  const normalMatches=glob.sync('**/*.txt',{cwd:root,nodir:true});assert.deepEqual(normalMatches.sort(),['a/b/one.txt','x/a/b/three.txt']);
  let reads=0;const observed={...fs,readdirSync(...args){reads++;return fs.readdirSync(...args);}};
  const g=new glob.GlobSync(Array(8).fill('**/../a/b').join('/'),{cwd:root,fs:observed,optimizationLevel:2,braceExpandMax:8});
  assert.equal(g.minimatch.set.length,1);assert.ok(reads<=100,'bounded fixture unexpectedly traversed too much');
  traversal={globVersion:req('glob/package.json').version,rows:g.minimatch.set.length,reads,matches:g.found};
 }finally{fs.rmSync(root,{recursive:true,force:true});}
 assert.ok(events.some(e=>e.parent.includes('eslint/lib/cli-engine/file-enumerator')&&e.kind==='constructor'),'actual ESLint enumeration was not observed');
 assert.ok(events.some(e=>e.parent.includes('eslint-plugin-import')&&e.kind==='makeRe'&&e.pattern==='blocked/**'),'actual import rule was not observed');
 assert.ok(events.some(e=>e.parent.includes('glob/common')&&e.kind==='constructor'&&e.options.optimizationLevel===2&&e.rows===1),'actual legacy glob pattern was not observed');
 console.log(JSON.stringify({entry,entry_sha256:createHash('sha256').update(fs.readFileSync(entry)).digest('hex'),linted:normalResults.map(r=>({file:path.relative(frontend,r.filePath),fatal:r.fatalErrorCount,errors:r.errorCount,warnings:r.warningCount})),blockedRuleCount:blocked[0].messages.filter(m=>m.ruleId==='import/no-internal-modules').length,allowedRuleCount:allowed[0].messages.filter(m=>m.ruleId==='import/no-internal-modules').length,traversal,events}));
})().catch(e=>{console.error(e.stack);process.exitCode=1;}).finally(()=>{Module._load=originalLoad;});
