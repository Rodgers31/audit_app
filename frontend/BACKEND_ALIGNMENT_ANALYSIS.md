# Frontend-Backend Endpoint Alignment Analysis 🔍

> **Superseded, 2026-09-07.** The Enhanced County Analytics service
> (`apis/enhanced_county_analytics_api.py`, port 8003) described below was
> deleted in issue #183 — it served hardcoded rankings of named counties and
> four aggregates nothing measured. Everything it is credited with here is a
> record of what existed then, not of what runs now. Note in particular that
> `InternalAPIClient` in `backend/main.py` still holds a client for it.
>
> **Partly superseded, 2026-09-07.** The Modernized API (`apis/modernized_api.py`,
> port 8004) is credited below with `/national/overview`, `/national/debt` and
> `/national/ministries`. Those three, plus `/national/ministries/{name}`,
> `/national/revenue` and `/analytics/comprehensive`, were withdrawn under issue
> #188: the debt total, the 60/40 external split, the debt-to-GDP ratio, the
> 2020–2024 series and the ministry execution rates they published were typed-in
> constants that disagree with the CBK figures in
> `backend/seeding/real_data/debt_timeline.json`. The service's other nine
> endpoints still run. Nothing replaced the withdrawn figures here — `backend/`
> already holds that data, sourced.

## Executive Summary

After analyzing your frontend endpoint configuration and backend API services, I've identified significant misalignments and data storage recommendations. Here's what I found:

## 🚨 Critical Misalignments

### 1. **Frontend Expects `/api/v1` Prefix - Backend Doesn't Use It**

**Frontend Configuration:**

```typescript
// lib/api/endpoints.ts
export const getApiBaseUrl = () => `${API_CONFIG.BASE_URL}/api/${API_CONFIG.VERSION}`;
// Results in: http://localhost:8000/api/v1
```

**Backend Reality:**

```python
# backend/main.py
@app.get("/api/v1/countries")  # ✅ Some endpoints have /api/v1
@app.get("/api/v1/entities")   # ✅ Some endpoints have /api/v1

# apis/enhanced_county_analytics_api.py
@app.get("/counties/all")      # ❌ Missing /api/v1 prefix
@app.get("/audit/queries")     # ❌ Missing /api/v1 prefix

# apis/modernized_api.py
@app.get("/national/overview") # ❌ Missing /api/v1 prefix
@app.get("/counties/{county_name}") # ❌ Missing /api/v1 prefix
```

### 2. **Missing Counties Endpoints in Backend**

**Frontend Expects:**

```typescript
COUNTIES_ENDPOINTS = {
  LIST: '/counties', // ❌ No backend equivalent
  GET_BY_ID: (id) => `/counties/${id}`, // ❌ No backend equivalent
  SEARCH: '/counties/search', // ❌ No backend equivalent
  TOP_PERFORMING: '/counties/top-performing', // ❌ No backend equivalent
  FLAGGED: '/counties/flagged', // ❌ No backend equivalent
  BUDGET: (id) => `/counties/${id}/budget`, // ❌ No backend equivalent
  DEBT: (id) => `/counties/${id}/debt`, // ❌ No backend equivalent
};
```

**Backend Has:**

```python
# enhanced_county_analytics_api.py (Port 8003)
@app.get("/counties/all")              # Similar to LIST but different path
@app.get("/counties/{county_name}")    # Uses name, not ID
@app.get("/rankings/{metric}")         # Similar to TOP_PERFORMING
```

### 3. **Backend Data is Spread Across 3 Different APIs**

Your backend has **3 separate API servers**:

1. **Main Backend** (Port 8000) - `/api/v1/...`
   - Countries, entities, documents, analytics
2. **Enhanced County Analytics** (Port 8003) - No prefix
   - Counties, rankings, audit queries, debt
3. **Modernized Data-Driven API** (Port 8004) - No prefix
   - National overview, ministries, counties stats

**Frontend assumes everything is on Port 8000** with `/api/v1` prefix!

## 📊 Current UI Data vs Backend Support

### ✅ **Data Currently Supported by Backend:**

1. **Counties Basic Info**

   - ✅ Backend: Enhanced County Analytics API `/counties/all`
   - ✅ Frontend: Using mock `KENYA_COUNTIES`

2. **National Statistics**

   - ✅ Backend: Modernized API `/national/overview`
   - ✅ Frontend: Dashboard stats hooks ready

3. **Audit Information**

   - ✅ Backend: Enhanced County Analytics `/audit/queries`
   - ✅ Frontend: Audit hooks configured

4. **Debt Data**
   - ✅ Backend: Enhanced County Analytics `/national/debt`
   - ✅ Frontend: Debt hooks ready

### ❌ **Data NOT Supported by Backend:**

1. **County Geographic Data (GeoJSON)**

   - 📍 Frontend: `public/kenya-counties.json` (47 counties with coordinates)
   - ❌ Backend: No geographic/boundary data endpoints
   - 🔧 **Recommendation:** Keep GeoJSON in frontend (large file, rarely changes)

2. **Quiz Questions & Educational Content**

   - 📚 Frontend: `components/EngagementQuiz.tsx` (3 quizzes, 12 questions total)
   - ❌ Backend: No quiz/educational endpoints
   - 🔧 **Recommendation:** Keep in frontend (static educational content)

3. **Detailed County Financial Metrics**
   - 📊 Frontend: Expects budget trends, debt timelines, financial summaries
   - ❌ Backend: Basic data only, no time series or detailed breakdowns

## 🎯 Data Storage Recommendations

### **Keep in Frontend (UI/Static Data):**

✅ **Quiz Questions** - Educational content that rarely changes

```tsx
// Good to keep in frontend
const quizzes = [
  {
    id: 'budget-basics',
    questions: [
      /* quiz data */
    ],
  },
];
```

✅ **Geographic Data (GeoJSON)** - Large, static boundary data

```json
// Good to keep in public/kenya-counties.json
{
  "type": "FeatureCollection",
  "features": [
    /* county boundaries */
  ]
}
```

✅ **UI Configuration** - Color schemes, map settings, display preferences

### **Move to Backend (Dynamic Data):**

❌ **County Financial Data** - Should come from backend

```typescript
// Move from frontend mock data to API calls
const KENYA_COUNTIES = [
  /* This should come from API */
];
```

❌ **Audit Reports** - Real-time audit information
❌ **Budget Information** - Current budget data  
❌ **Debt Statistics** - Up-to-date debt figures
❌ **Performance Rankings** - Dynamic rankings based on current data

## 🛠️ Required Backend Changes

### 1. **Standardize API Prefix**

```python
# ALL APIs should use /api/v1 prefix
@app.get("/api/v1/counties")           # ✅ Standardize
@app.get("/api/v1/counties/{id}")      # ✅ Add missing
@app.get("/api/v1/counties/search")    # ✅ Add missing
@app.get("/api/v1/audits")             # ✅ Add missing
@app.get("/api/v1/budget/comparison")  # ✅ Add missing
@app.get("/api/v1/debt/national")      # ✅ Add missing
@app.get("/api/v1/stats/dashboard")    # ✅ Add missing
```

### 2. **Consolidate to Single API**

Instead of 3 separate APIs, create unified endpoints in main backend:

```python
# Consolidate into backend/main.py
@app.get("/api/v1/counties")
@app.get("/api/v1/counties/{id}")
@app.get("/api/v1/counties/{id}/budget")
@app.get("/api/v1/counties/{id}/audits")
@app.get("/api/v1/audits")
@app.get("/api/v1/budget/national")
@app.get("/api/v1/debt/national")
@app.get("/api/v1/stats/dashboard")
```

### 3. **Add Missing Endpoints**

- County search functionality
- Budget trends and comparisons
- Debt timeline analysis
- Performance rankings
- Audit report filtering

## 🚀 Migration Strategy

### **Phase 1: Fix URL Alignment**

1. Update frontend to point to correct backend ports temporarily
2. Add `/api/v1` prefix to all backend endpoints
3. Test basic connectivity

### **Phase 2: Consolidate APIs**

1. Move all county/audit/budget logic to main backend
2. Update frontend to use single backend URL
3. Deprecate separate API services

### **Phase 3: Add Missing Features**

1. Implement missing endpoints (search, trends, rankings)
2. Replace frontend mock data with API calls
3. Add proper error handling and loading states

## 📝 Immediate Action Items

1. **Start with Main Backend** (Port 8000) - it's most aligned with frontend expectations
2. **Keep Quiz Questions in Frontend** - they're educational content that rarely changes
3. **Keep GeoJSON in Frontend** - large static geographic data
4. **Move County Financial Data to Backend** - dynamic data that needs real-time updates
5. **Standardize all backend endpoints** to use `/api/v1` prefix

## 🔧 Quick Fix for Testing

To test immediately, update your frontend base URL to point to the Enhanced County Analytics API:

```typescript
// Temporary fix in .env.local
NEXT_PUBLIC_API_URL=http://localhost:8003

// Or create endpoint mapping
const COUNTY_BASE_URL = 'http://localhost:8003';
const MAIN_BASE_URL = 'http://localhost:8000';
```

Would you like me to help implement any of these changes or create a migration plan?
