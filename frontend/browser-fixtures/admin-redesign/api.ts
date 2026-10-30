/** Explicit inert API. Unknown paths/mutations refuse; no proxy or credentials. */
import { accounts, post, system, validation } from '@/tests/socialFixtures';
import type { SocialPost } from '@/lib/api/social';
const savedCopy = 'Nairobi County pending bills data.\nNairobi County — Reported pending bills: county, FY 2025/26: 86899380000.00 units KES (actual; publisher-reported Grand Total stock as at 2026-06-30; completeness is not assumed).';
const sourceUrl='https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482';
let current=post({title:'Nairobi County pending bills data',origin_type:'generated',content_type:'debt_update',editorial_state:'pending_review',delivery_status:'not_requested',document:{...post().document,master:{text:savedCopy,link:'https://www.auditgava.com/debt',hashtags:[],media:[]}},references:[{url:sourceUrl,label:'Controller of Budget · Table 2.10, PDF page 52'}]});
const connected=accounts.map(a=>({...a,publishing_enabled:false}));
const respond=(data:unknown,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'private,no-store'}});
export async function GET(req:Request){
 const u=new URL(req.url),path=u.pathname.split('/social')[1];
 if(path==='/system/status')return respond({...system,publishing_enabled:false});
 if(path==='/accounts')return respond({accounts:connected});
 if(path==='/posts'){
  const state=u.searchParams.get('editorial_state'),origin=u.searchParams.get('origin_type'),category=u.searchParams.get('content_type');
  const rows=(!state||state===current.editorial_state)&&(!origin||origin===current.origin_type)&&(!category||category===current.content_type)?[current]:[];
  return respond({posts:rows,total:rows.length,page:1,page_size:20,has_more:false});
 }
 if(path==='/posts/'+current.id)return respond(current);
 if(path==='/posts/'+current.id+'/evidence')return respond({post_id:current.id,revision_id:current.revision_id,source_event_id:null,generator_metadata:{template_version:'factual-v1'},evidence:{evidence_version:3516,source:{source_type:'cob',source_key:'fixture:pending-bills',ingestion_id:'3516',facts:[{fact_id:'fixture:pending-bills:outstanding',entity:'Nairobi County',metric:'Reported pending bills',value:'86899380000.00',unit:'KES',scale:'units',period:'FY 2025/26',classification:'actual',comparison_basis:'publisher-reported Grand Total stock as at 2026-06-30; completeness is not assumed',document_url:sourceUrl,locator:'Table 2.10, Nairobi / Grand Total; PDF page 52 (printed page 18)',document_checksum:'919930622bc9fbc0c0b5cdcb566219e4f1432e7c9a3329dfd5bb23616cd33c20',publisher:'Office of the Controller of Budget',published_on:'2026-09-25',retrieved_at:'2026-10-29T13:25:38Z',verified_at:'2026-10-29T15:33:51Z'}]}}});
 if(path==='/automation/rules')return respond({items:[],page:1,has_more:false});
 return respond({detail:'Unknown inert fixture path'},404);
}
export async function POST(req:Request){
 const path=new URL(req.url).pathname.split('/social')[1];
 if(path==='/posts/'+current.id+'/validate')return respond(validation(current,false));
 if(path==='/posts'){const body=await req.json();current=post({...body,origin_type:'manual'});return respond(current);}
 return respond({detail:{code:'FIXTURE_REFUSED',message:'Delivery, control changes and approval are held in this fixture.',field_errors:[],target_errors:[],retryable:false}},409);
}
export async function PATCH(req:Request){
 const path=new URL(req.url).pathname.split('/social')[1];
 if(path!=='/posts/'+current.id)return respond({detail:'Held fixture operation'},403);
 const body=await req.json();
 if(body.expected_version!==current.version)return respond({detail:{code:'VERSION_CONFLICT',message:'Refresh this fixture revision.',field_errors:[],target_errors:[],retryable:false}},409);
 current={...current,...body,editorial_state:'draft',version:current.version+1,revision_id:'00000000-0000-4000-8000-'+String(current.version+40).padStart(12,'0')} as SocialPost;
 return respond(current);
}
