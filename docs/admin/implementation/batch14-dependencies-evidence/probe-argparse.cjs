'use strict';
// Diagnostic capture only: reports actual caller and child outcomes without
// turning a smaller audit into a compatibility verdict. Does not modify source.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {createRequire} = require('node:module');
const {spawnSync} = require('node:child_process');
async function main() {
  if (process.argv.length !== 3) throw new Error('Usage: node probe-argparse.cjs /absolute/frontend');
  const root = fs.realpathSync(process.argv[2]);
  const app = createRequire(path.join(root, 'package.json'));
  const nycPath = app.resolve('@istanbuljs/load-nyc-config');
  const nyc = createRequire(nycPath);
  const yamlPath = nyc.resolve('js-yaml/package.json');
  const yaml = createRequire(yamlPath);
  const argparsePath = yaml.resolve('argparse/package.json');
  const cliPath = path.join(path.dirname(yamlPath), 'bin/js-yaml.js');
  const cliCases = [
    {name:'help',args:['--help']}, {name:'version',args:['--version']},
    {name:'yaml',args:[],input:'all: true\ninclude: [src/**/*.ts]\n'},
    {name:'json',args:[],input:'{"all":true,"include":["src/**/*.ts"]}'},
    {name:'hidden-json',args:['--to-json'],input:'all: true\n'},
    {name:'malformed',args:[],input:'a: [\n'},
    {name:'compact-malformed',args:['--compact'],input:'a: [\n'},
    {name:'trace-malformed',args:['--trace'],input:'a: [\n'},
    {name:'unknown-option',args:['--batch14-absent-option']},
  ].map(c=>({name:c.name,args:c.args,input:c.input ?? null,
    child:child(spawnSync(process.execPath,[cliPath,...c.args],{encoding:'utf8',input:c.input ?? '',timeout:10000}))}));
  const repair = spawnSync(process.execPath, [path.join(root, 'scripts/apply-tooling-repairs.cjs'), '--check'], {cwd:root, encoding:'utf8', timeout:10000});
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'batch14-nyc-'));
  let config;
  try {
    fs.writeFileSync(path.join(fixture, 'package.json'), '{}');
    fs.writeFileSync(path.join(fixture, '.nycrc.yml'), 'all: true\ninclude:\n  - src/**/*.ts\nexclude:\n  - src/generated/**\n');
    config = await app('@istanbuljs/load-nyc-config').loadNycConfig({cwd:fixture});
  } finally {fs.rmSync(fixture, {recursive:true, force:true});}
  function child(p) {return {status:p.status, signal:p.signal, error:p.error?.message || null, stdout:p.stdout, stderr:p.stderr};}
  console.log(JSON.stringify({node:process.version, platform:process.platform, arch:process.arch,
    versions:{nyc:nyc('./package.json').version, yaml:yaml('./package.json').version, argparse:JSON.parse(fs.readFileSync(argparsePath)).version},
    resolved:{nyc:nycPath,yaml:yamlPath,argparse:argparsePath},nycConfig:config,cliCases,repair:child(repair)},null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
