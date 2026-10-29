/** Inert public landing data. Only the disclosed pending-bills example is populated. */
const county = {
 id:'71',name:'Nairobi',slug:'nairobi-county',coordinates:[36.82,-1.29],governor:null,
 demographics:{population:null,population_year:null,male_population:null,female_population:null,urban_population:null,rural_population:null,population_density:null},
 economic_profile:{economic_base:null,major_issues:[],major_issues_source:null},
 budget:{total_allocated:null,total_spent:null,utilization_rate:null,development_budget:null,recurrent_budget:null,per_capita_budget:null,sector_breakdown:{},fiscal_year:null,source:null},
 revenue:{total_revenue:null,local_revenue:null,equitable_share:null},
 debt:{total_debt:null,pending_bills:86899380000,debt_to_budget_ratio:null,per_capita_debt:null,breakdown:[],withheld:null},
 audit:{status:'pending',grade:null,health_score:null,findings_count:0,total_amount_involved:null,total_amount_involved_reason:'awaiting_sourced_data',by_severity:{},findings:[]},
 health_history:[],missing_funds:{total_amount:null,cases_count:0,cases:[],reason:'awaiting_sourced_data',withheld:null},
 stalled_projects:{count:0,total_contracted_value:null,total_amount_paid:null,projects:[]},
 financial_summary:{health_score:null,grade:null,budget_execution_rate:null,pending_bills_ratio:null,debt_sustainability:null},
 data_sources:{budget:null,audit:null,debt:'Local review example',population:null},
};
export async function GET(req: Request) {
 const url=new URL(req.url), path=url.pathname;
 const respond=(value:unknown,status=200)=>Response.json(value,{status,headers:{'Cache-Control':'no-store'}});
 if(path.endsWith('/comprehensive') && path.includes('/nairobi-county/')) return respond(county);
 if(path.endsWith('/fiscal-years')) return respond({years:[],latest_reported:null});
 if(path==='/api/v1/auth/watchlist') return respond([]);
 if(path.includes('/pending-bills/counties/') && /\/(71|nairobi-county)$/.test(path)) {
  const day=url.searchParams.get('as_at'), available=!day||day==='2026-06-30';
  return respond({county:'Nairobi County',county_id:'71',status:available?'success':'no_data',total_pending:available?86899380000:null,pending_bills_as_at:available?'2026-06-30':null,selection:{as_at:day||'2026-06-30'},
   pending_bills_source:available?{publisher:'Office of the Controller of Budget',url:'https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482'}:null,
   pending_bills_notes:[],
   breakdown_by_type:{},breakdown_by_type_absent_reason:'loans_table_carries_no_bill_type',aging_buckets:null,aging_buckets_absent_reason:'loans_table_carries_no_aging_data'});
 }
 return respond({detail:'Unimplemented local public fixture read'},404);
}
