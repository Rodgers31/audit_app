import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { LangProvider, useLang } from '@/lib/i18n/LangProvider';
import FigureEvidence from '@/components/evidence/FigureEvidence';
import OverviewTab from '@/app/counties/[id]/tabs/OverviewTab';
import EconomicContextStrip from '@/components/budget/EconomicContextStrip';
import ExecutionAuditLens from '@/components/budget/ExecutionAuditLens';
import { SummaryStrip } from '@/components/dashboard/HeroSection';
import profile from '../fixtures/figure-profile.json';
import fixture from '../fixtures/figure-qualifications.json';
import type { CountyComprehensive } from '@/types';

jest.mock('framer-motion', () => ({ motion: new Proxy({}, { get: () => ({ children, initial: _i, animate: _a, whileInView: _w, viewport: _v, transition: _t, ...props }: any) => <div {...props}>{children}</div> }) }));
jest.mock('@/components/dashboard/DebtExplainerModal', () => ({ __esModule: true, default: () => null }));
jest.mock('@/lib/react-query/useDebt', () => ({
  useDebtTimeline: () => ({ data: undefined }),
  useNationalDebtOverview: () => ({ data: { data: { total_outstanding: 0, gdp: 0, debt_to_gdp_ratio: 0, categories: {}, figure_qualifications: { loans: {}, gdp_data: {}, derived_ratio: { status: 'qualified', reason: 'published_imf_ratio_outside_seven_table_contract' } } } } }),
}));
jest.mock('@/lib/react-query/useFiscal', () => ({ useFiscalSummary: () => ({ data: undefined }) }));
function Controls() { const { setLang } = useLang(); return <>{(['en', 'sw', 'plain'] as const).map(lang => <button key={lang} onClick={() => setLang(lang)}>{lang}</button>)}</>; }
function subject(children: React.ReactNode) { render(<LangProvider><Controls />{children}</LangProvider>); }
beforeEach(() => localStorage.clear());
function evidence(label: string) {
  const el = document.querySelector(`[data-figure-evidence="${label}"]`);
  if (!(el instanceof HTMLElement)) throw new Error(`Missing original selector: ${label}`);
  return within(el);
}

it.each([
  ['sw', 'Pato la kaunti', 'Kiwango cha umaskini: 0%', 'Umaskini uliokithiri: Haijachapishwa', 'Ushahidi wa pato la kaunti', 'Ushahidi wa takwimu za bajeti ya kaunti'],
  ['plain', 'County economic output', 'People below the poverty line: 0%', 'Extreme poverty: Not published', 'Evidence for county economic output', 'Evidence for county budget observations'],
])('localizes real county economic facts and budget disclosure in %s without changing selectors or zero', (lang, title, zero, absent, gcp, budget) => {
  subject(<OverviewTab data={profile as unknown as CountyComprehensive} />);
  fireEvent.click(screen.getByRole('button', { name: lang }));
  expect(screen.getByRole('heading', { name: `${title} · 2024` })).toBeInTheDocument();
  expect(screen.getByText(zero)).toBeInTheDocument();
  expect(screen.getByText(absent)).toBeInTheDocument();
  expect(evidence('gross county product').getByText(new RegExp(gcp))).toBeInTheDocument();
  expect(evidence('county budget observations').getByText(new RegExp(budget))).toBeInTheDocument();
  expect(evidence('gross county product').getByRole('link', { hidden: true, name: lang === 'sw' ? 'Maelezo ya ushahidi wa takwimu' : 'Details for this observation' })).toHaveAttribute('href', `/sources/figures/gdp_data/${profile.economic_profile.latest_gcp.record_id}`);
  expect(within(screen.getByRole('heading', { name: `${title} · 2024` }).parentElement!).getByText('KES 0')).toBeInTheDocument();
});

it.each([
  ['sw', 'Ushahidi wa mgao na matumizi ya Health $&'],
  ['plain', 'Evidence for Health $& allocation and spending'],
])('localizes actual sector disclosure application copy in %s and keeps the raw sector label', (lang, expected) => {
  subject(<ExecutionAuditLens fiscalYear='FY2024/25' rows={[{ sector: 'Health $&', allocated: 100, spent: 0, unspent: 100, execution_rate: 0, qualifications: fixture.budget_lines.qualifications as any }]} />);
  fireEvent.click(screen.getByRole('button', { name: lang }));
  expect(evidence('Health $& allocation and expenditure').getByText(text => text.startsWith(expected))).toBeInTheDocument();
  expect(screen.getByTitle('Health $&')).toBeInTheDocument();
});

it.each([
  ['sw', 'Ushahidi wa mfumuko wa bei', 'Ushahidi wa bajeti / GDP'],
  ['plain', 'Evidence for price increases', 'Evidence for budget / GDP'],
])('localizes actual economic disclosure labels in %s while preserving numbers and original selectors', (lang, inflation, ratio) => {
  subject(<EconomicContextStrip ctx={{ gdp_billion_kes: 0, inflation_pct: 0, budget_to_gdp_pct: 0 }} />);
  fireEvent.click(screen.getByRole('button', { name: lang }));
  expect(evidence('Inflation').getByText(text => text.startsWith(inflation))).toBeInTheDocument();
  expect(evidence('Budget / GDP').getByText(text => text.startsWith(ratio))).toBeInTheDocument();
  expect(screen.getByText('KES 0B')).toBeInTheDocument();
});

it.each([
  ['sw', 'Ushahidi wa vipengele vya rejesta ya deni', 'Ushahidi wa takwimu za GDP', 'Ushahidi wa takwimu ya deni ikilinganishwa na GDP'],
  ['plain', 'Evidence for debt register inputs', 'Evidence for GDP observations', 'Evidence for debt compared with GDP'],
])('localizes actual dashboard debt disclosure labels in %s with original selectors and ratio unchanged', (lang, loans, gdp, ratio) => {
  subject(<SummaryStrip />);
  fireEvent.click(screen.getByRole('button', { name: lang }));
  expect(evidence('debt register operands').getByText(text => text.startsWith(loans))).toBeInTheDocument();
  expect(evidence('GDP observations').getByText(text => text.startsWith(gdp))).toBeInTheDocument();
  expect(evidence('debt-to-GDP observation').getByText(text => text.startsWith(ratio))).toBeInTheDocument();
  expect(screen.getByText('0.0%')).toBeInTheDocument();
  expect(evidence('debt-to-GDP observation').getByText(/published imf ratio outside seven table contract/)).toBeInTheDocument();
});

it.each([
  ['sw', 'Ushahidi wa takwimu za bajeti ya Nairobi $& {name}', 'Ushahidi wa debt register operands'],
  ['plain', 'Evidence for Nairobi $& {name} budget observations', 'Evidence for debt register operands'],
])('uses only explicit display keys in %s and retains literal entity names and original selector labels', (lang, translated, raw) => {
  subject(<><FigureEvidence label='Nairobi $& {name} budget observations' labelKey='evidence.label.county_named' labelValues={{ name: 'Nairobi $& {name}' }} /><FigureEvidence label='debt register operands' /></>);
  expect(evidence('Nairobi $& {name} budget observations').getByText(text => text.startsWith('Evidence for Nairobi $& {name} budget observations'))).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: lang }));
  expect(evidence('Nairobi $& {name} budget observations').getByText(text => text.startsWith(translated))).toBeInTheDocument();
  expect(evidence('debt register operands').getByText(text => text.startsWith(raw))).toBeInTheDocument();
});
