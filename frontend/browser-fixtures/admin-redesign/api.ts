/** Closed local samples. No proxy, provider, approval, publication or control writes. */
import { accounts, post, system } from '@/tests/socialFixtures';
import type { SocialAccount, SocialPost } from '@/lib/api/social';
import { sourceRecordsFixture } from './operations';
import samples from './comparison-examples.json';
import { fixtureAsset } from './media';
const platforms = ['facebook','instagram','threads','x','tiktok'] as const;
const formats = [['text','image','reel'],['image','reel'],['text','image','carousel','video'],['text','image','video'],['image','carousel','video']] as const;
const connected: SocialAccount[]=platforms.map((platform,i)=>({...accounts[0],id:'00000000-0000-4000-8000-'+String(20+i).padStart(12,'0'),platform,display_name:'AuditGava '+platform+' · local sample',handle:'@auditgava-sample',publishing_enabled:false,draft_formats:[...formats[i]],capabilities:{...accounts[0].capabilities,eligible:false,adapter_available:false,supported_formats:[],feature_states:{publishing:'restricted'}}}));
const posts: SocialPost[]=samples.map(s=>post({id:s.id,title:s.title,content_type:s.content_type as SocialPost['content_type'],origin_type:'generated',editorial_state:'pending_review',delivery_status:'not_requested',document:s.document as SocialPost['document'],references:s.references}));
const respond=(data:unknown,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'private,no-store'}});
export async function GET(req:Request){
 const u=new URL(req.url),path=u.pathname.split('/social')[1];
 if(path==='/system/status')return respond({...system,publishing_enabled:false});
 if(path==='/accounts')return respond({accounts:connected});
 if(path==='/media/capabilities')return respond({upload_available:false,library_available:true,allowed_mime_types:[],max_image_bytes:10485760,max_video_bytes:52428800,unavailable_reason:'Uploads are held. One local fixture image can demonstrate media selection.'});
 if(path==='/media/assets')return respond({assets:[fixtureAsset],total:1,page:1,page_size:20,has_more:false});
 if(path==='/posts'){
  const state=u.searchParams.get('editorial_state'),origin=u.searchParams.get('origin_type'),category=u.searchParams.get('content_type');
  const rows=posts.filter(p=>(!state||state===p.editorial_state)&&(!origin||origin===p.origin_type)&&(!category||category===p.content_type));
  return respond({posts:rows,total:rows.length,page:1,page_size:20,has_more:false});
 }
 const selected=posts.find(p=>path==='/posts/'+p.id||path==='/posts/'+p.id+'/evidence');
 if(selected){
  if(path.endsWith('/evidence')){const sample=samples.find(s=>s.id===selected.id)!;return respond({post_id:selected.id,revision_id:selected.revision_id,source_event_id:null,generator_metadata:sample.generator_metadata,evidence:{evidence_version:sample.source.evidence_version,source:sample.source}});}
  return respond(selected);
 }
 if(path==='/automation/rules'||path==='/automation/decisions')return respond({[path.endsWith('rules')?'rules':'decisions']:[],total:0,page:1,page_size:20,has_more:false});
 if(path==='/generation/controls')return respond({version:1,drafts_enabled:false,shadow_enabled:false,source_allowlist:[],targets:[]});
 if(path==='/generation/capabilities')return respond([{domain:'pending_bills',financial:true,reports:true,reason:'qualified_native_cells_required'},{domain:'national_budget',financial:true,reports:true,reason:'qualified_native_cells_required'},{domain:'revenue_by_source',financial:true,reports:true,reason:'qualified_native_cells_required'},{domain:'opendata',financial:false,reports:false,reason:'source_extracted_not_publication_qualified'}]);
 if(path==='/generation/source-records')return sourceRecordsFixture(u);
 return respond({detail:'Unknown inert fixture path'},404);
}
export async function POST(req:Request){
 const path=new URL(req.url).pathname.split('/social')[1];
 const selected=posts.find(p=>path==='/posts/'+p.id+'/validate');
 if(selected)return respond({valid:false,rules_version:'social-v1',errors:[],warnings:[],targets:selected.document.targets.map(t=>({account_id:t.account_id,platform:connected.find(a=>a.id===t.account_id)!.platform,valid:false,errors:[{code:'PUBLISHING_DISABLED',field:'capabilities',message:'Publishing and provider access are held for owner review.'}],warnings:[],resolved_preview:null}))});
 if(path==='/generation/preview'){const body=await req.json();return respond({drafts_enabled:false,results:body.record_ids.map((record_id:number)=>({record_id,status:'baseline',reason:'first_observation',source_document_id:1}))});}
 return respond({detail:{code:'FIXTURE_REFUSED',message:'Delivery, control changes and approval are held in this fixture.',field_errors:[],target_errors:[],retryable:false}},409);
}
export async function PATCH(req:Request){
 const path=new URL(req.url).pathname.split('/social')[1],index=posts.findIndex(p=>path==='/posts/'+p.id);
 if(index<0)return respond({detail:'Held fixture operation'},403);
 const current=posts[index],body=await req.json();
 if(body.expected_version!==current.version)return respond({detail:{code:'VERSION_CONFLICT',message:'Refresh this fixture revision.',field_errors:[],target_errors:[],retryable:false}},409);
 posts[index]={...current,...body,editorial_state:'draft',version:current.version+1,revision_id:'00000000-0000-4000-8000-'+String(current.version+100).padStart(12,'0')};
 return respond(posts[index]);
}
