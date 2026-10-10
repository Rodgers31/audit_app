import hashlib,json
from pathlib import Path
root=Path('/Users/roger/.codex/worktrees/batch11-dependency-compatibility/audit_app/frontend')
sha=lambda b:hashlib.sha256(b).hexdigest()
helper="""'use strict';
// Fixed policy: no caller option can disable the recursion ceiling.
exports.parseDepth = depth => {
  if (depth > 64) {
    throw Object.assign(new SyntaxError('braces nesting exceeds the reviewed 64-level limit'), { code: 'ERR_BRACES_DEPTH' });
  }
};
exports.walkDepth = depth => {
  if (depth > 128) {
    throw Object.assign(new SyntaxError('braces AST exceeds the reviewed 128-level walk limit'), { code: 'ERR_BRACES_DEPTH' });
  }
};
"""
guard="""                if (/[efg]/.test(match[8]) && match[7] !== undefined) {
                    var precision = match[7]
                    if (!((typeof precision === 'string' && /^\\d+$/.test(precision)) || typeof precision === 'number') ||
                        !Number.isInteger(Number(precision)) || Number(precision) < (match[8] === 'g' ? 1 : 0) || Number(precision) > 100) {
                        throw Object.assign(new SyntaxError('[sprintf] precision outside ECMAScript bounds'), { code: 'ERR_SPRINTF_PRECISION' })
                    }
                }
"""
def entry(package,version,file,edits=None,addition=None):
 original=(root/'node_modules'/package/file).read_bytes() if addition is None else None
 final=original.decode() if original else addition
 for a,b in (edits or []):
  if final.count(a)!=1:raise ValueError((file,a,final.count(a)))
  final=final.replace(a,b)
 data=final.encode()
 return {'package':package,'version':version,'file':file,'original_sha256':sha(original) if original else None,'repaired_sha256':sha(data),'edits':[{'before':a,'after':b} for a,b in (edits or [])],'addition':addition}
patches=[entry('braces','3.0.3','lib/audit-bounds.js',addition=helper)]
patches.append(entry('braces','3.0.3','lib/parse.js',[("'use strict';","'use strict';\n\nconst bounds = require('./audit-bounds');"),('      block = push({ type: \'paren\', nodes: [] });','      bounds.parseDepth(stack.length);\n      block = push({ type: \'paren\', nodes: [] });'),('      block = push(brace);','      bounds.parseDepth(stack.length);\n      block = push(brace);')]))
for file,fn,walk_call in [('lib/stringify.js','stringify','stringify(child)'),('lib/compile.js','walk','walk(child, node)'),('lib/expand.js','walk','walk(child, node)')]:
 edits=[("'use strict';","'use strict';\n\nconst bounds = require('./audit-bounds');"),(f'  const {fn} = (node, parent = {{}}) => {{',f'  const {fn} = (node, parent = {{}}, depth = 0) => {{\n    bounds.walkDepth(depth);'),(walk_call,f'{fn}(child, '+('node' if fn=='walk' else '{}')+', depth + 1)')]
 if file=='lib/expand.js':
  edits.extend([('    while (p.type', '    let parentDepth = 0;\n    while (p.type'),('      p = p.parent;', '      bounds.walkDepth(++parentDepth);\n      p = p.parent;'),('    while (block.type', '    parentDepth = 0;\n    while (block.type'),('      block = block.parent;', '      bounds.walkDepth(++parentDepth);\n      block = block.parent;')])
 patches.append(entry('braces','3.0.3',file,edits))
patches.append(entry('braces','3.0.3','lib/utils.js',[("'use strict';","'use strict';\n\nconst bounds = require('./audit-bounds');"),('  const flat = arr => {','  const flat = (arr, depth = 0) => {\n    bounds.walkDepth(depth);'),('        flat(ele);','        flat(ele, depth + 1);')]))
patches.append(entry('sprintf-js','1.0.3','src/sprintf.js',[('                switch (match[8]) {',guard+'\n                switch (match[8]) {')]))
output=root/'scripts/tooling-repairs.json'
output.write_text(json.dumps({'schema':1,'patches':patches},indent=2)+'\n')
print(output)
