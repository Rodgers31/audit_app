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

> Six of this service's endpoints were withdrawn on 2026-09-07 under issue #188
> — `/national/overview`, `/national/debt`, `/national/ministries`,
> `/national/ministries/{name}`, `/national/revenue` and
> `/analytics/comprehensive` served typed-in debt, budget and revenue figures.
> Two more were withdrawn on 2026-09-26: `/counties/statistics` and
> `/counties/{county_name}` served `enhanced_county_data.json`, whose every
> figure but the Census population is modelled (budget = population x KSh 4,500
> x a hand-set factor; missing funds 2% of that; audit ratings read off the same
> factor), as fact about named counties. Its other seven endpoints are
> unchanged.

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

### Phase 2: Core Functionality

1. **Audit Data Tests:**

   - Get all audit queries
   - Filter by county
   - Verify OAG data is realistic

2. **Analytics Tests:**
   - Transparency metrics
   - Comprehensive analytics

## 📊 EXPECTED DATA VALIDATION POINTS

### County Data Quality Checks:

This section used to list expected county budgets (Nairobi ~49.5B, Mombasa
~9.8B, a ~259B total) and to check that budgets track population. Those were
the outputs of the model in `enhanced_county_data.json` — population x KSh 4,500
x a hand-set factor — so matching them proved only that the model was being
served. Check county money against a published source — the Controller of
Budget's County Budget Implementation Review Reports — not against these.

### National Data Quality Checks:

- **National Debt**: check against `backend/seeding/real_data/debt_timeline.json`,
  which carries CBK figures cited to the PDF page. Do not assert 11.5T — that
  came from the endpoints withdrawn under issue #188 and disagrees with CBK.

### Audit Data Quality Checks:

- **OAG Queries**: Real audit concerns
- **Missing Funds**: Specific cases
- **Severity Levels**: High/Medium/Low classifications

## 🔧 TESTING SCENARIOS

### Scenario 1: Audit Investigation

1. Get all audit queries
2. Filter by specific county
3. Check for missing funds cases
4. Verify severity classifications

### Scenario 2: ETL Pipeline

1. Start Kenya ETL pipeline
2. Check job status
3. Get ETL sources status
4. Verify data refresh capabilities

## 🚨 RED FLAGS TO WATCH FOR

### Data Quality Issues:

- ❌ Nairobi population showing 906K (should be 4.4M)

### API Issues:

- ❌ 500 errors on basic endpoints
- ❌ Missing data in responses
- ❌ Timeout on large data requests
- ❌ Incorrect JSON structure

## ✅ SUCCESS CRITERIA

### Data Quality ✅

- All counties have realistic population data
- Every published figure traces to a sourced row, not to a typed constant
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
