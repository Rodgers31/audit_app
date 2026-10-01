"""
County Data Analyzer
Comprehensive analysis of available county data vs missing counties
"""

import json
from typing import Dict, List, Set

# Complete list of all 47 Kenyan counties
ALL_KENYAN_COUNTIES = [
    "Nairobi",
    "Mombasa",
    "Kwale",
    "Kilifi",
    "Tana River",
    "Lamu",
    "Taita Taveta",
    "Garissa",
    "Wajir",
    "Mandera",
    "Marsabit",
    "Isiolo",
    "Meru",
    "Tharaka Nithi",
    "Embu",
    "Kitui",
    "Machakos",
    "Makueni",
    "Nyandarua",
    "Nyeri",
    "Kirinyaga",
    "Murang'a",
    "Kiambu",
    "Turkana",
    "West Pokot",
    "Samburu",
    "Trans Nzoia",
    "Uasin Gishu",
    "Elgeyo Marakwet",
    "Nandi",
    "Baringo",
    "Laikipia",
    "Nakuru",
    "Narok",
    "Kajiado",
    "Kericho",
    "Bomet",
    "Kakamega",
    "Vihiga",
    "Bungoma",
    "Busia",
    "Siaya",
    "Kisumu",
    "Homa Bay",
    "Migori",
    "Kisii",
    "Nyamira",
]


def analyze_county_data():
    """Analyze county data availability and completeness."""
    print("🏛️ KENYA COUNTY DATA ANALYSIS")
    print("=" * 60)

    # Load county data
    try:
        with open(
            "../data/county/enhanced_county_data.json", "r", encoding="utf-8"
        ) as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ ../data/county/enhanced_county_data.json not found!")
        return

    county_data = data.get("county_data", {})
    counties_with_data = set(county_data.keys())
    expected_counties = set(ALL_KENYAN_COUNTIES)

    # Basic statistics
    print(f"📊 OVERVIEW:")
    print(f"   Expected counties: {len(expected_counties)}")
    print(f"   Counties with data: {len(counties_with_data)}")
    print(f"   Missing counties: {len(expected_counties - counties_with_data)}")
    print(
        f"   Data completeness: {(len(counties_with_data) / len(expected_counties)) * 100:.1f}%"
    )
    print()

    # Check for exact matches
    missing_counties = expected_counties - counties_with_data
    extra_counties = counties_with_data - expected_counties

    if missing_counties:
        print(f"❌ MISSING COUNTIES ({len(missing_counties)}):")
        for county in sorted(missing_counties):
            print(f"   • {county}")
        print()

    if extra_counties:
        print(f"⚠️ UNEXPECTED COUNTIES ({len(extra_counties)}):")
        for county in sorted(extra_counties):
            print(f"   • {county}")
        print()

    if not missing_counties and not extra_counties:
        print("✅ PERFECT MATCH: All 47 counties present!")
        print()

    # Analyze data quality for available counties
    print("📋 DATA QUALITY ANALYSIS:")

    counties_with_complete_data = 0
    counties_with_budget_data = 0
    counties_with_population_data = 0
    counties_with_debt_data = 0

    total_budget = 0
    total_population = 0
    total_debt = 0

    for county_name, county_info in county_data.items():
        has_budget = county_info.get("budget_2025", 0) > 0
        has_population = county_info.get("population", 0) > 0
        has_debt = county_info.get("debt_outstanding", 0) > 0

        if has_budget:
            counties_with_budget_data += 1
            total_budget += county_info.get("budget_2025", 0)

        if has_population:
            counties_with_population_data += 1
            total_population += county_info.get("population", 0)

        if has_debt:
            counties_with_debt_data += 1
            total_debt += county_info.get("debt_outstanding", 0)

        if has_budget and has_population and has_debt:
            counties_with_complete_data += 1

    print(
        f"   Counties with budget data: {counties_with_budget_data}/{len(counties_with_data)}"
    )
    print(
        f"   Counties with population data: {counties_with_population_data}/{len(counties_with_data)}"
    )
    print(
        f"   Counties with debt data: {counties_with_debt_data}/{len(counties_with_data)}"
    )
    print(
        f"   Counties with complete data: {counties_with_complete_data}/{len(counties_with_data)}"
    )
    print()

    # Financial summary
    print("💰 FINANCIAL SUMMARY:")
    print(f"   Total county budgets: KES {total_budget:,}")
    print(f"   Total county population: {total_population:,}")
    print(f"   Total county debt: KES {total_debt:,}")
    if counties_with_budget_data > 0:
        print(
            f"   Average county budget: KES {total_budget / counties_with_budget_data:,.0f}"
        )
    if counties_with_population_data > 0:
        print(
            f"   Average county population: {total_population / counties_with_population_data:,.0f}"
        )
    print()

    # Top counties by budget
    print("🏆 TOP 10 COUNTIES BY BUDGET:")
    counties_by_budget = [
        (name, info.get("budget_2025", 0)) for name, info in county_data.items()
    ]
    counties_by_budget.sort(key=lambda x: x[1], reverse=True)

    for i, (county, budget) in enumerate(counties_by_budget[:10], 1):
        print(f"   {i:2d}. {county:<15} KES {budget:>15,}")
    print()

    # Counties with potential data issues
    print("⚠️ POTENTIAL DATA ISSUES:")
    issue_counties = []

    for county_name, county_info in county_data.items():
        issues = []

        if county_info.get("budget_2025", 0) == 0:
            issues.append("No budget data")

        if county_info.get("population", 0) == 0:
            issues.append("No population data")

        if county_info.get("debt_outstanding", 0) == 0:
            issues.append("No debt data")

        budget = county_info.get("budget_2025", 0)
        population = county_info.get("population", 0)
        if budget > 0 and population > 0:
            per_capita_budget = budget / population
            if per_capita_budget > 50000:  # Suspiciously high
                issues.append(f"High per capita budget: KES {per_capita_budget:,.0f}")
            if per_capita_budget < 1000:  # Suspiciously low
                issues.append(f"Low per capita budget: KES {per_capita_budget:,.0f}")

        if issues:
            issue_counties.append((county_name, issues))

    if issue_counties:
        for county, issues in issue_counties[:10]:  # Show first 10
            print(f"   • {county}: {', '.join(issues)}")
    else:
        print("   ✅ No obvious data issues found!")

    print()
    return {
        "total_counties": len(counties_with_data),
        "missing_counties": list(missing_counties),
        "extra_counties": list(extra_counties),
        "complete_data_counties": counties_with_complete_data,
        "total_budget": total_budget,
        "total_population": total_population,
        "total_debt": total_debt,
    }


if __name__ == "__main__":
    # Run the analysis
    analysis_results = analyze_county_data()
    print()
    print("Legacy county analytics withdrawn (#302); use the DB-backed county API.")

    # Summary
    print()
    print("📈 SUMMARY:")
    print("=" * 30)
    if analysis_results:
        if analysis_results["missing_counties"]:
            print(f"❌ Missing {len(analysis_results['missing_counties'])} counties")
            print("   Action needed: Add missing county data")
        else:
            print("✅ All 47 counties have data!")

        print(f"💰 Total county budget: KES {analysis_results['total_budget']:,}")
        print(f"👥 Total population: {analysis_results['total_population']:,}")
        print(
            f"📊 Data quality: {analysis_results['complete_data_counties']}/{analysis_results['total_counties']} counties complete"
        )
