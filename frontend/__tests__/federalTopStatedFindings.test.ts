/**
 * The homepage's audit summary query asks the backend for the rows it renders.
 *
 * #221 follow-up. PR #257 trims `/api/v1/audits/federal` to the 4 findings
 * `AuditReportsSection` lists before the response is dehydrated into the
 * homepage. But the trim ran after the download, so every client refetch of
 * the stale hydrated copy still pulled the whole list. OBSERVED on production:
 * 139,320 B gzip for a document 3,243 s old.
 *
 * The backend now answers `?top_findings=N` with the same selection
 * (`select_top_stated_findings` in backend/main.py). Both implementations are
 * pinned to one cases file, `fixtures/federalTopStatedFindings.cases.json`,
 * which `backend/tests/test_federal_audits_top_findings.py` also reads.
 */
import type { FederalAuditFinding, FederalAuditResponse } from '@/lib/api/audits';
import {
  federalAuditsHomeSummaryQuery,
  HOME_TOP_FINDINGS,
  trimFederalAuditsForHome,
} from '@/lib/react-query/useAudits';

import cases from './fixtures/federalTopStatedFindings.cases.json';

const mockGet = jest.fn();
jest.mock('@/lib/api/axios', () => {
  const client = { get: (...args: unknown[]) => mockGet(...args) };
  return { __esModule: true, apiClient: client, default: client };
});

const response = (findings: unknown[]): FederalAuditResponse =>
  ({
    total_findings: 813,
    by_severity: { critical: 1 },
    findings,
  }) as unknown as FederalAuditResponse;

beforeEach(() => mockGet.mockReset());

/* ── the shared contract ────────────────────────────────────────────── */

describe.each(cases.cases)('shared case: $name', ({ n, findings, expected_ids }) => {
  it('the homepage trim keeps exactly these rows, in this order', () => {
    // The trim is fixed at the section's size; every case is written for it.
    expect(n).toBe(HOME_TOP_FINDINGS);
    const trimmed = trimFederalAuditsForHome(response(findings));
    expect(trimmed.findings.map((f: FederalAuditFinding) => f.id)).toEqual(expected_ids);
  });

  it('trimming what the backend already trimmed changes nothing', () => {
    // The query trims the backend's answer again, so a backend that predates
    // `top_findings` (and ignores it, as FastAPI does unknown params) still
    // yields a small document. For that to be safe, the trim must be a no-op
    // on the backend's output: the rows the backend picked, in its order.
    const backendPicked = findings.filter((f) => expected_ids.includes(f.id));
    const ordered = expected_ids.map((id) => backendPicked.find((f) => f.id === id));
    const once = response(ordered);
    expect(trimFederalAuditsForHome(once)).toEqual(once);
  });
});

/* ── the request ────────────────────────────────────────────────────── */

describe('federalAuditsHomeSummaryQuery', () => {
  it(`asks the backend for the top ${HOME_TOP_FINDINGS} stated findings, not all of them`, async () => {
    mockGet.mockResolvedValue({ data: response([]) });
    await federalAuditsHomeSummaryQuery().queryFn();
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet.mock.calls[0][0]).toBe(`/audits/federal?top_findings=${HOME_TOP_FINDINGS}`);
  });

  it('still trims when the backend ignores the parameter and sends every finding', async () => {
    const full = cases.cases[0];
    mockGet.mockResolvedValue({ data: response(full.findings) });
    const data = await federalAuditsHomeSummaryQuery().queryFn();
    expect(data.findings.map((f: FederalAuditFinding) => f.id)).toEqual(full.expected_ids);
    expect(data.total_findings).toBe(813);
  });
});
