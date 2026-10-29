import api from '@/lib/api/axios';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SocialAutomation from '@/components/admin/social/SocialAutomation';
import GeneratedEvidence from '@/components/admin/social/GeneratedEvidence';
import { generationApi, decodeCapabilities, decodePreview, decodeEvidence } from '@/lib/api/socialGeneration';
const mockRun=jest.fn();
jest.mock('next/navigation',()=>({useSearchParams:()=>new URLSearchParams()}));
jest.mock('@/lib/api/axios',()=>({get:jest.fn()}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:'owned'}})}));
jest.mock('@/lib/auth/admin',()=>({useAdmin:()=>({isAdmin:true})}));
jest.mock('@/lib/hooks/useSocial',()=>({useSocialAccounts:()=>({data:[]}),useSocialMutation:()=>({run:mockRun,isPending:false,error:null})}));
jest.mock('@/lib/api/socialGeneration',()=>({...jest.requireActual('@/lib/api/socialGeneration'),generationApi:{capabilities:jest.fn(),preview:jest.fn(),sourceRecords:jest.fn(),controls:jest.fn(),rules:jest.fn(),decisions:jest.fn(),evidence:jest.fn()}}));
const capabilities=['national_budget','revenue_by_source','pending_bills'].map(domain=>({domain,financial:true,reports:true,reason:'qualified_native_cells_required'}));
function mount(node:React.ReactNode){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{node}</QueryClientProvider>);}
let mockDomain='revenue_by_source';
beforeEach(()=>{
  jest.clearAllMocks();
  (api.get as jest.Mock).mockImplementation(async(path,config)=>{const domain=config?.params?.domain??'revenue_by_source';const job={id:42,domain,status:'completed',dry_run:false,started_at:'2026-10-28T10:00:00Z',finished_at:'2026-10-28T10:01:00Z',duration_seconds:60,items_processed:1,items_created:1,items_updated:0,errors:[],error_count:0,diagnostics_redacted:true,created_at:'2026-10-28T10:00:00Z',metadata:{source_mode:'live'}};if(path.endsWith('/42'))return {data:{...job,domain:mockDomain}};return {data:{jobs:[job],total:1,page:1,page_size:20,has_more:false}};});
  (generationApi.sourceRecords as jest.Mock).mockImplementation(async selection=>({...selection,page_size:25,total:1,record_ids:[12],has_more:false}));
  (generationApi.capabilities as jest.Mock).mockResolvedValue([...capabilities,{domain:'audits',financial:false,reports:true,reason:'financial_adapter_unavailable'}]);
  (generationApi.controls as jest.Mock).mockResolvedValue({version:1,drafts_enabled:false,shadow_enabled:false,source_allowlist:[],targets:[]});
  (generationApi.rules as jest.Mock).mockResolvedValue({items:[]});
  (generationApi.decisions as jest.Mock).mockResolvedValue({items:[]});
  mockRun.mockResolvedValue([]);
});

test('capability and new-fact response reasons survive the actual decoders',()=>{
  expect(decodeCapabilities(capabilities)).toEqual(capabilities);
  expect(decodePreview({drafts_enabled:true,results:[{record_id:1,status:'eligible_change',reason:'new_fact_in_established_source',source_document_id:3}]}).results[0].status).toBe('eligible_change');
});

test.each(capabilities.map(c=>c.domain))('admin previews then explicitly detects selected financial source %s',async domain=>{
  mockDomain=domain;
  (generationApi.preview as jest.Mock).mockResolvedValue({drafts_enabled:true,results:[{record_id:12,status:'eligible_change',reason:'semantic_evidence_changed',source_document_id:3}]});
  mount(<SocialAutomation />);
  await screen.findByRole('option',{name:'County pending bills'});
  fireEvent.change(screen.getByLabelText('Source'),{target:{value:domain}});
  await screen.findByRole('option',{name:new RegExp('job #42')});
  fireEvent.change(screen.getByLabelText('Completed live job'),{target:{value:'42'}});
  const preview=screen.getByRole('button',{name:'2. Preview without saving'});
  await waitFor(()=>expect(preview).toBeEnabled());fireEvent.click(preview);
  await screen.findByRole('heading',{name:'Preview outcome'});
  expect(mockRun).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('3. Run explicit detection for this preview'));
  fireEvent.change(screen.getByLabelText('Reason for this manual action'),{target:{value:'Owned financial review'}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm manual detection'}));
  await waitFor(()=>expect(mockRun).toHaveBeenCalledWith('/generation/detect',expect.objectContaining({domain,record_ids:[12],ingestion_id:42,backfill:false,reason:'Owned financial review'}),expect.any(Function)));
});
test('unsupported audits cannot enter financial detection',async()=>{
  mount(<SocialAutomation />);await screen.findByRole('option',{name:'Audit reports'});
  fireEvent.change(screen.getByLabelText('Source'),{target:{value:'audits'}});
  expect(screen.getByRole('button',{name:'2. Preview without saving'})).toBeDisabled();
  expect(screen.queryByLabelText('Completed live job')).not.toBeInTheDocument();
});

const financial={native_domain:'revenue_by_source',record_id:12,report_record_id:23,authority_fingerprint:'a'.repeat(64),period_start:'2024-07-01',period_end:'2025-06-30',published_on:'2025-07-10'};
const fact={fact_id:'paye',entity:'Kenya',metric:'PAYE',period:'FY 2024/25',comparison_basis:'Published collections',value:'561.00',unit:'KES',scale:'billions',classification:'actual',document_url:'https://www.kra.go.ke/report',locator:'KRA annual article paragraph 2',document_checksum:'b'.repeat(64),publisher:'Kenya Revenue Authority',published_on:'2025-07-10',retrieved_at:'2026-10-28T10:00:00Z',verified_at:'2026-10-28T10:00:01Z'};
const evidence={post_id:'p1',revision_id:'r1',source_event_id:'e1',generator_metadata:{template_version:'factual-v1'},evidence:{evidence_version:42,source:{source_type:'kra',source_key:'kra:financial:revenue_by_source:paye',ingestion_id:'42',financial,facts:[fact]}}};
test('review exposes exact financial record and publisher evidence identities',async()=>{
  (generationApi.evidence as jest.Mock).mockResolvedValue(decodeEvidence(evidence));
  mount(<GeneratedEvidence postId='p1' revisionId='r1' expectedVersion={1} />);
  expect(await screen.findByRole('article',{name:'Financial source authority'})).toHaveTextContent('Source record 12 · Publisher report evidence 23');
  expect(screen.getByText(/561.00 KES \(billions\)/)).toBeInTheDocument();
  expect(screen.getByText(/Human approval remains required/)).toBeInTheDocument();
});

test.each([{record_id:true},{report_record_id:0},{published_on:null},{period_start:'2026-01-01'},{authority_fingerprint:'unbound'}])('malformed financial authority refuses (%j)',change=>{
  expect(()=>decodeEvidence({...evidence,evidence:{...evidence.evidence,source:{...evidence.evidence.source,financial:{...financial,...change}}}})).toThrow();
});
