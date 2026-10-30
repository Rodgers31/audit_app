/** Pre-rendered illustrative source DTOs, never a proxy to production. */
import samples from './comparison-examples.json';
export async function GET(req: Request) {
 const selected=new URL(req.url);
 const params=(u:URL)=>JSON.stringify(Array.from(u.searchParams.entries()).sort());
 const sample=samples.find(s=>{const url=new URL(s.link);return selected.pathname==='/api/v1'+url.pathname&&params(selected)===params(url);});
 return Response.json(sample?.public_report??{detail:{code:'REPORT_VIEW_UNAVAILABLE',message:'The exact local sample is unavailable.'}},{status:sample?200:410,headers:{'Cache-Control':'no-store'}});
}
