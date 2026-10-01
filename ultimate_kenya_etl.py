"""Observe government source availability and document links.

These legacy checkers do not extract financial observations. An accessible
homepage or a discovered PDF link supplies no evidence for budgets or audits.
"""

import argparse
import json
from datetime import datetime

from comprehensive_kenya_etl import ComprehensiveKenyaETL
from tools.alternative_sources import AlternativeKenyaSources


class UltimateKenyaETL:
    """Combine source checks without generating financial records or quality scores."""

    def __init__(self):
        self.primary_etl = ComprehensiveKenyaETL()
        self.alternative_sources = AlternativeKenyaSources()
        self.results = {}

    def run_primary_collection(self):
        """Retain actual Treasury and Parliament access/link observations."""
        self.results["primary_sources"] = {
            "treasury": self.primary_etl.test_treasury_comprehensive(),
            "parliament": self.primary_etl.test_parliament_budget_office(),
        }

    def run_alternative_collection(self):
        """Retain accessible alternative sources, without inferring data quality."""
        self.results[
            "alternative_sources"
        ] = self.alternative_sources.get_all_alternative_sources()

    def run_ultimate_collection(self):
        """Check two primary and three alternative sources; financial data is absent."""
        self.results = {
            "primary_sources": {},
            "alternative_sources": [],
            "combined_summary": {},
            "comprehensive_data": None,
            "financial_data_status": "not_extracted",
            "timestamp": datetime.now().isoformat(),
        }
        self.run_primary_collection()
        self.run_alternative_collection()
        primary_working = sum(
            s.get("accessible") is True
            for s in self.results["primary_sources"].values()
        )
        alternative_working = sum(
            s.get("status") == "accessible" for s in self.results["alternative_sources"]
        )
        total_working = primary_working + alternative_working
        failures = 5 - total_working
        self.results["combined_summary"] = {
            "total_sources_attempted": 5,
            "primary_sources_working": primary_working,
            "alternative_sources_working": alternative_working,
            "total_sources_working": total_working,
            "errors_encountered": failures,
        }
        self.results["pipeline_status"] = (
            "source_checks_failed" if failures else "source_checks_completed"
        )
        return self.results


def main():
    """Save source checks and return failure when a source could not be checked."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="ultimate_etl_results.json")
    args = parser.parse_args()
    results = UltimateKenyaETL().run_ultimate_collection()
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Source observations saved to: {args.output}; financial data not extracted")
    return results


if __name__ == "__main__":
    raise SystemExit(1 if main()["combined_summary"]["errors_encountered"] else 0)
