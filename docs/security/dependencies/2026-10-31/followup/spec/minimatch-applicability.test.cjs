'use strict';
// Bounded controls for GHSA-g3hv-75wg-m249's optimizer mechanism only.
// These checks do not certify legacy minimatch against arbitrary ReDoS patterns.
const assert=require('node:assert/strict');const path=require('node:path');const {createRequire}=require('node:module');const {spawnSync}=require('node:child_process');const {test}=require('node:test');
const frontend=process.env.SPEC_FRONTEND_ROOT?path.resolve(process.env.SPEC_FRONTEND_ROOT):path.resolve(__dirname,'..');
const req=createRequire(path.join(frontend,'package.json'));
test('exact legacy caller has no optimizer phase and does not amplify the bounded upstream trigger',()=>{
 const entry=req.resolve('minimatch');assert.equal(req('minimatch/package.json').version,'3.1.5');
 const script=`const assert=require('node:assert/strict');const mm=require(${JSON.stringify(entry)});const pattern=Array(8).fill('**/../a/b').join('/');const matcher=new mm.Minimatch(pattern,{optimizationLevel:2,braceExpandMax:8});assert.equal(matcher.set.length,1);assert.equal(matcher.globParts.length,1);for(const key of ['firstPhasePreProcess','secondPhasePreProcess','partsMatch'])assert.equal(typeof mm.Minimatch.prototype[key],'undefined');assert.equal(mm('src/owned.js','**/*.js'),true);assert.equal(mm.makeRe('src/**').test('src/owned.js'),true);console.log(JSON.stringify({rows:matcher.set.length,mechanism:'no optimizer preprocessing phases',legacyMakeRe:true}));`;
 const child=spawnSync(process.execPath,['--max-old-space-size=64','-e',script],{encoding:'utf8',timeout:2000,env:{PATH:path.dirname(process.execPath)}});
 assert.ifError(child.error);assert.equal(child.signal,null);assert.equal(child.status,0,child.stderr);assert.equal(JSON.parse(child.stdout).rows,1);
});
test('actual modern TypeScript caller caps that same trigger and retains small-pattern semantics',()=>{
 const typescript=createRequire(req.resolve('@typescript-eslint/typescript-estree'));const {Minimatch}=typescript('minimatch');assert.equal(typescript('minimatch/package.json').version,'11.0.3');
 const matcher=new Minimatch(Array(8).fill('**/../a/b').join('/'),{optimizationLevel:2,braceExpandMax:8});assert.equal(matcher.set.length,8);
 const small=new Minimatch('**/../a/b/**/../c/d',{optimizationLevel:2});assert.equal(small.set.length,4);assert.equal(small.match('../a/b/../c/d'),true);assert.equal(small.match('x/a/b/y/c/d'),true);
});
