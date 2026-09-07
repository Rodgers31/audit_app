# API Consolidation Plan 🔄

> **Superseded, 2026-09-07.** The Enhanced County Analytics service
> (`apis/enhanced_county_analytics_api.py`, port 8003) described below was
> deleted in issue #183 — it served hardcoded rankings of named counties and
> four aggregates nothing measured. Everything it is credited with here is a
> record of what existed then, not of what runs now. Note in particular that
> `InternalAPIClient` in `backend/main.py` still holds a client for it.

## Current State Analysis

You have **financial data endpoints** spread across 3 APIs:

### 🏛️ **Main Backend (Port 8000)** - `/api/v1/...`

**Financial Endpoints Available:**

- ✅ `/api/v1/countries/{id}/summary` - National financial summary
- ✅ `/api/v1/entities` - Government entities with budget data
- ✅ `/api/v1/entities/{id}` - Entity financial details
- ✅ `/api/v1/analytics/top_spenders` - Top spending entities

**Missing Counties Support:** ❌ No county-specific endpoints

### 🏘️ **Enhanced County Analytics (Port 8003)** - No prefix

**Financial Endpoints Available:**

- ✅ `/counties/all` - All counties with financial data (budget, debt, revenue)
- ✅ `/counties/{county_name}` - Detailed county financial metrics
- ✅ `/rankings/{metric}` - Financial performance rankings
- ✅ `/national/debt` - National debt analysis
- ✅ `/national/revenue` - Revenue analysis

**Data Structure:**

```python
county_info = {
    "budget_2025": float,
    "revenue_2024": float,
    "debt_outstanding": float,
    "pending_bills": float,
    "financial_health_score": float,
    "budget_execution_rate": float,
    "debt_to_budget_ratio": float
}
```

### 📊 **Modernized API (Port 8004)** - No prefix

**Financial Endpoints Available:**

- ✅ `/national/overview` - National budget overview
- ✅ `/national/debt` - National debt from verified sources
- ✅ `/national/ministries` - Ministry budget allocations
- ✅ `/counties/{county_name}` - County details from extracted data

## 🎯 Consolidation Strategy

### **Phase 1: Add County Endpoints to Main Backend**

Add these endpoints to `backend/main.py` to match your frontend expectations:

```python
# Add to backend/main.py

@app.get("/api/v1/counties")
async def get_counties(
    search: Optional[str] = Query(None),
    audit_status: Optional[List[str]] = Query(None),
    limit: Optional[int] = Query(20)
):
    """Get counties with financial data"""
    # Call Enhanced County Analytics API internally

@app.get("/api/v1/counties/{county_id}")
async def get_county(county_id: str):
    """Get detailed county financial information"""

@app.get("/api/v1/counties/{county_id}/budget")
async def get_county_budget(county_id: str, fiscal_year: Optional[str] = None):
    """Get county budget information"""

@app.get("/api/v1/counties/{county_id}/debt")
async def get_county_debt(county_id: str):
    """Get county debt information"""

@app.get("/api/v1/counties/{county_id}/audits")
async def get_county_audits(county_id: str):
    """Get county audit reports"""

@app.get("/api/v1/counties/search")
async def search_counties(q: str):
    """Search counties by name"""

@app.get("/api/v1/counties/top-performing")
async def get_top_performing_counties(limit: int = 10):
    """Get top performing counties"""

@app.get("/api/v1/stats/dashboard")
async def get_dashboard_stats():
    """Get dashboard statistics"""

@app.get("/api/v1/debt/national")
async def get_national_debt():
    """Get national debt analysis"""

@app.get("/api/v1/budget/national")
async def get_national_budget():
    """Get national budget summary"""
```

### **Phase 2: County ID Mapping**

Your frontend uses county IDs like `'001'`, but the Enhanced County Analytics API uses county names like `'Nairobi'`. Need to create a mapping:

```python
# Add county mapping in backend/main.py
COUNTY_ID_TO_NAME_MAP = {
    '001': 'NAIROBI',
    '002': 'KWALE',
    '003': 'KILIFI',
    # ... all 47 counties
}

COUNTY_NAME_TO_ID_MAP = {v: k for k, v in COUNTY_ID_TO_NAME_MAP.items()}
```

### **Phase 3: Internal API Calls**

The main backend will make internal HTTP calls to the other APIs:

```python
import httpx

async def call_county_analytics_api(endpoint: str):
    """Internal call to Enhanced County Analytics API"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://localhost:8003{endpoint}")
        return response.json()

async def call_modernized_api(endpoint: str):
    """Internal call to Modernized API"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://localhost:8004{endpoint}")
        return response.json()
```

## 🛠️ Implementation Plan

### **Step 1: Install Required Dependencies**

```bash
cd backend/
pip install httpx  # For internal API calls
```

### **Step 2: Add County Mapping**

Create the 47-county ID to name mapping in main backend.

### **Step 3: Add Missing Endpoints**

Add all the county endpoints that your frontend expects.

### **Step 4: Test Integration**

Start all 3 APIs and test the consolidated endpoints.

### **Step 5: Update Frontend Configuration**

Keep frontend pointing to main backend (Port 8000) only.

## 📊 Financial Data You Currently Have

Based on the Enhanced County Analytics API, you have **comprehensive financial data**:

### **County-Level Financial Data:**

- ✅ **Budget 2025** - County budget allocation
- ✅ **Revenue 2024** - County revenue collection
- ✅ **Debt Outstanding** - Current county debt
- ✅ **Pending Bills** - Unpaid county obligations
- ✅ **Budget Execution Rate** - How much of budget was spent
- ✅ **Financial Health Score** - Calculated health metric
- ✅ **Debt to Budget Ratio** - Debt sustainability indicator

### **National-Level Financial Data:**

- ✅ **Total National Debt** - 11.5T KES
- ✅ **Debt Breakdown** - External vs domestic debt
- ✅ **Ministry Budget Allocations** - Per ministry spending
- ✅ **Revenue Collection** - Government income

### **Audit Data:**

- ✅ **Audit Queries** - County-specific audit issues
- ✅ **Missing Funds Cases** - Identified financial irregularities
- ✅ **Audit Ratings** - County audit performance

## 🚀 What You Need to Build

You have the **financial data** - you just need to **consolidate the endpoints** into your main backend to match your frontend expectations.

The financial data exists in the Enhanced County Analytics API - we just need to:

1. ✅ Add proper `/api/v1` endpoints to main backend
2. ✅ Create county ID ↔ name mapping
3. ✅ Make internal API calls to get the data
4. ✅ Format responses to match frontend expectations

## 🎯 Next Steps

1. **Start with County Mapping** - Create the 47-county ID mapping
2. **Add Basic County Endpoints** - `/api/v1/counties` and `/api/v1/counties/{id}`
3. **Test One Endpoint** - Get counties list working first
4. **Add Financial Endpoints** - Budget, debt, audit endpoints
5. **Update Frontend** - Point to consolidated API

Would you like me to start implementing the county mapping and basic endpoints in your main backend?
