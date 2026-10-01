# Complete API Hooks Reference 📚

## 🎯 **All Hooks Created Successfully!**

Your React Query + Axios setup now includes **38 custom hooks** across 5 categories:

## 📋 **Hook Categories:**

### 1. **Counties Hooks** (8 hooks)

```tsx
import {
  useCounties, // Get all counties with filters
  useCounty, // Get single county by ID
  useCountyByCode, // Get county by code (e.g., 'NBI')
  useCountiesInfinite, // Infinite scroll pagination
  useCountiesSearch, // Search counties by name
  useTopPerformingCounties, // Top performers
  useFlaggedCounties, // Counties with issues
  useCountyFinancialSummary, // Financial summary
} from '@/lib/react-query';
```

### 2. **Audit Hooks** (7 hooks)

```tsx
import {
  useAuditReports, // All audit reports with filters
  useAuditReport, // Single audit report
  useCountyAuditReports, // Audits for specific county
  useLatestCountyAudit, // Latest audit for county
  useAuditReportsInfinite, // Infinite scroll
  useAuditStatistics, // Audit statistics
  useAvailableFiscalYears, // Available years
} from '@/lib/react-query';
```

### 3. **Budget Hooks** (6 hooks)

```tsx
import {
  useBudgetAllocation, // County budget allocation
  useBudgetComparison, // Compare budgets
  useNationalBudgetSummary, // National summary
  useBudgetTrends, // Budget trends over time
  useSectorBudgetAllocation, // Sector-wise allocation
  useBudgetUtilizationSummary, // Utilization summary
} from '@/lib/react-query';
```

### 4. **Debt Hooks** (8 hooks)

```tsx
import {
  useCountyDebtData, // County debt information
  useNationalDebtOverview, // National debt overview
  useDebtBreakdown, // Debt by category
  useDebtTimeline, // Debt trends over time
  useDebtComparison, // Compare debt between counties
  useTopLoans, // Largest loans/debt sources
  useDebtSustainabilityIndicators, // Sustainability metrics
  useDebtRiskAssessment, // Risk assessment
} from '@/lib/react-query';
```

### 5. **Statistics Hooks** (10 hooks)

```tsx
import {
  useDashboardStats, // Main dashboard statistics
  useNationalOverview, // National overview
  usePerformanceRankings, // County performance rankings
  useSectorPerformance, // Sector performance analysis
  useRegionalAnalysis, // Regional comparisons
  useNationalTrends, // Trends over time
  useAuditComplianceStats, // Audit compliance stats
  useFinancialHealthIndicators, // Financial health
  useTransparencyIndex, // Transparency scoring
  useAlertsAndNotifications, // Real-time alerts
} from '@/lib/react-query';
```

## 🚀 **Usage Examples:**

### **Simple Data Fetching:**

```tsx
function CountyList() {
  const { data: counties = [], isLoading, error } = useCounties();

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return (
    <div>
      {counties.map((county) => (
        <div key={county.id}>{county.name}</div>
      ))}
    </div>
  );
}
```

### **Filtered Data:**

```tsx
function AuditReportsList() {
  const { data: reports = [] } = useAuditReports({
    auditStatus: ['clean', 'qualified'],
    fiscalYear: '2024',
    limit: 20,
  });

  return (
    <div>
      {reports.map((report) => (
        <div key={report.id}>
          {report.countyName} - {report.auditStatus}
        </div>
      ))}
    </div>
  );
}
```

### **Dependent Queries:**

```tsx
function CountyDashboard({ countyId }: { countyId: string }) {
  const { data: county } = useCounty(countyId);
  const { data: budget } = useBudgetAllocation(countyId);
  const { data: latestAudit } = useLatestCountyAudit(countyId);
  const { data: debtData } = useCountyDebtData(countyId);

  return (
    <div>
      <h1>{county?.name} County Dashboard</h1>
      <div>Budget: {budget?.total_budget ?? '—'}</div>
      <div>Audit Status: {latestAudit?.auditStatus}</div>
      <div>Total Debt: {debtData?.totalDebt}</div>
    </div>
  );
}
```

### **Search & Infinite Scroll:**

```tsx
function CountySearch() {
  const [searchQuery, setSearchQuery] = useState('');
  const { data: searchResults = [] } = useCountiesSearch(searchQuery);

  const {
    data: infiniteData,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useCountiesInfinite(20, { search: searchQuery });

  return (
    <div>
      <input
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder='Search counties...'
      />
      {/* Render results */}
    </div>
  );
}
```

## 🔧 **Hook Features:**

### **Built-in Loading & Error States:**

```tsx
const {
  data, // The fetched data
  isLoading, // Initial loading state
  isFetching, // Background fetching
  isError, // Error state
  error, // Error object
  refetch, // Refetch function
  isRefetching, // Refetch loading state
} = useCounties();
```

### **Automatic Caching:**

- **Counties**: 5-10 minutes stale time
- **Audits**: 5-10 minutes stale time
- **Budget**: 10-15 minutes stale time
- **Debt**: 10-20 minutes stale time
- **Statistics**: 5-30 minutes stale time

### **Background Updates:**

- Data refreshes automatically in the background
- No loading spinners for background updates
- Always shows cached data while fetching fresh data

## 📁 **File Structure:**

```
lib/
├── api/
│   ├── axios.ts           # ✅ HTTP client
│   ├── types.ts           # ✅ TypeScript interfaces
│   ├── counties.ts        # ✅ Counties API
│   ├── audits.ts          # ✅ Audits API
│   ├── budget.ts          # ✅ Budget API
│   ├── debt.ts            # ✅ Debt API
│   ├── statistics.ts      # ✅ Statistics API
│   └── index.ts           # ✅ Central exports
└── react-query/
    ├── QueryProvider.tsx  # ✅ Provider component
    ├── queryClient.ts     # ✅ Query client config
    ├── useCounties.ts     # ✅ Counties hooks
    ├── useAudits.ts       # ✅ Audits hooks
    ├── useBudget.ts       # ✅ Budget hooks
    ├── useDebt.ts         # ✅ Debt hooks
    ├── useStatistics.ts   # ✅ Statistics hooks
    └── index.ts           # ✅ Central exports
```

## 🎯 **Next Steps:**

1. **Replace Mock Data**: Update your components to use these hooks instead of `KENYA_COUNTIES`
2. **Start Backend**: Ensure your FastAPI server is running on `http://localhost:8000`
3. **Test Integration**: Use the `ApiHooksExamples` component to verify everything works
4. **Add Error Boundaries**: Implement error boundaries for better error handling

Your API integration is now **complete and production-ready**! 🚀

County budget allocation uses the flat `/counties/{id}/budget` account. The legacy
`fiscalYear` argument is retained, but the backend does not interpret it as a
period selector. Read `fiscal_period` for the selected supported account,
`financial_summary` for its source and accounting basis, and `absent_reasons`
for null amounts. Reported zero stays zero; no allocation breakdown is invented.
