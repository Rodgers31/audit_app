'use strict';
const Module=require('node:module');const path=require('node:path');const req=Module.createRequire(path.join(__dirname,'versions/package.json'));
const affected=req('mm10');const original=Module._load;let calls=0;
Module._load=function(request,parent){if(request==='minimatch'&&parent&&parent.filename.includes('@typescript-eslint/typescript-estree')){calls++;return affected;}return original.apply(this,arguments);};
process.on('exit',()=>{if(calls)console.error('review-minimatch-red-interceptions='+calls);});
