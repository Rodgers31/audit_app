import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,readFileSync,realpathSync,rmSync,symlinkSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,join} from 'node:path';
import test from 'node:test';

const script=resolve('browser-fixtures/b86-callback/prepare.mjs');
function run(output,root){return spawnSync(process.execPath,[script,output],{cwd:resolve('.'),env:{PATH:process.env.PATH,B86_CALLBACK_EVIDENCE_ROOT:root,B86_CALLBACK_RUNTIME_IMAGE:process.env.B86_CALLBACK_RUNTIME_IMAGE||'b86-callback-runtime:local'},encoding:'utf8',timeout:30000});}
test('actual generator accepts a fresh directory in an explicitly owned portable evidence root',()=>{
  const root=mkdtempSync(join(realpathSync(tmpdir()),'b86-callback-evidence-'));
  try{
    const output=join(root,'renderer'),result=run(output,root);
    assert.equal(result.status,0,result.stderr);
    assert.equal(JSON.parse(readFileSync(join(output,'fixture-source.json'),'utf8')).source,resolve('.'));
    assert.match(readFileSync(join(output,'app/api/v1/social/oauth/meta/callback/route.ts'),'utf8'),/history.replaceState/);
    assert.match(readFileSync(join(output,'app/api/v1/social/oauth/meta/callback/route.ts'),'utf8'),/synthetic-first-collector/);
    assert.notEqual(run(output,root).status,0,'existing evidence must never be overwritten');
  }finally{rmSync(root,{recursive:true,force:true});}
});
test('generator rejects traversal, sibling paths, symlinked ancestry and checkout output before writes',()=>{
  const root=mkdtempSync(join(realpathSync(tmpdir()),'b86-callback-boundaries-'));
  const sibling=root+'-sibling';mkdirSync(sibling);
  try{
    const link=join(root,'linked');symlinkSync(sibling,link);
    for(const output of [join(root,'fresh')+'/../escape',join(sibling,'fresh'),join(link,'fresh'),resolve('browser-fixtures/b86-callback/should-not-exist')]){
      const result=run(output,root);assert.notEqual(result.status,0);assert.equal(existsSync(output),false);
    }
    assert.notEqual(run(join(root,'fresh'),root+'/../'+root.split('/').at(-1)).status,0);
    assert.notEqual(run(resolve('browser-fixtures/b86-callback/should-not-exist'),resolve('.')).status,0);
  }finally{rmSync(root,{recursive:true,force:true});rmSync(sibling,{recursive:true,force:true});}
});
