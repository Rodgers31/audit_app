"""Hash contract for persistent permission profile; no connections or files."""
import hashlib,json,re
PROFILE='persistent_privileges_excluding_exact_numeric_temp_schema_names_v1'
def require(x):
 if x is not True:raise ValueError('PERSISTENT_PROFILE_REFUSED')
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(v):return hashlib.sha256(canonical(v).encode('utf8')).hexdigest()
def catalog_projection(catalog,logical):
 # Only structural proxies: no row hashes or sequence states are represented as
 # observations. The returned/hash-bound object is solely the real catalog.
 require(type(catalog)is dict and catalog.get('kind')=='catalog')
 shape=[catalog]
 for r in catalog['relations']:
  if r[2]in('r','m'):shape.append({'kind':'table','schema':r[0],'name':r[1],'count':0,'sha256':'0'*64})
  elif r[2]=='S':shape.append({'kind':'sequence','schema':r[0],'name':r[1],'last_value':1,'is_called':False})
 return logical.canonical_inventory(shape)[0]
def durable_projection(props,acquisition):
 acquisition.validate_recovery_prerequisites(props)
 result={k:v for k,v in props.items() if k not in('kind','readonly','isolation','activity_counts')}
 result=json.loads(json.dumps(result,allow_nan=False))
 if result['database_properties']['acl']is not None:result['database_properties']['acl'].sort()
 for key in('database_role_settings','system_schema_acls','system_relation_acls','system_column_acls','system_routine_acls','parameter_acls'):
  if result[key]is not None:
   for row in result[key]:
    if row[-1]is not None:row[-1].sort()
   result[key].sort(key=lambda row:json.dumps(row,sort_keys=True))
 return result

def validate_matrix(matrix,roles):
 require(type(roles)is list and bool(roles) and all(type(name)is str and bool(name) and '\x00'not in name for name in roles) and len(roles)==len(set(roles)))
 require(type(matrix)is dict and set(matrix)=={'kind','server_version','rows'} and matrix['kind']=='effective_privileges' and matrix['server_version']=='17.6' and type(matrix['rows'])is list and bool(matrix['rows']))
 require(all(type(row)is list and len(row)==5 and type(row[0])is str and all(type(x)is bool for x in row[1:4]) and type(row[4])is str and re.fullmatch('[0-9a-f]{64}',row[4])is not None for row in matrix['rows']))
 require([r[0]for r in matrix['rows']]==roles and len(roles)==len(set(roles)))
 return matrix
