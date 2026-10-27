"use strict";
const test=require('node:test'),assert=require('node:assert/strict');
const manifest=require('../package.json');
test('application metadata declares the patched supported Node24 line',()=>{
 assert.equal(manifest.engines.node, '>=24.22.1 <25');
 assert.equal(require('../package-lock.json').packages[''].engines.node, manifest.engines.node);
 const fs=require('node:fs');
 assert.equal(fs.readFileSync(require('node:path').join(__dirname,'../.nvmrc'),'utf8').trim(), '24.22.1');
});

const { isSupportedNode }=require('./verify-node-runtime.cjs');
const { spawnSync }=require('node:child_process');
const path=require('node:path');
test('runtime guard rejects unsupported versions and malformed claims',()=>{
 for(const bad of [null,undefined,true,24,{},[],'','v24.22.1','24.22.1-rc.0','24.022.1','24.22.0','22.23.4','26.12.1','24.9007199254740992.1'])assert.equal(isSupportedNode(bad),false,String(bad));
 for(const good of ['24.22.1','24.22.2','24.23.0'])assert.equal(isSupportedNode(good),true,good);
});
test('the actual CLI checks the running binary rather than environment version claims',()=>{
 const run=spawnSync(process.execPath,[path.join(__dirname,'verify-node-runtime.cjs')],{
  encoding:'utf8',env:{PATH:process.env.PATH,NODE_VERSION:'20.9.0',HOME:'/scratch/home'}});
 assert.equal(run.status,0,run.stderr);
 assert.equal(JSON.parse(run.stdout).node,process.version);
 assert.equal(JSON.parse(run.stdout).supported,true);
});
