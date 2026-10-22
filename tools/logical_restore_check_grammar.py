"""Pre-DDL allowlist for the two public CHECK predicates; no SQL is executed.

This is a rejection guard only. PostgreSQL's exact canonical reparse/dependency
proof remains mandatory; this module never establishes expression equivalence.
"""
import collections,re
class Refusal(RuntimeError):pass
def need(x):
 if x is not True:raise Refusal('UNAPPROVED_CHECK_SOURCE_GRAMMAR')
TOKEN=re.compile(r"\s+|::|>=|<=|=|[()[\],]|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+")
class Parser:
 def __init__(self,s):
  need(type(s)is str and 0<len(s)<16384 and '\x00'not in s)
  self.tokens=[];i=0
  while i<len(s):
   m=TOKEN.match(s,i);need(m is not None);value=m.group();i=m.end()
   if not value.isspace():self.tokens.append(value if value.startswith(("'",'"')) else value.lower())
  self.i=0;need(len(self.tokens)<2048)
 def peek(self):return self.tokens[self.i]if self.i<len(self.tokens)else None
 def get(self):
  t=self.peek();need(t is not None);self.i+=1;return t
 def take(self,t):need(self.get()==t)
 def expr(self):
  value=self.comparison()
  while self.peek()=='and':self.get();value=('and',value,self.comparison())
  return value
 def comparison(self):
  left=self.value();op=self.peek()
  if op=='between':
   self.get();low=self.value();self.take('and');high=self.value();return('and',('>=',left,low),('<=',left,high))
  if op in('=','>=','<='):
   self.get()
   if op=='=' and self.peek()=='any':self.get();self.take('(');right=self.value();self.take(')');return('any',left,right)
   return(op,left,self.value())
  return left
 def value(self):
  token=self.get()
  if token=='(':
   value=self.expr();self.take(')')
  elif token=='array':
   self.take('[');items=[self.value()]
   while self.peek()==',':self.get();items.append(self.value())
   self.take(']');value=('array',items)
  elif token=='length':self.take('(');value=('length',self.value());self.take(')')
  elif token in('domain','app_id','subject_digest','digest_version') or token in('"domain"','"app_id"','"subject_digest"','"digest_version"'):value=('column',token.strip('"'))
  elif token.startswith("'"):value=('literal',token[1:-1].replace("''","'"))
  elif re.fullmatch('[0-9]+',token):value=('integer',int(token))
  else:raise Refusal('UNAPPROVED_CHECK_SOURCE_GRAMMAR')
  while self.peek()=='::':
   self.get();typ=self.get()
   if typ=='character':self.take('varying');typ='character varying'
   need(typ in('text','character varying'))
   if self.peek()=='[':self.get();self.take(']');typ+='[]'
   value=('cast',value,typ)
  return value
 def parse(self):
  self.take('check');value=self.expr();need(self.peek()is None);return value

def stripped(node):
 if node[0]=='cast':return stripped(node[1])
 if node[0]=='array':return('array',tuple(stripped(x)for x in node[1]))
 return tuple(stripped(x)if isinstance(x,tuple)else x for x in node)
def leaves(node):return leaves(node[1])+leaves(node[2])if node[0]=='and'else[node]
def validate(identity,source):
 parsed=Parser(source).parse()
 def resolution_guard(node):
  if not isinstance(node,tuple):return
  if node[0]=='length':need(isinstance(node[1],tuple) and node[1][0]=='cast' and node[1][2]=='text')
  if node[0]=='any':need(isinstance(node[1],tuple) and node[1][0]=='cast' and node[1][2]=='text')
  for item in node[1:]:
   if isinstance(item,tuple):resolution_guard(item)
   elif isinstance(item,list):
    for part in item:resolution_guard(part)
 resolution_guard(parsed)
 tree=stripped(parsed)
 if identity==('public','etl_dispatch_domains','ck_etl_dispatch_domain'):
  expected=('any',('column','domain'),('array',tuple(('literal',x)for x in('audits','fiscal_summary','counties_budget','population','cra','opendata'))))
  need(tree==expected)
 elif identity==('public','social_privacy_ownership','ck_social_privacy_subject'):
  term=lambda op,name,n:(op,('length',('column',name)),('integer',n))
  expected=[term('>=','app_id',1),term('<=','app_id',64),term('=','subject_digest',64),term('>=','digest_version',1),term('<=','digest_version',32)]
  need(collections.Counter(leaves(tree))==collections.Counter(expected))
 else:raise Refusal('UNAPPROVED_CHECK_SCOPE')
 return True
