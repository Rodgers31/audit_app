from pathlib import Path
import json,subprocess,sys,datetime
out=Path(__file__).resolve().parent
numbers=[int(x) for x in sys.argv[1:]] or [850,851,852,853]
records=[]
q='query($n:Int!){repository(owner:"Rodgers31",name:"audit_app"){pullRequest(number:$n){reviews(first:1){totalCount}comments(first:1){totalCount}reviewThreads(first:100){totalCount pageInfo{hasNextPage}nodes{id isResolved comments(first:100){totalCount pageInfo{hasNextPage}nodes{databaseId body author{login}}}}}}}}'
for n in numbers:
 d=json.loads(subprocess.check_output(['gh','pr','view',str(n),'--json','number,headRefOid,baseRefName,isDraft,state,reviewDecision,reviewRequests,closingIssuesReferences,statusCheckRollup,body'],text=True))
 for name,path in [('reviews',f'pulls/{n}/reviews'),('inline',f'pulls/{n}/comments'),('comments',f'issues/{n}/comments')]:
  pages=json.loads(subprocess.check_output(['gh','api','--paginate','--slurp','repos/Rodgers31/audit_app/'+path],text=True));d[name]=[x for page in pages for x in page]
 d['requests']=json.loads(subprocess.check_output(['gh','api',f'repos/Rodgers31/audit_app/pulls/{n}/requested_reviewers'],text=True))
 d['graphql']=json.loads(subprocess.check_output(['gh','api','graphql','-f','query='+q,'-F',f'n={n}'],text=True))['data']['repository']['pullRequest']
 records.append(d)
 print(json.dumps({'number':n,'head':d['headRefOid'],'base':d['baseRefName'],'state':d['state'],'draft':d['isDraft'],'decision':d['reviewDecision'],'counts':{k:len(d[k])for k in ['reviews','inline','comments']},'graphql_counts':{k:d['graphql'][k]['totalCount']for k in ['reviews','comments','reviewThreads']},'thread_pagination':d['graphql']['reviewThreads']['pageInfo'],'nested_pagination':[x['comments']['pageInfo']for x in d['graphql']['reviewThreads']['nodes']if x['comments']['pageInfo']['hasNextPage']],'unresolved':[x['id']for x in d['graphql']['reviewThreads']['nodes']if not x['isResolved']],'requests':d['requests'],'reviews':[(x['user']['login'],x['state'])for x in d['reviews']],'closing':d['closingIssuesReferences'],'checks':d['statusCheckRollup']}),flush=True)
at=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
f=out/('review-census-'+at+'.json');f.write_text(json.dumps(records,indent=2)+'\n');print('SAVED',f,flush=True)
