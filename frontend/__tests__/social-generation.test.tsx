import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SocialAutomation from '@/components/admin/social/SocialAutomation';
import GeneratedEvidence from '@/components/admin/social/GeneratedEvidence';
import { decodeDraftControls, decodeRule, decodeDecision, decodeEvidence, describeShadowReason, generationApi } from '@/lib/api/socialGeneration';
const mockRun = jest.fn();
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: 'fixture-actor' } }) }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/hooks/useSocial', () => ({ useSocialAccounts: () => ({ data: [{ id: 'account-1', platform: 'facebook', display_name: 'Fixture Page' }] }), useSocialMutation: () => ({ run: mockRun, isPending: false, error: null }) }));
jest.mock('@/lib/api/socialGeneration', () => ({ ...jest.requireActual('@/lib/api/socialGeneration'), generationApi: { capabilities: jest.fn().mockResolvedValue([]), preview: jest.fn(), controls: jest.fn(), rules: jest.fn(), decisions: jest.fn(), evidence: jest.fn() } }));
function mount(node: React.ReactNode) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{node}</QueryClientProvider>); }
beforeEach(() => { jest.clearAllMocks(); (generationApi.controls as jest.Mock).mockResolvedValue({ version: 1, drafts_enabled: false, shadow_enabled: false, source_allowlist: [], targets: [] }); (generationApi.rules as jest.Mock).mockResolvedValue({ items: [], total: 0, page: 1, has_more: false }); (generationApi.decisions as jest.Mock).mockResolvedValue({ items: [], total: 0, page: 1, has_more: false }); });
test('safe controls are distinct and begin off; no live automation toggle exists', async () => { mount(<SocialAutomation />); expect(await screen.findByText(/Draft generation: off/)).toBeInTheDocument(); expect(screen.getByText(/Automatic approval, scheduling and publishing default to OFF/)).toBeInTheDocument(); fireEvent.click(screen.getByRole('button', { name: 'Edit draft & shadow controls' })); expect(screen.getByRole('checkbox', { name: /Generate drafts for selected sources/ })).not.toBeChecked(); expect(screen.getByRole('checkbox', { name: /Permit explicit shadow evaluation/ })).not.toBeChecked(); expect(screen.queryByRole('checkbox', { name: /Publish automatically/ })).not.toBeInTheDocument(); });
test('source review shows exact decimals, classification, period and source locator', async () => { (generationApi.evidence as jest.Mock).mockResolvedValue({ post_id: 'p1', revision_id: 'r1', source_event_id: 'e1', generator_metadata: { template_version: 'factual-v1' }, evidence: { evidence_version: 2, source: { source_type: 'cob', source_key: 'county:1', ingestion_id: 'job:42', facts: [{ fact_id: 'f1', entity: 'County fixture', metric: 'Budget', value: '123.4500', scale: 'millions', unit: 'KES', classification: 'projected', period: 'FY2025/26', comparison_basis: 'County total', publisher: 'COB', published_on: '2026-01-01', locator: 'page 12, table 4', document_url: 'https://example.gov/report.pdf', document_checksum: 'a'.repeat(64), retrieved_at: '2026-10-15', verified_at: '2026-10-15' }] } } }); mount(<GeneratedEvidence postId='p1' revisionId='r1' expectedVersion={1} />); expect(await screen.findByText('123.4500 KES (millions)')).toBeInTheDocument(); expect(screen.getByText('FY2025/26 · projected')).toBeInTheDocument(); expect(screen.getByText(/page 12, table 4/)).toBeInTheDocument(); expect(screen.getByRole('link', { name: 'Open supporting source' })).toHaveAttribute('href', 'https://example.gov/report.pdf'); expect(screen.getByText(/Human approval remains required/)).toBeInTheDocument(); });
test('response contracts reject false success and malformed controls', () => { for (const payload of [null, {}, { version: 1, drafts_enabled: 'false', shadow_enabled: false, source_allowlist: [], targets: [] }]) expect(() => decodeDraftControls(payload)).toThrow(); expect(() => decodeRule({ id: 'x', version: 1, definition: { mode: 'live' } })).toThrow(); expect(() => decodeDecision({ outcome: 'published' })).toThrow(); });

test('shadow decisions explain the reason without asserting live approval', () => { expect(describeShadowReason('ALL_SHADOW_GATES_PASSED_HUMAN_APPROVAL_REQUIRED')).toMatch('Human approval is still required'); expect(describeShadowReason('SOURCE_SUPERSEDED')).toMatch('newer source event'); expect(describeShadowReason('FUTURE_REASON')).toBe('Unrecognized decision reason: FUTURE_REASON'); });

const report = { source_record_id: 1, authority_fingerprint: 'a'.repeat(64), entity_id: 1, entity: 'Nairobi City County', period: 'FY2025/26', period_start: '2025-07-01', period_end: '2026-06-30', source_document_id: 12,
  document_url: 'https://cob.go.ke/owned-report.pdf', document_checksum: 'a'.repeat(64), publisher: 'Controller of Budget', published_on: '2026-07-01',
  retrieved_at: '2026-10-17T00:00:00Z', verified_at: '2026-10-17T00:00:01Z', canonical_url: 'https://www.auditgava.com/counties/1',
  locator: 'PDF page 1; Publication date: 2026-07-01', publication_extraction_id: 23, qualification_extraction_id: 24 };
const reportEvidence = { post_id: 'p1', revision_id: 'r1', source_event_id: 'e1', generator_metadata: { template_version: 'report-availability-v1' },
  evidence: { evidence_version: 2, source: { source_type: 'cob', source_key: 'cob:county:1:reports', ingestion_id: '42', facts: [], report } } };

test('neutral report review shows retained identity and date proof without a financial stand-in', async () => {
  (generationApi.evidence as jest.Mock).mockResolvedValue(decodeEvidence(reportEvidence));
  mount(<GeneratedEvidence postId='p1' revisionId='r1' expectedVersion={1} />);
  expect(await screen.findByRole('article', { name: 'Neutral report evidence' })).toHaveTextContent('Controller of Budget report · Nairobi City County');
  expect(screen.getByText(/Publication evidence 23 · Qualified scope evidence 24/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open publisher report' })).toHaveAttribute('href', report.document_url);
  expect(screen.queryByText(/1 report|KES/)).not.toBeInTheDocument();
});

test.each([0, false, null, '23'])('neutral evidence decoder refuses invalid date proof identity %p', value => {
  expect(() => decodeEvidence({ ...reportEvidence, evidence: { ...reportEvidence.evidence, source: { ...reportEvidence.evidence.source, report: { ...report, publication_extraction_id: value } } } })).toThrow();
});

test('neutral evidence decoder refuses mixed financial and report claims', () => {
  expect(() => decodeEvidence({ ...reportEvidence, evidence: { source: { ...reportEvidence.evidence.source, facts: [{}] } } })).toThrow();
});


test.each(['', 'a'.repeat(63), 'g'.repeat(64), null, false])('neutral evidence decoder refuses malformed current source authority %p', value => {
  expect(() => decodeEvidence({ ...reportEvidence, evidence: { ...reportEvidence.evidence, source: { ...reportEvidence.evidence.source, report: { ...report, authority_fingerprint: value } } } })).toThrow();
});

const catalogue = { ...report, native_domain: 'revenue_by_source', entity: 'Kenya annual revenue performance',
  publisher: 'Kenya Revenue Authority', document_url: 'https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026',
  canonical_url: 'https://www.auditgava.com/budget', published_on: null, evidence_kind: 'publisher_catalogue',
  catalogued_on: '2026-07-08', catalogue_url: 'https://www.kra.go.ke/component/search/?searchphrase=all&searchword=KRA+performance' };
function catalogueEvidence(changes = {}) { return { ...reportEvidence, evidence: { ...reportEvidence.evidence,
  source: { ...reportEvidence.evidence.source, source_type: 'kra', report: { ...catalogue, ...changes } } } }; }

test('catalogue evidence labels its own date and unknown publication; human review required', async () => {
  (generationApi.evidence as jest.Mock).mockResolvedValue(decodeEvidence(catalogueEvidence()));
  mount(<GeneratedEvidence postId='p1' revisionId='r1' expectedVersion={1} />);
  expect(await screen.findByText(/Official KRA catalogue entry date: 2026-07-08/)).toHaveTextContent('Report publication date is not stated.');
  expect(screen.getByText(/Catalogue evidence only. Human review required/)).toBeInTheDocument();
  expect(screen.getByText(/Catalogue availability evidence 23/)).toBeInTheDocument();
  expect(screen.queryByText(/Publisher publication date:/)).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open official catalogue entry' })).toHaveAttribute('href', catalogue.catalogue_url);
  expect(describeShadowReason('CATALOGUE_HUMAN_REVIEW_REQUIRED')).toContain('automatic approval is unavailable');
});

test.each([{ published_on: '2026-07-08' }, { catalogued_on: null }, { catalogued_on: 'July 2026' },
  { evidence_kind: 'publication' }, { native_domain: 'national_budget' }, { publisher: 'Other' },
  { catalogue_url: 'https://evil.invalid' }, { evidence_kind: undefined }])('decoder refuses malformed catalogue distinctions %p', changes => {
  expect(() => decodeEvidence(catalogueEvidence(changes))).toThrow();
});

test.each(['2026-02-30','2026-13-01','2026-00-08','2025-02-29','0000-01-01'])('catalogue dates must be real calendar days %s', value => {
  expect(() => decodeEvidence(catalogueEvidence({catalogued_on:value}))).toThrow();
});
