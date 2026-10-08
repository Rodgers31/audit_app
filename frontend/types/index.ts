export interface AuditIssue {
  id: string;
  type: 'financial' | 'compliance' | 'performance' | 'governance';
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;
  amount?: number; // Monetary impact if applicable
  status: 'open' | 'resolved' | 'pending';
}

/** The Auditor-General's own words about an unfinished project, with the
 * report, paragraph and page they come from. Attached to a COB row only when
 * the heading shares distinctive name terms with it (`match`). */
export interface OagStalledFinding {
  speaker: 'Auditor-General';
  report: string | null;
  source_url: string;
  page: string | null;
  paragraph: number | string | null;
  fiscal_period: string | null;
  audit_year: number | null;
  heading: string | null;
  text: string;
  audit_id: number;
  match?: { shared_terms: string[]; score: number };
}

/** One row of a county's "Stalled Projects" table in the Controller of
 * Budget's County Budget Implementation Review Report, as reported by the
 * county treasury (or assembly) to COB. The backend publishes a row only when
 * it carries source_url, source_page, as_of and reported_by
 * (backend/services/stalled_projects.py). Figures COB left blank ("-") or
 * that could not be read against the table's own header are null, never 0;
 * `cells` holds every cell exactly as printed. */
export interface StalledProject {
  project_name: string | null;
  row_no: string | null;
  sector?: string | null;
  location?: string | null;
  completion_pct: number | null;
  reason?: string | null;
  action?: string | null;
  group?: string | null;
  estimated_value_kes: number | null;
  amount_paid_kes: number | null;
  cells: Record<string, string>;
  flags: string[];
  source_url: string;
  source_page: number;
  as_of: string;
  reported_by: string;
  publisher: string;
  table_caption: string | null;
  table_no: string | null;
  oag_corroboration: OagStalledFinding[];
}

export interface AuditFinding {
  id: number;
  audited_entity_name?: string | null;
  source_url?: string | null;
  page_ref?: string | null;
  finding: string;
  severity: 'info' | 'warning' | 'critical';
  category: string;
  status: string;
  amount_involved: number;
  amount_label: string;
  audit_year?: string;
  reference?: string;
  recommendation?: string;
}

/** Each measure keeps the source table's basis and fiscal period. */
export interface CountyRevenue {
  total_revenue: number | null;
  total_revenue_target: number | null;
  equitable_share: number | null;
  equitable_share_target: number | null;
  additional_allocations: number | null;
  local_revenue: number | null;
  own_source_target: number | null;
  local_revenue_basis?: 'cash_receipts' | 'summary_table_actual_realised' | null;
  total_revenue_basis?: 'cash_receipts_including_opening_balance' | null;
  summary_table_own_source_revenue?: number | null;
  own_source_disagreement?: { summary_table: number; county_revenue_table: number } | null;
  streams: Array<{ stream: string; target: number | null; actual: number }>;
  fiscal_year: string | null;
  source: string | null;
  sources?: Array<{ id: number | null; url: string | null; page_ref: string | null; measure: string }>;
  total_revenue_absent_reason: string | null;
  total_revenue_absence_source?: {
    id: number; url: string | null; pages: number[];
    publisher: string | null; title: string | null;
    basis: 'cash_receipts_including_opening_balance'; unit: 'KES';
    artifact_sha256: string | null;
  } | null;
}

/** Where an official's name came from. */
export interface OfficialSource {
  publisher: string | null;
  source_url: string;
  fetched_at: string | null;
}

export type FinancialHealthComponentName =
  | 'budget_absorption'
  | 'own_source_revenue'
  | 'pending_bills'
  | 'audit_opinion';

/** The site's index terms, as computed for this county. Shares use the
 * effective denominator of available terms, never unavailable nominal weights. */
export interface CountyFinancialHealth {
  score: number | null;
  grade: string | null;
  weighting: 'audit_opinion_weighted';
  weights: Record<FinancialHealthComponentName, number>;
  effective_weight: number;
  minimum_components: number;
  absent_reason: 'fewer_than_two_components' | null;
  available_inputs: FinancialHealthComponentName[];
  unavailable_inputs: Array<{ name: FinancialHealthComponentName; reason: string }>;
  components: Array<{
    name: FinancialHealthComponentName;
    score: number;
    observed: number | string;
    basis: string;
    weight: number;
    share_pct: number;
    source_period: string | null;
    source_url: string | null;
    as_at: string | null;
    measurement_basis?: 'cash_receipts' | 'summary_table_actual_realised' | null;
    source_periods?: string[];
    source_dates?: string[];
    source_warning?: 'mixed_pending_periods' | 'mixed_pending_sources' | null;
  }>;
}

import type { QualificationRows, Qualifications } from '@/lib/evidence/qualification';

export interface CountyComprehensive {
  id: string;
  name: string;
  slug: string;
  coordinates: [number, number];
  /** null unless a publisher supplied it (the Council of Governors); see
   *  `officials_source`. A name nobody can check is withheld (#231). */
  governor?: string | null;
  deputy_governor?: string | null;
  officials_source?: {
    governor: OfficialSource | null;
    deputy_governor: OfficialSource | null;
  };
  demographics: {
    /** null when the county has no PopulationData row. The endpoint used to
     *  fall back to bootstrap's un-sourced copy in entity.meta, and to 0 when
     *  even that was absent. */
    population: number | null;
    population_year?: number;
    male_population?: number;
    female_population?: number;
    urban_population?: number;
    rural_population?: number;
    population_density?: number;
  };
  economic_profile: {
    latest_gcp?: { id: number; record_id: number; entity_id: number; year: number; quarter: string | null; gdp_value: number | null; gdp_growth_rate: number | null; currency: string; qualifications: Qualifications } | null;
    latest_poverty?: { id: number; record_id: number; entity_id: number; year: number; poverty_headcount_rate: number | null; extreme_poverty_rate: number | null; gini_coefficient: number | null; qualifications: Qualifications } | null;
    // Null: nobody publishes a county's "economic base". The fixture said
    // "agriculture" for 42 of the 47 — a judgement, not a figure. KNBS's
    // Gross County Product would support one; the fixture did not.
    economic_base: string | null;
    // The Auditor-General's findings for THIS county. They used to be four
    // strings identical across all 47.
    major_issues: string[];
    major_issues_source?: string | null;
  };
  budget: {
    figure_qualifications?: QualificationRows;
    total_allocated: number;
    total_spent: number;
    utilization_rate: number;
    development_budget: number;
    recurrent_budget: number;
    /** null when the population is unknown — the share of a budget cannot be
     *  computed without a denominator, and 0 is not that share. */
    per_capita_budget: number | null;
    sector_breakdown: Record<string, { allocated: number; spent: number }>;
    /** Fiscal year these budget numbers refer to (e.g. "FY2024/25").
     * Set by the backend to the latest FY with actual execution data,
     * not necessarily the current FY. */
    fiscal_year?: string | null;
    /** Which rows produced the figures above — see BudgetSource. Drives the
     *  page's provenance note, so a CBIRR period stops being described to the
     *  reader as a CRA model. */
    source?: BudgetSource;
  };
  revenue: CountyRevenue;
  debt: {
    total_debt: number | null;
    total_debt_absent_reason?: string | null;
    debt_currency?: 'KES' | null;
    debt_accounting_basis?: 'selected_instrument_outstanding';
    debt_basis?: 'actual' | null;
    debt_as_at?: string | null;
    debt_coverage?: 'selected_eligible_instruments_only';
    /** null when no publication states this county's pending bills — Nandi
     *  reported none to the Controller of Budget at 30 June 2026. */
    pending_bills: number | null;
    /** ISO date the figure is a stock on; null exactly when the figure is. */
    pending_bills_as_at?: string | null;
    pending_bills_source?: {
      publisher: string;
      title: string;
      table: string | null;
      url: string | null;
    } | null;
    /** What the report says about the figure, as codes the page words. */
    pending_bills_notes?: Array<{ code: string } & Record<string, unknown>>;
    /** Why there is NO figure, when the report says why; null otherwise. */
    pending_bills_absence?: {
      reason: 'not_reported' | 'withheld';
      as_at: string;
      table: string | null;
    } | null;
    debt_to_budget_ratio: number | null;
    debt_to_budget_ratio_absent_reason?: string | null;
    /** null when the population or the debt is unknown. */
    per_capita_debt: number | null;
    breakdown: Array<{
      lender: string;
      category: string;
      principal: number | null;
      outstanding: number | null;
      interest_rate?: number | null;
      currency?: string;
      source_document_id?: number;
      page_ref?: string | null;
      basis?: string | null;
      provenance?: unknown;
      absent_reasons?: Record<string, string>;
    }>;
  };
  audit: {
    status: string;
    grade: string | null;
    health_score: number | null;
    findings_count: number;
    /** null when no publishable finding carries an amount. NOT 0 — the API
     *  distinguishes "nothing was flagged" from "we cannot source a figure",
     *  and collapsing them here re-creates the manufactured zero the backend
     *  removed (review, PR #135). */
    total_amount_involved: number | null;
    by_severity: Record<string, number>;
    findings: AuditFinding[];
  };
  /** Findings the Auditor-General titled "Unaccounted …" / "Loss of Funds"
   *  (issue #233). Never a money total: `total_amount` is always null. */
  missing_funds: {
    basis?: 'oag_finding_title';
    total_amount: null;
    total_amount_reason?: 'no_amount_extracted';
    cases_count: number;
    cases: UnaccountedCase[];
    reason?: string | null;
    withheld?: { count: number; by_reason: Record<string, number> };
  };
  stalled_projects: {
    /** null when no evidence-backed row exists — unknown, not zero. */
    count: number | null;
    total_contracted_value: number | null;
    /** How many rows the total covers; rows with no printed figure are left out. */
    total_contracted_value_rows: number;
    total_amount_paid: number | null;
    total_amount_paid_rows: number;
    projects: StalledProject[];
    reason: 'no_evidence_backed_source' | 'no_table_in_edition' | 'table_unreadable' | null;
    source: {
      publisher: string;
      title: string | null;
      fiscal_year: string | null;
      period: string | null;
      published: string | null;
      as_of: string | null;
      url: string;
      wpdmdl: number | null;
      sha256: string | null;
      reported_by: string;
    } | null;
    /** COB's own words about this county: its summary sentence, a statement
     * that it reported nothing, and its line in Table 2.6 — verbatim. */
    cob_statements: Record<string, unknown> | null;
    reconciliation: {
      status: 'agrees' | 'agrees_with_gaps' | 'disagrees' | 'unverifiable';
      checks: { check: string; rows: number | null; cob: number | null; cob_source: string; agrees: boolean | null }[];
      [key: string]: unknown;
    } | null;
    withheld_fields: { field: string; why: string; detail: string }[];
    oag_findings: OagStalledFinding[];
    withheld: { count: number; by_reason: Record<string, number> };
  };
  financial_summary: {
    health_score: number | null;
    grade: string | null;
    budget_execution_rate: number;
    pending_bills_ratio: number | null;
    debt_sustainability: string;
  };
  /** Optional during a rolling deploy or while an older API cache expires. */
  financial_health?: CountyFinancialHealth;
  /** Per-FY health scores, oldest → newest. Only periods with actual
   * execution are included; allocated-only years are skipped. */
  health_history?: Array<{ fy: string; score: number; grade: string }>;
  health_history_absent_reason?: 'dated_health_components_unavailable';
  /** Completed periods of budget execution; this is not a health score. */
  budget_execution_history?: Array<{
    fiscal_period: { id: number; label: string; start_date: string; end_date: string };
    total_allocation: number | null;
    total_spent: number | null;
    execution_rate: number | null;
    accounting_basis: string | null;
    currency: string | null;
    sources: Array<{
      id: number | null;
      title: string | null;
      publisher: string | null;
      url: string | null;
      page_refs: string[];
    }>;
    absent_reasons: Record<string, string>;
    budget_lines_count: number;
  }>;
  data_sources: Record<string, string>;
}

/**
 * Where a county's headline budget figure came from, as reported by the API.
 *
 * `cob_cbirr` — the Controller of Budget's own Total/Development/Recurrent
 * aggregates, read from the County Budget Implementation Review Report.
 * `cra_model` — a CRA equitable-share projection period: modelled.
 * `mixed` — a figure POOLED across counties that came from both kinds of row,
 * which is what the national money-flow aggregate is whenever the CBIRR has
 * reached only part of the country. A single county is never `mixed`.
 * `null`/absent — no budget was published, so there is no source to name.
 *
 * The standing provenance note on the county pages is rendered from this.
 */
export type BudgetSource = 'cob_cbirr' | 'cra_model' | 'mixed' | null;

export interface County {
  figureQualifications?: { budget_lines?: QualificationRows; gdp_data?: QualificationRows };
  id: string;
  name: string;
  code?: string;
  coordinates?: [number, number]; // [longitude, latitude]
  // Money figures are absent-or-published, never zero-filled. `undefined`
  // means the API withheld the figure — render "—" and withhold any claim
  // derived from it rather than substituting 0, which states that a county
  // was allocated nothing / owes nothing / received nothing.
  budget?: number;
  debt?: number;
  // Null when no KNBS census row exists — same rule, and the same field, as
  // CountyComprehensive.demographics.population above. The list endpoint
  // published 0 for those counties, and every consumer read it as a real
  // count: the ranking table sorted them smallest, the compare page divided
  // a budget by it.
  population: number | null;
  // Backend actual fields
  budget_2025: number;
  financial_health_score?: number; // absent when fewer than two components can be computed
  audit_rating: string; // Real OAG rating — empty string until audits pipeline provides one
  fiscal_grade?: string; // From the financial-health composite — NOT an audit opinion; absent when it cannot be computed
  // Legacy frontend fields for compatibility
  auditStatus?: 'clean' | 'qualified' | 'adverse' | 'disclaimer' | 'pending';
  lastAuditDate?: string;
  gdp?: number;
  // Enhanced financial data
  moneyReceived?: number; // Total grants/transfers received — undefined when withheld
  budgetUtilization?: number; // Percentage of budget used
  auditIssues?: AuditIssue[];
  revenueCollection?: number; // Measure described by revenue.local_revenue_basis
  revenue?: CountyRevenue;
  pendingBills?: number; // Outstanding payments
  developmentBudget?: number; // Capital/development budget
  recurrentBudget?: number; // Operational budget
  // Provenance of `budget` above — the list and compare pages carry the same
  // provenance note the detail page does, and need the same answer.
  budgetSource?: BudgetSource;
  // Additional fields for county explorer
  governor?: string; // Governor name
  totalBudget?: number; // Total budget (computed from dev + recurrent)
  totalDebt?: number; // Selected eligible instrument outstanding, including reported zero
  totalDebtAbsentReason?: string | null;
  debtCurrency?: string | null;
  debtAccountingBasis?: string;
  debtBasis?: 'actual' | null;
  debtAsAt?: string | null;
  debtCoverage?: string;
  education?: number; // Education spending
  health?: number; // Health spending
  infrastructure?: number; // Infrastructure spending
}

export interface NationalData {
  totalDebt: number;
  gdp: number;
  debtToGdpRatio: number;
  lastUpdated: string;
  debtBreakdown: {
    domestic: number;
    external: number;
  };
}

export interface AuditStatus {
  status: 'clean' | 'qualified' | 'adverse' | 'disclaimer' | 'pending';
  label: string;
  color: string;
  icon: string;
}

export interface FederalProject {
  id: string;
  name: string;
  ministry: string;
  budget: number;
  completion: number; // percentage
  auditStatus: 'clean' | 'qualified' | 'adverse' | 'disclaimer' | 'pending';
  keyIssues: string[];
  citizenImpact: string;
  timeframe: string;
}

export interface Ministry {
  id: string;
  name: string;
  budget: number;
  auditStatus: 'clean' | 'qualified' | 'adverse' | 'disclaimer' | 'pending';
  majorProjects: string[];
  keyIssues: string[];
  citizenServices: string[];
}

export interface GradeFactor {
  impact: 'positive' | 'minor' | 'moderate' | 'major';
  label: string;
  detail: string;
  /** Point delta applied to the 100-point accountability score.
   * Negative for penalties, 0 for neutral/positive factors. */
  points?: number;
}

export interface AccountabilityScorecard {
  county_id: string;
  county_name: string;
  audit_opinion_history: Array<{ year: number; opinion: string }>;
  /** Per-year audit findings severity score (0-100, higher = fewer/less-severe findings).
   * Used for the hero AUDIT trend sparkline. Separate from opinion_history so we
   * never conflate "critical findings" with "adverse opinion" in scoring. */
  audit_severity_history?: Array<{
    year: number;
    score: number;
    info: number;
    warning: number;
    critical: number;
  }>;
  /** null when no publishable finding carries an amount — never 0, which
   *  would read as "the Auditor-General flagged nothing". */
  total_flagged_amount: number | null;
  /** Why total_flagged_amount is null: awaiting_sourced_data | no_findings_recorded. */
  total_flagged_amount_reason?: string | null;
  /** Findings held back because their source document has no openable URL. */
  withheld?: { count: number; reason: string | null };
  /** 'publishable_findings' | 'no_publishable_findings' | 'no_findings_recorded'
   *  — whether the grade below rests on any evidence at all. */
  evidence_basis?: string;
  /** Why there is no grade: awaiting_sourced_data | not_yet_audited_in_this_dataset. */
  accountability_reason?: string | null;
  /** Total raw findings count (may not equal sum of critical+warning if some have no severity). */
  total_findings?: number;
  critical_findings?: number;
  warning_findings?: number;
  recurring_findings_count: number;
  unresolved_findings_count: number;
  absorption_rate: number | null;
  /** Total flagged amount as % of current-FY budget. */
  flagged_pct_of_budget?: number | null;
  /** null when there is no publishable finding to grade — NOT 'F'. */
  accountability_grade: string | null; // A/B/C/D/F
  /** Derived from a 100-point scale: A≥85, B≥70, C≥55, D≥40, else F. */
  accountability_score?: number | null;
  /** Ordered list of penalty/positive factors that drove the score. */
  grade_factors?: GradeFactor[];
  peer_comparison: {
    region: string;
    region_avg_flagged_amount: number | null;
    region_avg_grade: string | null;
    /** null when the county has no census row — a county with no counted
     *  population has no population bracket, and cannot be compared against
     *  one. See AccountabilityTab's `|| bracket_fallback` rung. */
    population_bracket: string | null;
    population_bracket_avg: number | null;
  };
}

export interface AuditAmountCoverage {
  status: 'complete' | 'partial' | 'unavailable';
  reason: string | null;
  total_findings: number;
  findings_with_amount: number;
  findings_without_amount: number;
  findings_with_invalid_amount: number;
  withheld_findings: number;
}

export interface MoneyFlowStage {
  amount_coverage?: AuditAmountCoverage;
  stage: string;
  label: string;
  amount: number | null;
  /** Caption printed under the figure. On the Allocated stage this is derived
   *  from `MoneyFlowData.budget_source`, so it names the rows the amount was
   *  actually summed from. Absent when nothing was published — an unpublished
   *  figure has no source. */
  source?: string;
  source_doc?: string;
  gap_from_prev?: number | null;
  gap_label?: string;
  data_unavailable?: boolean;
}

export interface MoneyFlowData {
  audit_amount_coverage?: AuditAmountCoverage;
  county_id: number | null;
  county_name: string;
  fiscal_year: string;
  stages: MoneyFlowStage[];
  total_waste_estimate: number | null;
  efficiency_score: number | null;
  county_count?: number;
  /** Official CoB publication that produced these figures. Surfaced
   * in the UI so every number is traceable to a government source. */
  source_document_title?: string | null;
  source_document_url?: string | null;
  /** Which rows produced the Allocated stage's amount — see BudgetSource.
   *  The stage's own `source` caption is the API's prose for this code; keep
   *  any UI that captions the stage switching on this rather than asserting a
   *  source of its own, or the caption drifts from the figure again. */
  budget_source?: BudgetSource;
  /** Procurement encumbrances — not a waterfall stage but shown as a
   * supplementary line under "Spent" when present, so readers can see
   * how much of the budget is committed to contracts vs fully free. */
  committed_amount?: number | null;
}

export interface ChartData {
  name: string;
  value: number;
  color?: string;
}

export interface TooltipData {
  content: string;
  position: {
    x: number;
    y: number;
  };
  visible: boolean;
}

/** One finding from backend/services/audit_derived.py::derive_unaccounted_cases. */
export interface UnaccountedCase {
  finding_id: number;
  entity: string | null;
  entity_id?: number;
  county_name?: string | null;
  county_slug?: string | null;
  entity_type: string | null;
  /** The Auditor-General's own heading for the finding. */
  title: string;
  /** The finding's text after its title, in the report's words. May be empty
   *  when the extractor captured only the heading. */
  excerpt: string;
  /** The report section it sits under, e.g. "Basis for Adverse Opinion". */
  heading: string | null;
  fiscal_year: string | null;
  page_ref: string | null;
  source: {
    document_id: number;
    title: string | null;
    publisher: string | null;
    url: string | null;
    page_url: string | null;
  };
}
