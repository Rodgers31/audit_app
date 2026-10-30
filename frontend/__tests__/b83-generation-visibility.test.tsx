import api from '@/lib/api/axios';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import GenerationPreview from '@/components/admin/social/GenerationPreview';
import GenerationOutcomes from '@/components/admin/social/GenerationOutcomes';
import { generationApi, decodePreview, decodeCapabilities } from '@/lib/api/socialGeneration';
import { parseGenerationOutcome } from '@/lib/admin/ingestion';
jest.mock('next/navigation',()=>({useSearchParams:()=>new URLSearchParams()}));
jest.mock('@/lib/api/axios',()=>({get:jest.fn()}));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 'inert' } }) }));
jest.mock('@/lib/hooks/useSocial',()=>({useSocialMutation:()=>({run:jest.fn(),isPending:false,error:null})}));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/api/socialGeneration', () => ({...jest.requireActual('@/lib/api/socialGeneration'),generationApi:{capabilities:jest.fn(),preview:jest.fn(),sourceRecords:jest.fn()}}));
const capability = {domain:'opendata',financial:false,reports:false,reason:'source_extracted_not_publication_qualified'};
let mockDomain='revenue_by_source';
beforeEach(() => {jest.clearAllMocks();
  (api.get as jest.Mock).mockImplementation(async(path,config)=>{const domain=config?.params?.domain??'revenue_by_source';const job={id:42,domain,status:'completed',dry_run:false,started_at:'2026-10-28T10:00:00Z',finished_at:'2026-10-28T10:01:00Z',duration_seconds:60,items_processed:1,items_created:1,items_updated:0,errors:[],error_count:0,diagnostics_redacted:true,created_at:'2026-10-28T10:00:00Z',metadata:{source_mode:'live'}};if(path.endsWith('/42'))return {data:{...job,domain:mockDomain}};return {data:{jobs:[job],total:1,page:1,page_size:20,has_more:false}};});
  (generationApi.sourceRecords as jest.Mock).mockImplementation(async selection=>({...selection,page_size:25,total:1,record_ids:[12],has_more:false}));(generationApi.capabilities as jest.Mock).mockResolvedValue([capability]);});

test('unsupported source explains its absent contract without asking for IDs or mutating',async()=>{
  render(<QueryClientProvider client={new QueryClient()}><GenerationPreview /></QueryClientProvider>);
  await screen.findByRole('option',{name:'OpenData'});
  fireEvent.change(screen.getByLabelText('Source'),{target:{value:'opendata'}});
  expect(screen.getByRole('button',{name:'2. Preview without saving'})).toBeDisabled();
  expect(screen.getByText(/does not support the selected content/)).toBeInTheDocument();
  expect(generationApi.preview).not.toHaveBeenCalled();
});

test('missing receipts and uncertain execution never render zero-created success',()=>{
  const {rerender}=render(<GenerationOutcomes metadata={{}} />);
  expect(screen.getAllByText(/outcome is unknown/)).toHaveLength(2);
  rerender(<GenerationOutcomes metadata={{post_commit_generation:{state:'unavailable',execution_unverified:true,reason:'hook_not_executed'}}} />);
  expect(screen.getByText(/Counters are unknown/)).toBeInTheDocument();
  expect(screen.queryByText(/Drafts created 0/)).not.toBeInTheDocument();
});

test('known reasons survive safe job decoding; private diagnostics do not',()=>{
  const raw={state:'unavailable',execution_unverified:false,processed:1,drafts_created:0,baselines:0,unchanged:0,refused:1,reason:'SOURCE_SECRET',refusal_reasons:{publisher_date_receipt_unavailable:1}};
  expect(parseGenerationOutcome(raw)).toEqual({...raw,reason:undefined});
});

test.each([true,NaN,Infinity,-1,2147483648])('preview decoder refuses hostile record identity %p',record_id=>{
  expect(()=>decodePreview({drafts_enabled:false,results:[{record_id,status:'baseline',reason:'first_observation',source_document_id:1}]})).toThrow();
});
test('capability decoder rejects unknown reasons and duplicate domains',()=>{
  expect(()=>decodeCapabilities([{...capability,reason:'PRIVATE_DIAGNOSTIC'}])).toThrow();
  expect(()=>decodeCapabilities([capability,capability])).toThrow();
});


test('confirmed refusal reasons survive an uncertain later record without claiming totals',()=>{
  const raw={state:'failed',execution_unverified:true,reason:'generation_database_unavailable',processed:null,drafts_created:null,baselines:null,unchanged:null,refused:null,
    confirmed:{processed:1,drafts_created:0,baselines:0,unchanged:0,refused:1},refusal_reasons:{publisher_date_receipt_unavailable:1}};
  expect(parseGenerationOutcome(raw)).toEqual(raw);
  render(<GenerationOutcomes metadata={{post_commit_generation:parseGenerationOutcome(raw)}} />);
  expect(screen.getByRole('list',{name:'Confirmed refusals before uncertainty'})).toBeInTheDocument();
  expect(screen.getByText(/Counters are unknown/)).toBeInTheDocument();
  expect(screen.queryByText(/Drafts created 0/)).not.toBeInTheDocument();
  expect(()=>parseGenerationOutcome({...raw,confirmed:undefined})).toThrow();
  expect(()=>parseGenerationOutcome({...raw,refusal_reasons:{publisher_date_receipt_unavailable:2}})).toThrow();
  expect(()=>parseGenerationOutcome({...raw,refusal_reasons:{environment_disabled:1}})).toThrow();
});

test('native report preview resolves extraction IDs from the selected completed job',async()=>{
  (generationApi.capabilities as jest.Mock).mockResolvedValue([{domain:'revenue_by_source',financial:false,reports:true,reason:'financial_adapter_unavailable'}]);
  (generationApi.preview as jest.Mock).mockResolvedValue({drafts_enabled:false,results:[{record_id:12,status:'baseline',reason:'first_observation',source_document_id:3}]});
  render(<QueryClientProvider client={new QueryClient()}><GenerationPreview /></QueryClientProvider>);
  await screen.findByRole('option',{name:'KRA revenue collections'});
  fireEvent.change(screen.getByLabelText('Source'),{target:{value:'revenue_by_source'}});
  fireEvent.change(screen.getByLabelText('Content to check'),{target:{value:'report'}});
  await screen.findByRole('option',{name:/job #42/});
  fireEvent.change(screen.getByLabelText('Completed live job'),{target:{value:'42'}});
  const button=screen.getByRole('button',{name:'2. Preview without saving'});
  await waitFor(()=>expect(button).toBeEnabled());fireEvent.click(button);
  await screen.findByRole('heading',{name:'Preview outcome'});
  expect(generationApi.preview).toHaveBeenCalledWith({domain:'revenue_by_source',record_ids:[12],ingestion_id:42,reports:true,backfill:false});
});
