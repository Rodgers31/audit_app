import api from '@/lib/api/axios';
import { generationApi } from '@/lib/api/socialGeneration';
import { parseGenerationOutcome } from '@/lib/admin/ingestion';
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{post:jest.fn()}}));
const body={domain:'counties_budget',record_ids:[1,2],ingestion_id:42,reports:true,backfill:false};
const item=(record_id:number)=>({record_id,status:'baseline',reason:'first_observation',source_document_id:1});

test.each([{results:[item(999)]},{results:[item(1)]},{results:[item(2),item(1)]}])('preview refuses mismatched, missing or reordered cohorts',async ({results})=>{
  (api.post as jest.Mock).mockResolvedValue({data:{drafts_enabled:false,results}});
  await expect(generationApi.preview(body)).rejects.toThrow();
});
test('matching preview cohort remains observable',async()=>{
  (api.post as jest.Mock).mockResolvedValue({data:{drafts_enabled:false,results:[item(1),item(2)]}});
  expect((await generationApi.preview(body)).results.map(r=>r.record_id)).toEqual([1,2]);
});
const uncertain={state:'failed',execution_unverified:true,processed:null,drafts_created:null,baselines:null,unchanged:null,refused:null};
const confirmed={processed:2,drafts_created:1,baselines:1,unchanged:0,refused:0};
test('unknown total retains independently confirmed lower bound',()=>{
  expect(parseGenerationOutcome({...uncertain,confirmed})).toEqual({...uncertain,confirmed});
});
test.each([{...confirmed,processed:true},{...confirmed,drafts_created:NaN},{...confirmed,baselines:-1},{...confirmed,processed:3},{...confirmed,extra:1},null])('malformed confirmed lower bound cannot certify progress',confirmed=>{
  expect(()=>parseGenerationOutcome({...uncertain,confirmed})).toThrow();
});
