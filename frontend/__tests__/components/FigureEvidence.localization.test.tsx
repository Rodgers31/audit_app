import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import FigureEvidence from '@/components/evidence/FigureEvidence';
import FigureEvidencePage from '@/app/sources/figures/[table]/[id]/FigureEvidencePage';
import { LangProvider, useLang } from '@/lib/i18n/LangProvider';
import fixture from '../fixtures/figure-qualifications.json';
import type { FigureQualification } from '@/lib/evidence/qualification';
import api from '@/lib/api/axios';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock('@/components/layout/PageShell', () => ({ __esModule: true, default: ({ children, title, subtitle }: any) => <main><h1>{title}</h1><p>{subtitle}</p>{children}</main> }));

const original = fixture.budget_lines.qualifications.allocated_amount as FigureQualification;
function LanguageControls() {
  const { setLang } = useLang();
  return <>{(['en', 'sw', 'plain'] as const).map(lang => <button key={lang} onClick={() => setLang(lang)}>{lang}</button>)}</>;
}
function renderWithLanguage(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(<LangProvider><LanguageControls /><QueryClientProvider client={client}>{children}</QueryClientProvider></LangProvider>);
  return client;
}
beforeEach(() => { localStorage.clear(); jest.clearAllMocks(); });

it.each([
  ['sw', 'Ushahidi wa', 'Takwimu iliyothibitishwa', 'Fungua hati chanzo', 'Maelezo ya ushahidi wa takwimu', 'Baiti za chanzo: zimekaguliwa · Thamani: imelingana'],
  ['plain', 'Evidence for', 'Checked observation', 'Open the source document', 'Details for this observation', 'Source bytes: checked · Value: matched'],
])('switches shared evidence prose to %s without changing source facts or links', (lang, prefix, status, source, details, checks) => {
  renderWithLanguage(<FigureEvidence label='publisher $& label' qualifications={{ allocated_amount: original }} table='budget_lines' recordId={1} />);
  fireEvent.click(screen.getByRole('button', { name: lang }));
  expect(screen.getByText(`${prefix} publisher $& label · ${status}`)).toBeInTheDocument();
  expect(screen.getByText(checks)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: source, hidden: true })).toHaveAttribute('href', original.source_url);
  expect(screen.getByRole('link', { name: details, hidden: true })).toHaveAttribute('href', '/sources/figures/budget_lines/1');
  expect(screen.getByText(/Nairobi · FY2024\/25 · KES · actual/)).toBeInTheDocument();
  expect(screen.getByText(/Central Bank of Kenya/)).toBeInTheDocument();
  expect(screen.getByText(/retained source and observation matched/)).toBeInTheDocument();
  expect(screen.getByText(/json path \$\.observation/)).toBeInTheDocument();
  expect(screen.getByText(new RegExp(original.digest!))).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'en' }));
  expect(screen.getByText('allocated amount · Verified observation')).toBeInTheDocument();
});

it.each([
  ['sw', 'Ushahidi wa takwimu', 'Thamani iliyohifadhiwa: 0', 'Onyesha ushahidi upya'],
  ['plain', 'Evidence for this observation', 'Saved value: 0', 'Check evidence again'],
])('switches the exact detail page to %s and preserves zero and selector', async (lang, title, value, refresh) => {
  (api.get as jest.Mock).mockResolvedValue({ data: { value: '0', reason: null, qualifications: { allocated_amount: original } } });
  const client = renderWithLanguage(<FigureEvidencePage table='budget_lines' id='1' />);
  await screen.findByText('Stored value: 0');
  fireEvent.click(screen.getByRole('button', { name: lang }));
  expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
  expect(screen.getByText(value)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: refresh })).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledTimes(1);
  expect(api.get).toHaveBeenCalledWith('/provenance/verify/budget_lines', expect.objectContaining({ params: { record_id: '1' } }));
  client.clear();
});

it('switches invalid-reference and absent-evidence fallbacks to Kiswahili', () => {
  renderWithLanguage(<><FigureEvidencePage table='unknown' id='0' /><FigureEvidence label='raw label' /></>);
  fireEvent.click(screen.getByRole('button', { name: 'sw' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Rejeo hili la takwimu si halali.');
  expect(screen.getByText(/Ushahidi haupatikani/)).toBeInTheDocument();
  expect(screen.getByText(/Hakuna maelezo ya uthibitisho wa kipimo yaliyotolewa/)).toBeInTheDocument();
  expect(api.get).not.toHaveBeenCalled();
});

it('switches request failure and explicit retry to Kiswahili', async () => {
  (api.get as jest.Mock).mockRejectedValue(new Error('fixture offline'));
  const client = renderWithLanguage(<FigureEvidencePage table='budget_lines' id='1' />);
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', { name: 'sw' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Imeshindikana kupakia ushahidi wa takwimu. Hakuna matokeo ya uthibitisho yanayopatikana.');
  expect(screen.getByRole('button', { name: 'Jaribu tena' })).toBeInTheDocument();
  expect(screen.queryByText(/Verified observation/)).not.toBeInTheDocument();
  client.clear();
});

it.each([
  ['sw', ['Takwimu iliyothibitishwa', 'Rejeo lenye mipaka ya uthibitisho', 'Ushahidi haupatikani', 'Ushahidi unaokinzana', 'Imekadiriwa kwa modeli', 'Makadirio ya mbele', 'Ushahidi haujakamilika']],
  ['plain', ['Checked observation', 'Citation with verification limits', 'Evidence is not available', 'Evidence conflicts', 'Based on a model', 'Projection', 'Evidence is incomplete']],
])('keeps all evidence statuses distinct after switching to %s', (lang, expected) => {
  const statuses = ['verified', 'qualified', 'unavailable', 'conflicting', 'modelled', 'projected', 'verified'] as const;
  renderWithLanguage(<FigureEvidence label='raw cohort' qualifications={Object.fromEntries(statuses.map((status, index) => [`measure_${index}`, { ...original, status, value_checked: index !== 6 }]))} />);
  fireEvent.click(screen.getByRole('button', { name: lang }));
  expected.forEach((label, index) => expect(screen.getByText(`measure ${index} · ${label}`)).toBeInTheDocument());
  expect(screen.queryByText(/Verified observation/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Verified total/)).not.toBeInTheDocument();
});

it('localizes loading, missing publication and malformed-record fallbacks without inventing a value', async () => {
  let resolve: (value: unknown) => void = () => {};
  (api.get as jest.Mock).mockImplementation(() => new Promise(done => { resolve = done; }));
  const client = renderWithLanguage(<FigureEvidencePage table='budget_lines' id='1' />);
  fireEvent.click(screen.getByRole('button', { name: 'sw' }));
  expect(screen.getByRole('status')).toHaveTextContent('Inapakia ushahidi wa takwimu…');
  resolve({ data: { value: null, reason: null, qualifications: { unknown_measure: { status: 'verified', identity: null, reason: null, publisher: null, source_kind: 'unknown', document_bytes_checked: false, value_checked: false } } } });
  await screen.findByText('Thamani iliyohifadhiwa: Haijachapishwa');
  expect(screen.getByText('unknown measure · Ushahidi haupatikani')).toBeInTheDocument();
  expect(screen.getByText('Utambulisho wa takwimu haupatikani')).toBeInTheDocument();
  expect(screen.getByText('Sababu ya hali ya uthibitisho haipatikani')).toBeInTheDocument();
  expect(screen.getByText('Mchapishaji hapatikani · Chanzo cha aina haijulikani')).toBeInTheDocument();
  expect(screen.getByText('Baiti za chanzo: haijakaguliwa · Thamani: haijakaguliwa')).toBeInTheDocument();
  expect(screen.queryByText(/Verified observation/)).not.toBeInTheDocument();
  client.clear();
});
