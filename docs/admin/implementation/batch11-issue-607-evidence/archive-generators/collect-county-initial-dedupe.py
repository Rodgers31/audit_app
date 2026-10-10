import concurrent.futures,subprocess,json,hashlib
from pathlib import Path
OUT=Path(__file__).resolve().parent
queries={'county-initial-exact-search':'repo:Rodgers31/audit_app "has exactly one h1"','county-legacy-exact-search':'repo:Rodgers31/audit_app "normal 47-county list"','county-duplicate-search':'repo:Rodgers31/audit_app counties duplicate in:title,body,comments','county-heading-search':'repo:Rodgers31/audit_app county heading in:title,body,comments','budget-refresh-search':'repo:Rodgers31/audit_app budget in:title,body,comments'}
def get(item):
 name,q=item
 args=['gh','api','search/issues','--method','GET','-f','q='+q,'-f','per_page=100']
 raw=subprocess.check_output(args);d=json.loads(raw)
 with (OUT/(name+'.json')).open('xb') as f:f.write(raw)
 print(name,d.get('total_count'),d.get('incomplete_results'),flush=True)
 return {'name':name,'command':args,'total_count':d['total_count'],'incomplete_results':d['incomplete_results'],'sha256':hashlib.sha256(raw).hexdigest()}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: rows=list(ex.map(get,queries.items()))
for issue in [221,449,450,445,607,601,291,545]:
 args=['gh','issue','view',str(issue),'--repo','Rodgers31/audit_app','--json','number,title,state,body,comments,url']
 raw=subprocess.check_output(args)
 with (OUT/('county-candidate-'+str(issue)+'.json')).open('xb') as f:f.write(raw)
 rows.append({'issue':issue,'command':args,'sha256':hashlib.sha256(raw).hexdigest()})
with (OUT/'county-initial-dedupe-collection.json').open('x') as f:json.dump(rows,f,indent=2)
