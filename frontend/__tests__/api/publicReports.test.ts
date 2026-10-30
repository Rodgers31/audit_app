import { decodePublicReport, reportSelector } from '@/lib/api/publicReports';

const selector=reportSelector('national_budget','1',new URLSearchParams({view:'financial',record:'3',snapshot:'a'.repeat(64)}))!;
function response(){return {schema_version:1,domain:'national_budget',view:'financial',snapshot:'a'.repeat(64),title:'National budget figures',entity:'Kenya',period:'FY 2025/26',period_start:'2025-07-01',period_end:'2026-06-30',publisher:'Controller of Budget',published_on:'2026-09-04',catalogued_on:null,availability:'published',figures:[{entity:'Kenya',metric:'Actual expenditure: Health',period:'FY 2025/26',value:'1200000000.00',display_value:'KSh 1.2 billion',unit:'KES',scale:'units',classification:'actual',comparison_basis:'actual expenditure, same sector and annual reporting period',locator:'PDF page 1 / Health'}],sources:[{url:'https://cob.go.ke/owned-report.pdf',publisher:'Controller of Budget',locator:'PDF page 1 / Health'}]};}

test('decode keeps exact strings and exact requested report identity',()=>{
  expect(decodePublicReport(response(),selector).figures[0].value).toBe('1200000000.00');
  expect(decodePublicReport(response(),selector).sources[0].url).toContain('cob.go.ke');
});
test.each([{domain:'audits'},{snapshot:'b'.repeat(64)},{view:'report'},{period_end:'2025-02-30'},{published_on:null},{figures:[]}])('rejects mismatching or malformed report %j',change=>{
  expect(()=>decodePublicReport({...response(),...change},selector)).toThrow();
});
test.each([null,NaN,true,'NaN','1e9','1,200'])('rejects malformed figure %s',value=>{
  const raw=response();(raw.figures[0] as {value:unknown}).value=value;
  expect(()=>decodePublicReport(raw,selector)).toThrow();
});
test.each(['javascript:alert(1)','https://user:password@cob.go.ke/','http://cob.go.ke/report'])('rejects unsafe publisher references %s',url=>{
  const raw=response();raw.sources[0].url=url;expect(()=>decodePublicReport(raw,selector)).toThrow();
});
test.each(['view=financial&record=3','view=report&entity=1&snapshot='+'a'.repeat(64)+'&view=financial','view=financial&record=3&entity=1&snapshot='+'a'.repeat(64)])('invalid selectors never become a default report %s',params=>{
  expect(reportSelector('national_budget','1',new URLSearchParams(params))).toBeUndefined();
});


test.each([{entity:'Mombasa County'},{period:'FY 1999/00'}])('figure scope must agree with the report header %j',change=>{
  const raw=response();Object.assign(raw.figures[0],change);
  expect(()=>decodePublicReport(raw,selector)).toThrow();
});
