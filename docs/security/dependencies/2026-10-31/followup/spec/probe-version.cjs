'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {performance}=require('node:perf_hooks');
const args=JSON.parse(process.argv[2]);
if(!Number.isInteger(args.parts)||args.parts<1||args.parts>12)throw new Error('bounded parts required');
const name=args.module;
if(!/^mm(?:3|6|7|71|9|1024|10|1100|1101|11)$/.test(name))throw new Error('owned module required');
const requireVersion=require('node:module').createRequire(path.join(__dirname,'versions/package.json'));
const library=requireVersion(name);
const entry=requireVersion.resolve(name);
const metadata=JSON.parse(fs.readFileSync(path.join(__dirname,'versions/node_modules',name,'package.json'),'utf8'));
const C=library.Minimatch;
const observations={firstPhase:[],secondPhase:[],partsMatch:0};
const methods={firstPhasePreProcess:'firstPhase',secondPhasePreProcess:'secondPhase'};
const features={firstPhase:typeof C.prototype.firstPhasePreProcess==='function',secondPhase:typeof C.prototype.secondPhasePreProcess==='function',partsMatch:typeof C.prototype.partsMatch==='function'};
if(args.instrument){
 for(const[method,label]of Object.entries(methods)){
  const original=C.prototype[method];
  if(typeof original==='function')C.prototype[method]=function(rows,...rest){const before=rows.length;const out=original.call(this,rows,...rest);observations[label].push({before,after:out.length});return out;};
 }
 const original=C.prototype.partsMatch;
 if(typeof original==='function')C.prototype.partsMatch=function(...args){observations.partsMatch++;return original.apply(this,args);};
}
const pattern=args.family==='previous'?'a/**/../'.repeat(args.parts)+'leaf':Array(args.parts).fill('**/../a/b').join('/');
const options={braceExpandMax:args.max??8};
if(args.level!=='default')options.optimizationLevel=args.level;
const before=process.memoryUsage();const start=performance.now();
const matcher=new C(pattern,options);
const elapsed=performance.now()-start;const after=process.memoryUsage();
if(!Array.isArray(matcher.set)||!Array.isArray(matcher.globParts))throw new Error('No actual compile result');
console.log(JSON.stringify({module:name,version:metadata.version,entry,entry_sha256:createHash('sha256').update(fs.readFileSync(entry)).digest('hex'),family:args.family||'advisory',parts:args.parts,pattern,options,instrument:!!args.instrument,features,observations,globParts:matcher.globParts.length,setLength:matcher.set.length,elapsed_ms:elapsed,heap_delta:after.heapUsed-before.heapUsed,rss:after.rss}));
