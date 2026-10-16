const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const { spawnSync } = require('node:child_process');
const out = __dirname;
const baseline = '/Users/roger/.codex/worktrees/compatible-dependencies/audit_app/frontend';
const candidate = path.join(out, '../argparse2-candidate/frontend');
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
(async () => {
 const results = { runtime: {node: process.version, platform: process.platform, arch: process.arch}, roots: [] };
 for (const [label, root] of [['baseline',baseline],['candidate',candidate]]) {
  const req = createRequire(path.join(root,'package.json'));
  const nycPath = req.resolve('@istanbuljs/load-nyc-config');
  const nyc = req('@istanbuljs/load-nyc-config');
  const yr = createRequire(createRequire(nycPath).resolve('js-yaml'));
  const yamlDir = path.dirname(yr.resolve('js-yaml/package.json'));
  const cli = path.join(yamlDir, 'bin/js-yaml.js');
  const dir = path.join(out,label); fs.mkdirSync(dir,{recursive:true});
  fs.writeFileSync(path.join(dir,'package.json'), JSON.stringify({private:true}));
  const r = {label,root,hashes: Object.fromEntries(['package.json','package-lock.json','scripts/apply-tooling-repairs.cjs'].map(p=>[p,hash(path.join(root,p))])), versions:{yaml:yr('js-yaml/package.json').version,argparse:yr('argparse/package.json').version}, nyc:[],cli:[],repair:[]};
  const configs = [
   ['valid','check-coverage: true\ninclude: ["src/**/*.js"]\nlines: 91\n'],
   ['empty',''],
   ['null','null\n'],
   ['malformed','include: [broken\n'],
   ['invalid-extends','extends: [false]\n'],
   ['missing-extends','extends: ./missing.yaml\n'],
   ['circular','extends: ./circular.yaml\n'],
   ['inherited','extends: ./parent.yaml\nexclude: dist\n'],
  ];
  fs.writeFileSync(path.join(dir,'parent.yaml'),'report-dir: coverage-custom\ninclude: lib\n');
  for(const [name, body] of configs){
   const file=path.join(dir,name+'.yaml');fs.writeFileSync(file,body);
   try {const value=await nyc.loadNycConfig({cwd:dir,nycrcPath:file}); r.nyc.push({name,status:'resolved',value});}
   catch(e){r.nyc.push({name,status:'rejected',nameOfError:e.name,message:e.message});}
  }
  try{await nyc.loadNycConfig({cwd:dir,nycrcPath:'absent.yaml'});r.nyc.push({name:'absent',status:'resolved'});}catch(e){r.nyc.push({name:'absent',status:'rejected',message:e.message});}
  for(const [name,args,input] of [
   ['help',['--help'],''],['version',['--version'],''],['stdin-yaml',[],'a: 1\nb: [x, y]\n'],
   ['stdin-json',[],'{"a":1}'],['empty',[],''],['unknown',['--unknown'],''],
   ['missing-file',[path.join(dir,'absent.yaml')],''],['compact-malformed',['--compact'],'a: [\n'],
   ['trace-malformed',['--trace'],'a: [\n'],['deprecated-json',['--to-json'],'a: 1\n'],
   ['explicit-file',[path.join(dir,'valid.yaml')],''],['multi-doc',[],'a: 1\n---\nb: 2\n']
  ]){
   const p=spawnSync(process.execPath,[cli,...args],{cwd:dir,input,encoding:'utf8',timeout:10000});
   r.cli.push({name,args,status:p.status,signal:p.signal,error:p.error?.message,stdout:p.stdout,stderr:p.stderr});
  }
  const repair = req('./scripts/apply-tooling-repairs.cjs');
  for(const production of [false,true]){
   try {const plan=repair.planRepairs(root,{check:true,production});r.repair.push({production,status:'resolved',packages:plan.packages,absent:plan.absentPackages});}
   catch(e){r.repair.push({production,status:'rejected',message:e.message});}
  }
  const lock=req('./package-lock.json');r.lockPackages=Object.entries(lock.packages).filter(([p])=>/node_modules\/(argparse|sprintf-js)$/.test(p)).map(([p,v])=>({p,version:v.version}));
  results.roots.push(r);
 }
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2)+'\n');
 for(const r of results.roots) console.log(JSON.stringify({label:r.label,versions:r.versions,nyc:r.nyc.map(x=>({name:x.name,status:x.status})),cli:r.cli.map(x=>({name:x.name,status:x.status,stderr:x.stderr.slice(0,180)})),repair:r.repair,lockPackages:r.lockPackages}));
})().catch(e=>{console.error(e);process.exitCode=1;});
