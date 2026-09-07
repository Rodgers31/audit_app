# 🚀 POSTMAN SETUP & TESTING GUIDE

# Kenya Audit Transparency API Collection

## 📋 QUICK SETUP INSTRUCTIONS

### 1. Import Collection & Environment

1. Open Postman
2. Click "Import" button (top left)
3. Import these files:
   - `Kenya_Audit_Transparency_API.postman_collection.json`
   - `Kenya_Audit_API.postman_environment.json`
4. Select "Kenya Audit API Environment" from environment dropdown

### 2. Start All API Services

Open 2 separate terminals and run:

**Terminal 1 - Modernized Data-Driven API:**

```bash
cd c:/Users/rodge/projects/audit_app/apis
python modernized_api.py
```

_Should start on http://localhost:8004_

**Terminal 2 - Main Backend API:**

```bash
cd c:/Users/rodge/projects/audit_app/backend
python main.py
```

_Should start on http://localhost:8000_

## 🎯 PRIORITY TESTING SEQUENCE

### Phase 1: Health Checks (Test First!)

1. **Modernized API Health Check** - `GET /health`
2. **Main Backend API Root** - `GET /`

### Phase 2: Data Validation (Critical!)

1. **Get County Statistics** - `GET /counties/statistics` (Modernized API)
   - ✅ Check total budget is ~259B KES
   - ✅ Verify 47 counties present

### Phase 3: Core Functionality

1. **County-Specific Tests:**

   - Test with: Nairobi, Mombasa, Nakuru, Kiambu
   - Check population-budget correlation

2. **Audit Data Tests:**

   - Get all audit queries
   - Filter by county
   - Verify OAG data is realistic

3. **Analytics Tests:**
   - County rankings
   - Transparency metrics
   - Comprehensive analytics

## 📊 EXPECTED DATA VALIDATION POINTS

### County Data Quality Checks:

- **Nairobi**: Population 4.4M, Budget ~49.5B KES
- **Mombasa**: Population 1.2M, Budget ~9.8B KES (NOT 18B!)
- **Nakuru**: Population 2.2M, Budget ~15.2B KES
- **No Uniform Patterns**: Budgets should vary by population

### National Data Quality Checks:

- **Total County Budgets**: ~259B KES
- **National Debt**: 11.5T KES
- **Ministry Data**: Realistic allocations

### Audit Data Quality Checks:

- **OAG Queries**: Real audit concerns
- **Missing Funds**: Specific cases
- **Severity Levels**: High/Medium/Low classifications

## 🔧 TESTING SCENARIOS

### Scenario 1: County Comparison

1. Get Nairobi data
2. Get Mombasa data
3. Compare budget-to-population ratios
4. Verify no suspicious uniform patterns

### Scenario 2: Audit Investigation

1. Get all audit queries
2. Filter by specific county
3. Check for missing funds cases
4. Verify severity classifications

### Scenario 3: National Overview

1. Get national debt analysis
2. Get ministry performance data
3. Get revenue analysis
4. Check for data consistency

### Scenario 4: ETL Pipeline

1. Start Kenya ETL pipeline
2. Check job status
3. Get ETL sources status
4. Verify data refresh capabilities

## 🚨 RED FLAGS TO WATCH FOR

### Data Quality Issues:

- ❌ Mombasa budget showing 18B (old fake data)
- ❌ Nairobi population showing 906K (should be 4.4M)
- ❌ Uniform budget patterns across counties
- ❌ Total budgets under 200B KES

### API Issues:

- ❌ 500 errors on basic endpoints
- ❌ Missing data in responses
- ❌ Timeout on large data requests
- ❌ Incorrect JSON structure

## ✅ SUCCESS CRITERIA

### Data Quality ✅

- All counties have realistic population data
- Budget allocations correlate with population
- National debt shows 11.5T KES
- No algorithmic fake patterns

### API Functionality ✅

- All 46 endpoints return valid JSON
- Filtering parameters work correctly
- Error handling for invalid inputs
- Consistent response formats

### Performance ✅

- Response times under 5 seconds
- Large datasets handled properly
- No memory leaks or crashes
- Stable under multiple requests

## 📈 TESTING REPORT TEMPLATE

**API Service**: [Modernized/Main Backend]
**Endpoint**: [GET/POST endpoint URL]
**Status Code**: [200/404/500]
**Response Time**: [X seconds]
**Data Quality**: [✅/❌ with notes]
**Issues Found**: [List any problems]

## 🎉 COMPLETION CHECKLIST

- [ ] All 3 APIs running successfully
- [ ] Health checks pass for all services
- [ ] County data shows realistic figures
- [ ] National overview data correct
- [ ] Audit queries contain real OAG data
- [ ] No fake data patterns detected
- [ ] All endpoints respond correctly
- [ ] Filtering and search work properly
- [ ] POST endpoints accept valid data
- [ ] Error handling works for invalid inputs

**Ready for UI Development When:**
✅ All checklist items completed
✅ No critical data quality issues
✅ All core endpoints tested successfully
