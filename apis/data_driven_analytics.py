"""
Data-Driven Government Analytics System
Reads from actual extracted data files instead of hard-coded values
Automatically updates when new data is available

WITHDRAWN 2026-09-07 (issue #188): six methods that did NOT read from any data
file, and published typed-in figures under the docstring above.

    get_current_national_debt          "total_debt": 11_500_000_000_000, a 60/40
                                       external split, "debt_to_gdp_ratio": 70.2
    _calculate_debt_trend              five typed constants for 2020-2024
    get_actual_budget_data             "national_budget_2024_25": 3_800_000_000_000
    get_ministry_performance_from_data execution rates from abs(hash(name)) % 25
    get_revenue_data_from_sources      revenue = budget * 0.75 * 0.875, split 80/20
    get_comprehensive_analytics        composed the five above

Every point of that debt series disagrees with backend/seeding/real_data/
debt_timeline.json, which carries CBK figures cited to the PDF page — including
the direction of 2023-2024, which CBK records as a fall (11,139.7 to 10,925.3
Bn) and the module drew as a rise, and the external share, which CBK puts at
46.3% for 2024 against the module's 60%.

What remains reads from files and reports what it finds. Note that the five
paths in ``data_sources`` below do not resolve in this repo — ``data/`` exists,
``data/county/``, ``data/audit/``, ``data/cob/`` and ``data/government/`` do
not — so these methods currently report absence. That is a separate defect,
recorded in issue #188 under "the data-driven path is dead, and fails
silently", and reporting absence is not the same thing as asserting a
fabricated number.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataDrivenGovernmentAnalytics:
    """Data-driven analytics system that reads from actual extracted data."""

    def __init__(self):
        self.data_sources = {
            "county_data": "../data/county/enhanced_county_data.json",
            "oag_audit": "../data/audit/oag_audit_data.json",
            "cob_reports": "../data/cob/comprehensive_cob_reports_database.json",
            "government_reports": "../data/government/comprehensive_government_reports.json",
            "etl_results": "../data/government/ultimate_etl_results.json",
        }

        self.cached_data = {}
        self.load_all_data()

    def load_all_data(self):
        """Load all available data sources."""
        logger.info("📊 Loading data from actual extracted files...")

        for source_name, filename in self.data_sources.items():
            try:
                if os.path.exists(filename):
                    with open(filename, "r", encoding="utf-8") as f:
                        self.cached_data[source_name] = json.load(f)
                    logger.info(f"✅ Loaded {source_name} from {filename}")
                else:
                    logger.warning(f"⚠️ File not found: {filename}")
                    self.cached_data[source_name] = {}
            except Exception as e:
                logger.error(f"❌ Failed to load {filename}: {e}")
                self.cached_data[source_name] = {}

    def get_actual_county_statistics(self) -> Dict[str, Any]:
        """Get county statistics from actual extracted data."""
        county_file_data = self.cached_data.get("county_data", {})

        if not county_file_data:
            logger.warning("⚠️ No county data available, using minimal dataset")
            return {"total_counties": 47, "data_available": False}

        # Extract the actual county data from the nested structure
        counties = county_file_data.get("county_data", {})

        if not counties:
            logger.warning("⚠️ County data structure missing 'county_data' key")
            return {"total_counties": 47, "data_available": False}

        total_counties = len(counties)

        # Calculate totals from actual data
        total_budget = sum(county.get("budget_2025", 0) for county in counties.values())
        total_population = sum(
            county.get("population", 0) for county in counties.values()
        )
        total_debt = sum(
            county.get("debt_outstanding", 0) for county in counties.values()
        )

        # Calculate averages
        avg_budget = total_budget / total_counties if total_counties > 0 else 0
        avg_execution = (
            sum(county.get("budget_execution_rate", 0) for county in counties.values())
            / total_counties
            if total_counties > 0
            else 0
        )

        return {
            "total_counties": total_counties,
            "total_county_budget": total_budget,
            "average_budget_per_county": avg_budget,
            "total_county_population": total_population,
            "total_county_debt": total_debt,
            "average_execution_rate": avg_execution,
            "data_source": "enhanced_county_data.json",
            "data_available": True,
            "last_calculated": datetime.now().isoformat(),
        }

    def get_actual_audit_statistics(self) -> Dict[str, Any]:
        """Get audit statistics from actual OAG data."""
        oag_data = self.cached_data.get("oag_audit", {})

        if not oag_data:
            logger.warning("⚠️ No OAG audit data available")
            return {"audit_queries": 0, "data_available": False}

        # Extract real audit metrics
        audit_queries = oag_data.get("audit_queries", [])
        total_queries = len(audit_queries)

        # Calculate actual missing funds
        total_missing_funds = sum(
            query.get("amount", 0)
            for query in audit_queries
            if query.get("severity") in ["High", "Critical"]
        )

        # Count by severity
        severity_counts = {}
        for query in audit_queries:
            severity = query.get("severity", "Unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        return {
            "total_audit_queries": total_queries,
            "total_missing_funds": total_missing_funds,
            "severity_breakdown": severity_counts,
            "data_source": "oag_audit_data.json",
            "data_available": True,
            "last_calculated": datetime.now().isoformat(),
        }

    def _calculate_transparency_score(self) -> int:
        """Calculate transparency score based on actual data availability."""
        total_sources = len(self.data_sources)
        available_sources = len([k for k, v in self.cached_data.items() if v])

        base_score = (available_sources / total_sources) * 100

        # Bonus points for data quality
        if self.cached_data.get("county_data"):
            base_score += 5
        if self.cached_data.get("oag_audit"):
            base_score += 5
        if self.cached_data.get("cob_reports"):
            base_score += 5

        return min(100, int(base_score))

    def update_data_source(self, source_name: str, new_filename: str):
        """Update a data source and reload."""
        if source_name in self.data_sources:
            self.data_sources[source_name] = new_filename
            logger.info(f"📊 Updated {source_name} to use {new_filename}")
            self.load_all_data()
        else:
            logger.warning(f"⚠️ Unknown data source: {source_name}")

    def refresh_all_data(self):
        """Refresh all data from files."""
        logger.info("🔄 Refreshing all data sources...")
        self.load_all_data()
        logger.info("✅ Data refresh complete")


def create_data_driven_config() -> Dict[str, Any]:
    """Create configuration file for data-driven analytics."""
    config = {
        "data_sources": {
            "county_data": {
                "file": "enhanced_county_data.json",
                "description": "County-level budget, population, and performance data",
                "update_frequency": "monthly",
                "critical": True,
            },
            "audit_data": {
                "file": "oag_audit_data.json",
                "description": "Office of Auditor-General audit queries and findings",
                "update_frequency": "quarterly",
                "critical": True,
            },
            "budget_data": {
                "file": "comprehensive_government_reports.json",
                "description": "Government budget documents and reports",
                "update_frequency": "annually",
                "critical": True,
            },
        },
        "calculation_methods": {
            "transparency_score": "data_availability_weighted",
        },
        "update_notifications": {
            "email_alerts": False,
            "log_changes": True,
            "backup_old_data": True,
        },
    }

    return config


def main():
    """Test the data-driven analytics system."""
    analytics = DataDrivenGovernmentAnalytics()

    print("🏛️ DATA-DRIVEN GOVERNMENT ANALYTICS SYSTEM")
    print("=" * 50)

    # Test each component
    print("\n🏛️ COUNTY STATISTICS (from actual data):")
    county_stats = analytics.get_actual_county_statistics()
    print(f"Counties: {county_stats['total_counties']}")
    print(f"Data Available: {county_stats['data_available']}")
    if county_stats["data_available"]:
        print(f"Total County Budget: KES {county_stats['total_county_budget']:,}")

    print("\n🔍 AUDIT STATISTICS (from OAG data):")
    audit_stats = analytics.get_actual_audit_statistics()
    print(f"Audit Queries: {audit_stats['total_audit_queries']}")
    print(f"Data Available: {audit_stats['data_available']}")

    print("\n📈 TRANSPARENCY SCORE (from data availability):")
    print(f"Score: {analytics._calculate_transparency_score()}")

    # Save configuration
    config = create_data_driven_config()
    with open("data_driven_config.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"⚙️ Configuration saved to: data_driven_config.json")


if __name__ == "__main__":
    main()
