'use strict';
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');const crypto=require('node:crypto');const {createRequire}=require('node:module');
const here=__dirname,root='/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app/frontend';
const patchSet=JSON.parse(fs.readFileSync(path.join(root,'scripts/tooling-repairs.json')));const inventory=patchSet.packages.find(p=>p.name==='deepmerge');
const core=createRequire(path.join(root,'package.json'))('@jest/core');
const app=createRequire(path.join(root,'package.json'));const config=createRequire(createRequire(app.resolve('@jest/core')).resolve('jest-config'));
const installed=path.dirname(config.resolve('deepmerge/package.json'));const nonce='review_injected_d471';
function umd(file,mode){let result;const context=mode==='amd'?{define:factory=>{result=factory();}}:{};if(mode==='amd')context.define.amd={};vm.runInNewContext(fs.readFileSync(file,'utf8'),context,{timeout:1000});return mode==='amd'?result:context.deepmerge;}
const variants=[];
for(const [profile,dir] of [['original',path.join(here,'original/package')],['patched',path.join(here,'patched')]])for(const kind of ['cjs','index','umd-cjs','umd-browser','umd-amd']){
 const file=path.join(dir,kind==='cjs'?'dist/cjs.js':kind==='index'?'index.js':'dist/umd.js');const merge=kind==='umd-browser'?umd(file,'browser'):kind==='umd-amd'?umd(file,'amd'):require(file);variants.push({name:profile+'/'+kind,profile,merge});
}
variants.push({name:'installed/Jest-CJS',profile:'installed',merge:config('deepmerge')},{name:'installed/UMD-CJS',profile:'installed',merge:require(path.join(installed,'dist/umd.js'))},{name:'installed/UMD-browser',profile:'installed',merge:umd(path.join(installed,'dist/umd.js'),'browser')},{name:'installed/UMD-AMD',profile:'installed',merge:umd(path.join(installed,'dist/umd.js'),'amd')});
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
for(const [file,identity] of Object.entries(inventory.files))assert.equal(hash(fs.readFileSync(path.join(installed,file))),identity.repaired_sha256,'installed file hash '+file);
const packageMeta=JSON.parse(fs.readFileSync(path.join(installed,'package.json')));assert.equal(packageMeta.main,'dist/cjs.js');assert.equal(config.resolve('deepmerge'),path.join(installed,packageMeta.main));
function poison(){return JSON.parse('{"__proto__":{"'+nonce+'":true},"safe":17}');}
function clean(result,prototype){assert.equal(result[nonce],undefined);assert.equal(Object.getPrototypeOf(result),prototype);assert.equal(Object.hasOwn(result,'__proto__'),false);assert.equal(({})[nonce],undefined);}
const cases=[
 ['null target/source poison',(m,p)=>{const result=m(Object.create(null),poison());clean(result,p);assert.equal(result.safe,17)}],
 ['target poison',(m,p)=>{const result=m(poison(),{});clean(result,p);assert.equal(result.safe,17)}],
 ['source poisoned getter',(m,p)=>{let reads=0;const s=Object.create(null);Object.defineProperty(s,'__proto__',{enumerable:true,get(){reads++;throw Error('proto getter read')}});s.safe=17;const result=m(Object.create(null),s);clean(result,p);assert.equal(reads,0);assert.equal(result.safe,17)}],
 ['target poisoned getter',(m,p)=>{let reads=0;const t=Object.create(null);Object.defineProperty(t,'__proto__',{enumerable:true,get(){reads++;throw Error('proto getter read')}});t.safe=17;const result=m(t,{});clean(result,p);assert.equal(reads,0);assert.equal(result.safe,17)}],
 ['frozen null source',(m,p)=>{const source=Object.create(null);Object.defineProperty(source,'__proto__',{enumerable:true,value:{[nonce]:true}});source.safe=17;Object.freeze(source);clean(m(Object.create(null),source),p)}],
 ['source Proxy trap',(m,p)=>{let reads=0;const s=new Proxy(poison(),{get(t,k,r){if(k==='__proto__'){reads++;throw Error('proxy proto get')}return Reflect.get(t,k,r)}});clean(m(Object.create(null),s),p);assert.equal(reads,0)}],
 ['target Proxy trap',(m,p)=>{let reads=0;const t=new Proxy(poison(),{get(t,k,r){if(k==='__proto__'){reads++;throw Error('proxy proto get')}return Reflect.get(t,k,r)}});clean(m(t,{}),p);assert.equal(reads,0)}],
 ['custom merge callback',(m,p)=>{let forbidden=0;const t=poison();const result=m(t,poison(),{customMerge(k){if(k==='__proto__'){forbidden++;return()=>({[nonce]:true})}return undefined}});clean(result,p);assert.equal(forbidden,0)}],
 ['all and nested arrays',(m,p)=>{const s={rows:[poison(),{inner:poison()}]};const out=m.all([Object.create(null),s]);clean(out.rows[0],p);clean(out.rows[1].inner,p)}],
 ['custom array cloning helper',(m,p)=>{const out=m({rows:[]},{rows:[poison()]},{arrayMerge(t,s,o){return s.map(v=>o.cloneUnlessOtherwiseSpecified(v,o))}});clean(out.rows[0],p)}],
 ['clone false root protection',(m,p)=>{clean(m(Object.create(null),poison(),{clone:false}),p);clean(m(poison(),{}, {clone:false}),p)}],
 ['JSON escaped key',(m,p)=>{clean(m(Object.create(null),JSON.parse('{"__pr\\u006fto__":{"'+nonce+'":true}}')),p)}],
 ['safe same-name-looking keys',(m,p)=>{const s={'__PROTO__':1,'__proto__\0':2,'prototype':3};const out=m(Object.create(null),s);clean(out,p);for(const k of Object.keys(s))assert.equal(out[k],s[k])}],
 ['symbol and reserved symbol description',(m,p)=>{const symbol=Symbol('__proto__'),s={[symbol]:{safe:2}};const out=m(Object.create(null),s);clean(out,p);assert.equal(out[symbol].safe,2)}],
 ['constructor/prototype retain data semantics',(m,p)=>{const out=m({constructor:{a:1},prototype:{a:2}},{constructor:{b:3},prototype:{b:4}});clean(out,p);assert.equal(out.constructor.a,1);assert.equal(out.constructor.b,3);assert.equal(out.prototype.a,2);assert.equal(out.prototype.b,4);assert.equal(({}).b,undefined)}],
];
for(const value of [null,undefined,false,0,'','text'])cases.push(['nested placeholder '+String(value),(m,p)=>{const out=m({x:value},{x:poison()});clean(out.x,p);assert.equal(out.x.safe,17)}]);
const results=[];
for(const variant of variants){const prototype=Object.getPrototypeOf(variant.merge({},{}));for(const [label,fn] of cases){try{fn(variant.merge,prototype);results.push({variant:variant.name,case:label,pass:true})}catch(e){results.push({variant:variant.name,case:label,pass:false,error:String(e)})}}}
const bad=results.filter(x=>!x.pass&& !x.variant.startsWith('original/'));if(bad.length)console.error(JSON.stringify(bad,null,2));
if(!results.some(x=>!x.pass&&x.variant.startsWith('original/')))throw Error('No original-package red proof');
// These are documented extension boundaries, not prototype creation by mergeObject.
const inherited=Object.create({[nonce]:true});const cloneFalse=config('deepmerge')({}, {kept:inherited},{clone:false});assert.equal(cloneFalse.kept,inherited);assert.equal(cloneFalse.kept[nonce],true);
const custom=config('deepmerge')({kept:{}},{kept:{}},{customMerge:key=>key==='kept'?()=>inherited:undefined});assert.equal(custom.kept,inherited);
const record={observedAt:new Date().toISOString(),sourceHashes:{installer:hash(fs.readFileSync(path.join(root,'scripts/apply-tooling-repairs.cjs'))),patchSet:hash(fs.readFileSync(path.join(root,'scripts/tooling-repairs.json')))},variants:variants.length,casesPerVariant:cases.length,results,failuresInCandidate:bad.length,extensionBoundaries:['clone:false intentionally preserves nested object identity and an existing custom prototype','customMerge intentionally permits caller-returned objects; no general callback-output sanitization is claimed']};
fs.writeFileSync(path.join(here,'deepmerge-probe-final-results.json'),JSON.stringify(record,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({variants:variants.length,casesPerVariant:cases.length,originalFailures:results.filter(x=>!x.pass&&x.variant.startsWith('original/')).length,candidateFailures:bad.length}));if(bad.length)process.exitCode=1;
