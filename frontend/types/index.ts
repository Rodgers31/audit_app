export interface AuditIssue {
  id: string;
  type: 'financial' | 'compliance' | 'performance' | 'governance';
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;
  amount?: number; // Monetary impact if applicable
  status: 'open' | 'resolved' | 'pending';
}

export interface StalledProject {
  project_name: string;
  sector: string;
  contracted_amount: number;
  amount_paid: number;
  completion_pct: number;
  start_year: number;
  expected_completion: number;
  status: 'stalled' | 'delayed';
  reason: string;
  oag_reference: string;
}

export interface AuditFinding {
  id: number;
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

export interface CountyComprehensive {
  id: string;
  name: string;
  slug: string;
  coordinates: [number, number];
  governor?: string;
  demographics: {
    population: number;
    population_year?: number;
    male_population?: number;
    female_population?: number;
    urban_population?: number;
    rural_population?: number;
    population_density?: number;
  };
  economic_profile: {
    county_type: string;
    economic_base: string;
    infrastructure_level: string;
    revenue_potential: string;
    major_issues: string[];
  };
  budget: {
    total_allocated: number;
    total_spent: number;
    utilization_rate: number;
    development_budget: number;
    recurrent_budget: number;
    per_capita_budget: number;
    sector_breakdown: Record<string, { allocated: number; spent: number }>;
  };
  revenue: {
    total_revenue: number;
    local_revenue: number;
    equitable_share: number;
  };
  debt: {
    total_debt: number;
    pending_bills: number;
    debt_to_budget_ratio: number;
    per_capita_debt: number;
    breakdown: Array<{
      lender: string;
      category: string;
      principal: number;
      outstanding: number;
      interest_rate?: number;
    }>;
  };
  audit: {
    status: string;
    grade: string;
    health_score: number;
    findings_count: number;
    total_amount_involved: number;
    by_severity: Record<string, number>;
    findings: AuditFinding[];
  };
  missing_funds: {
    total_amount: number;
    cases_count: number;
    cases: any[];
  };
  stalled_projects: {
    count: number;
    total_contracted_value: number;
    total_amount_paid: number;
    projects: StalledProject[];
  };
  financial_summary: {
    health_score: number;
    grade: string;
    budget_execution_rate: number;
    pending_bills_ratio: number;
    debt_sustainability: string;
  };
  data_sources: Record<string, string>;
}

export interface County {
  id: string;
  name: string;
  code?: string;
  coordinates?: [number, number]; // [longitude, latitude]
  budget?: number;
  debt?: number;
  population: number;
  // Backend actual fields
  budget_2025: number;
  financial_health_score: number;
  audit_rating: string; // 'A-', 'B', 'B+', etc.
  // Legacy frontend fields for compatibility
  auditStatus?: 'clean' | 'qualified' | 'adverse' | 'disclaimer' | 'pending';
  lastAuditDate?: string;
  gdp?: number;
  // Enhanced financial data
  moneyReceived?: number; // Total grants/transfers received
  budgetUtilization?: number; // Percentage of budget used
  auditIssues?: AuditIssue[];
  revenueCollection?: number; // Local revenue collected
  pendingBills?: number; // Outstanding payments
  developmentBudget?: number; // Capital/development budget
  recurrentBudget?: number; // Operational budget
  // Additional fields for county explorer
  governor?: string; // Governor name
  totalBudget?: number; // Total budget (computed from dev + recurrent)
  totalDebt?: number; // Total debt (same as debt)
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

export interface AccountabilityScorecard {
  county_id: string;
  county_name: string;
  audit_opinion_history: Array<{ year: number; opinion: string }>;
  total_flagged_amount: number;
  recurring_findings_count: number;
  unresolved_findings_count: number;
  absorption_rate: number | null;
  accountability_grade: string; // A/B/C/D/F
  peer_comparison: {
    region: string;
    region_avg_flagged_amount: number;
    region_avg_grade: string;
    population_bracket: string;
    population_bracket_avg: number;
  };
}

export interface MoneyFlowStage {
  stage: string;
  label: string;
  amount: number | null;
  source?: string;
  source_doc?: string;
  gap_from_prev?: number | null;
  gap_label?: string;
  data_unavailable?: boolean;
}

export interface MoneyFlowData {
  county_id: number | null;
  county_name: string;
  fiscal_year: string;
  stages: MoneyFlowStage[];
  total_waste_estimate: number | null;
  efficiency_score: number | null;
  county_count?: number;
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
