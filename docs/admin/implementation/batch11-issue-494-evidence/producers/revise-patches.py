import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
old=json.loads((root/'scripts/tooling-repairs.json').read_bytes())
(out/'pre-adversarial-tooling-repairs.json').write_bytes((root/'scripts/tooling-repairs.json').read_bytes())
sha=lambda b:hashlib.sha256(b).hexdigest()
canonical={}
for name in ('braces','sprintf-js'):
 for p in (root/'node_modules'/name).rglob('*'):
  if not p.is_file():continue
  key=(name,p.relative_to(root/'node_modules'/name).as_posix())
  patch=next((x for x in old['patches'] if (x['package'],x['file'])==key),None)
  b=p.read_bytes()
  if patch:
   if patch['original_sha256'] is None:continue
   assert sha(b)==patch['repaired_sha256'],key
   s=b.decode()
   for e in reversed(patch['edits']):
    assert s.count(e['after'])==1,key
    s=s.replace(e['after'],e['before'])
   b=s.encode()
   assert sha(b)==patch['original_sha256'],key
  canonical[key]=b
  target=out/'canonical-upstream'/name/key[1]
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as f:f.write(b)
patches=old['patches']
expand=next(x for x in patches if x['file']=='lib/expand.js')
expand['edits'] += [
 {'before':"const append = (queue = '', stash = '', enclose = false) => {",'after':"const append = (queue = '', stash = '', enclose = false, depth = 0) => {\n  bounds.walkDepth(depth);"},
 {'before':'append(value, stash, enclose)','after':'append(value, stash, enclose, depth + 1)'},
 {'before':'append(item, ele, enclose)','after':'append(item, ele, enclose, depth + 1)'}]
sprintf=next(x for x in patches if x['package']=='sprintf-js')
guard="""                var conversion = match[8], precision = match[7]
                if (/[efg]/.test(conversion) && precision !== undefined) {
                    if (!((typeof precision === 'string' && /^\\d+$/.test(precision)) || typeof precision === 'number') ||
                        !Number.isInteger(Number(precision)) || Number(precision) < (conversion === 'g' ? 1 : 0) || Number(precision) > 100) {
                        throw Object.assign(new SyntaxError('[sprintf] precision outside ECMAScript bounds'), { code: 'ERR_SPRINTF_PRECISION' })
                    }
                }
"""
sprintf['edits']=[{'before':'                match = parse_tree[i] // convenience purposes only','after':'                match = parse_tree[i] // convenience purposes only\n'+guard}]
for before,after in [('re.not_string.test(match[8])','re.not_string.test(conversion)'),('re.not_json.test(match[8])','re.not_json.test(conversion)'),('switch (match[8])','switch (conversion)'),('re.json.test(match[8])','re.json.test(conversion)')]:
 sprintf['edits'].append({'before':before,'after':after})
# re.number is used twice; bind each surrounding expression separately.
for before,after in [('if (re.number.test(match[8]))','if (re.number.test(conversion))'),('if (re.number.test(match[8]) &&','if (re.number.test(conversion) &&')]:
 sprintf['edits'].append({'before':before,'after':after})
for before,after in [('match[7] ? arg.toExponential(match[7])','precision ? arg.toExponential(precision)'),('match[7] ? parseFloat(arg).toFixed(match[7])','precision ? parseFloat(arg).toFixed(precision)'),('match[7] ? parseFloat(arg).toPrecision(match[7])','precision ? parseFloat(arg).toPrecision(precision)')]:
 sprintf['edits'].append({'before':before,'after':after})
final=dict(canonical)
for patch in patches:
 key=(patch['package'],patch['file'])
 s=patch['addition'] if patch['original_sha256'] is None else canonical[key].decode()
 for e in patch['edits']:
  assert s.count(e['before'])==1,(key,e['before'])
  s=s.replace(e['before'],e['after'])
 final[key]=s.encode();patch['repaired_sha256']=sha(final[key])
packages=[]
for name,version in [('braces','3.0.3'),('sprintf-js','1.0.3')]:
 files={f:{'original_sha256':sha(canonical[(n,f)]) if (n,f) in canonical else None,'repaired_sha256':sha(b)} for (n,f),b in sorted(final.items()) if n==name}
 packages.append({'name':name,'version':version,'files':files})
(root/'scripts/tooling-repairs.json').write_text(json.dumps({'schema':2,'packages':packages,'patches':patches},indent=2)+'\n')
(out/'canonical-upstream-manifest.json').write_text(json.dumps({'files':{n+'/'+f:sha(b) for (n,f),b in sorted(canonical.items())},'generator_sha256':sha(Path(__file__).read_bytes()),'input_manifest_sha256':sha((out/'pre-adversarial-tooling-repairs.json').read_bytes())},indent=2)+'\n')
print(json.dumps({'canonical_files':len(canonical),'patches':len(patches),'package_inventories':[len(p['files']) for p in packages]}))
