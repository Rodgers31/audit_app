#!/usr/bin/env python3
"""
COMPLETE BACKEND API ENDPOINTS TESTING GUIDE
============================================

This document provides all endpoints for testing your Kenya audit transparency app
in Postman, including request methods, parameters, and expected responses.
"""

from datetime import datetime


def generate_api_testing_guide():
    print("🚀 COMPLETE BACKEND API ENDPOINTS TESTING GUIDE")
    print("=" * 58)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    print("🏗️ AVAILABLE API SERVICES")
    print("=" * 26)
    print("1. 🔧 Modernized Data-Driven API (Port 8004)")
    print("2. 🏛️ Main Backend API (Port 8000)")
    print()

    print("=" * 80)
    print("🔧 1. MODERNIZED DATA-DRIVEN API")
    print("=" * 80)
    print("Base URL: http://localhost:8004")
    print("Description: Modern API using actual extracted data")
    print()

    modernized_endpoints = [
        {
            "method": "GET",
            "endpoint": "/health",
            "description": "API health check with data source status",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/data-sources",
            "description": "Get status of all data sources",
            "params": None,
            "body": None,
        },
        {
            "method": "POST",
            "endpoint": "/refresh-data",
            "description": "Refresh all data from source files",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/national/overview",
            "description": "Get data-driven national overview",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/national/debt",
            "description": "Get real-time debt analysis",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/national/ministries",
            "description": "Get ministry data from actual sources",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/national/ministries/{ministry_name}",
            "description": "Get specific ministry from data-driven sources",
            "params": "ministry_name (path): Ministry name",
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/national/revenue",
            "description": "Get revenue data from actual sources",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/counties/statistics",
            "description": "Get county statistics from realistic data",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/counties/{county_name}",
            "description": "Get specific county from realistic data",
            "params": "county_name (path): County name",
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/audit/overview",
            "description": "Get audit overview from real OAG data",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/audit/queries",
            "description": "Get audit queries with filtering",
            "params": "county (query, optional), query_type (query, optional), severity (query, optional)",
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/analytics/comprehensive",
            "description": "Get comprehensive analytics from all sources",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/analytics/transparency",
            "description": "Get transparency score and metrics",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/reports/summary",
            "description": "Get summary of available reports",
            "params": None,
            "body": None,
        },
    ]

    for i, ep in enumerate(modernized_endpoints, 1):
        print(f"{i:2d}. {ep['method']} {ep['endpoint']}")
        print(f"    📝 {ep['description']}")
        if ep["params"]:
            print(f"    📋 Parameters: {ep['params']}")
        print()

    print("=" * 80)
    print("🏛️ 2. MAIN BACKEND API")
    print("=" * 80)
    print("Base URL: http://localhost:8000")
    print("Description: Core backend API with ETL and document management")
    print()

    main_endpoints = [
        {
            "method": "GET",
            "endpoint": "/",
            "description": "API root information",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/countries",
            "description": "Get all countries (Kenya focus)",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/countries/{country_id}/summary",
            "description": "Get country summary",
            "params": "country_id (path): Country ID (1 for Kenya)",
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/entities",
            "description": "Get all government entities",
            "params": "type (query, optional): Filter by entity type",
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/entities/{entity_id}",
            "description": "Get specific entity details",
            "params": "entity_id (path): Entity ID",
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/entities/{entity_id}/periods/{period_id}/budget_lines",
            "description": "Get budget lines for entity and period",
            "params": "entity_id (path), period_id (path)",
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/documents/{document_id}",
            "description": "Get specific document",
            "params": "document_id (path): Document ID",
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/search",
            "description": "Search documents and entities",
            "params": "q (query): Search query string",
            "body": None,
        },
        {
            "method": "POST",
            "endpoint": "/api/v1/annotations",
            "description": "Create annotation",
            "params": None,
            "body": '{"document_id": 1, "text": "annotation text", "type": "note"}',
        },
        {
            "method": "POST",
            "endpoint": "/api/v1/documents/upload",
            "description": "Upload document",
            "params": None,
            "body": "Form data with file upload",
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/analytics/top_spenders",
            "description": "Get top spending entities",
            "params": None,
            "body": None,
        },
        {
            "method": "POST",
            "endpoint": "/api/v1/etl/kenya/start",
            "description": "Start Kenya ETL pipeline",
            "params": None,
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/etl/status/{job_id}",
            "description": "Get ETL job status",
            "params": "job_id (path): ETL job ID",
            "body": None,
        },
        {
            "method": "GET",
            "endpoint": "/api/v1/etl/kenya/sources",
            "description": "Get Kenya ETL data sources status",
            "params": None,
            "body": None,
        },
    ]

    for i, ep in enumerate(main_endpoints, 1):
        print(f"{i:2d}. {ep['method']} {ep['endpoint']}")
        print(f"    📝 {ep['description']}")
        if ep["params"]:
            print(f"    📋 Parameters: {ep['params']}")
        if ep["body"]:
            print(f"    📤 Body: {ep['body']}")
        print()

    print("=" * 80)
    print("🧪 POSTMAN TESTING INSTRUCTIONS")
    print("=" * 80)
    print()
    print("1. 🚀 START THE APIS:")
    print("   cd /c/Users/rodge/projects/audit_app")
    print("   # Terminal 1:")
    print("   # Terminal 2:")
    print("   cd apis && python modernized_api.py")
    print("   # Terminal 3:")
    print("   cd backend && python main.py")
    print()
    print("2. 📋 CREATE POSTMAN COLLECTION:")
    print("   • Create new collection: 'Kenya Audit Transparency API'")
    print("   • Add folders: 'Modernized API', 'Main Backend'")
    print("   • Import endpoints from this guide")
    print()
    print("3. 🎯 PRIORITY ENDPOINTS TO TEST FIRST:")
    print("   Modernized API:")
    print("   • GET /health")
    print("   • GET /data-sources")
    print("   • GET /counties/statistics")
    print("   • GET /analytics/transparency")
    print()
    print("   Main Backend:")
    print("   • GET /api/v1/countries")
    print("   • POST /api/v1/etl/kenya/start")
    print("   • GET /api/v1/analytics/top_spenders")
    print()
    print("4. 📊 EXPECTED RESPONSE FORMATS:")
    print("   • All responses in JSON format")
    print("   • HTTP 200 for successful requests")
    print("   • HTTP 404 for missing resources")
    print("   • HTTP 500 for server errors")
    print()
    print("5. 🔧 SAMPLE TEST VALUES:")
    print("   County names: 'Nairobi', 'Mombasa', 'Nakuru', 'Kiambu'")
    print("   Metrics: 'budget', 'debt', 'execution_rate', 'financial_health'")
    print("   Ministry names: 'Health', 'Education', 'Infrastructure'")
    print()
    print("✅ TESTING COMPLETE WHEN:")
    print("   • All endpoints return valid JSON responses")
    print("   • County data shows realistic figures (not fake patterns)")
    print("   • Audit data contains real OAG queries")
    print("   • National debt shows 11.5T KES (corrected figure)")
    print("   • No hard-coded fake values in responses")


if __name__ == "__main__":
    generate_api_testing_guide()
