import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import GenerationPreview from '@/components/admin/social/GenerationPreview';
import GenerationOutcomes from '@/components/admin/social/GenerationOutcomes';
import { generationApi, decodePreview, decodeCapabilities } from '@/lib/api/socialGeneration';
import { parseGenerationOutcome } from '@/lib/admin/ingestion';
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 'inert' } }) }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/api/socialGeneration', () => ({...jest.requireActual('@/lib/api/socialGeneration'),generationApi:{capabilities:jest.fn(),preview:jest.fn()}}));
const capability = {domain:'opendata',financial:false,reports:false,reason:'source_extracted_not_publication_qualified'};
beforeEach(() => {jest.clearAllMocks();(generationApi.capabilities as jest.Mock).mockResolvedValue([capability]);});

test('preview shows unsupported source without a mutation or invented availability',async()=>{
  (generationApi.preview as jest.Mock).mockResolvedValue({drafts_enabled:false,results:[{record_id:1,status:'unsupported_source',reason:capability.reason,source_document_id:null}]});
  render(<QueryClientProvider client={new QueryClient()}><GenerationPreview /></QueryClientProvider>);
  await screen.findByRole('option',{name:'opendata'});
  fireEvent.change(screen.getByLabelText('Source domain'),{target:{value:'opendata'}});
  fireEvent.change(screen.getByLabelText(/Preview record IDs/),{target:{value:'1'}});
  fireEvent.change(screen.getByLabelText('Preview ingestion job ID'),{target:{value:'42'}});
  fireEvent.click(screen.getByRole('button',{name:'Preview without saving'}));
  expect(await screen.findByRole('heading',{name:'Record 1 · unsupported source'})).toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Inspect ingestion job 42'})).toHaveAttribute('href','/admin/ingestion/42');
  expect(generationApi.preview).toHaveBeenCalledWith({domain:'opendata',record_ids:[1],ingestion_id:42,reports:true,backfill:false},expect.anything());
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
