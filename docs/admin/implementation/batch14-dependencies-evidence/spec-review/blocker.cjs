const fs=require('node:fs'),path=require('node:path');
const baseline='/Users/roger/.codex/worktrees/compatible-dependencies/audit_app/frontend';
const candidate=path.join(__dirname,'../argparse2-candidate/frontend');
const root=path.join(__dirname,'blocker-fixture');
fs.mkdirSync(path.join(root,'node_modules'),{recursive:true});
fs.copyFileSync(path.join(candidate,'package-lock.json'),path.join(root,'package-lock.json'));
fs.cpSync(path.join(baseline,'node_modules/braces'),path.join(root,'node_modules/braces'),{recursive:true});
const {planRepairs}=require(path.join(baseline,'scripts/apply-tooling-repairs.cjs'));
const results=[];
for(const production of [false,true]){
 try{planRepairs(root,{check:true,production});results.push({production,status:'unexpected-success'});process.exitCode=1;}
 catch(e){results.push({production,status:'rejected',message:e.message});if(e.message!=='tooling repair: missing locked sprintf-js')process.exitCode=1;}
}
fs.writeFileSync(path.join(__dirname,'blocker-results.json'),JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify(results));
