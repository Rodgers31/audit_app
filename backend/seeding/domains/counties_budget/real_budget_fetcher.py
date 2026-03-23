"""
Real Budget Data Fetcher - DEPRECATED

This script was used to generate the initial budgets.json fixture from
hardcoded county population data and CRA formula estimates.

The seeding pipeline now fetches live budget data from:
- COB (Controller of Budget) quarterly C-BIRR PDF reports
- Fixture files serve only as FALLBACK when live sources are unreachable

See counties_budget/fetcher.py for the live implementation.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).resolve().parents[4]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RealBudgetDataFetcher:
    """Fetches real county budget data from government allocations and estimates."""

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or str(
            project_root / "backend" / "seeding" / "real_data"
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_county_budget_allocations(self) -> List[Dict]:
        """
        Generate realistic county budget allocations based on:
        1. Commission on Revenue Allocation (CRA) formulas
        2. County population data
        3. Historical budget patterns
        4. Kenya's equitable share distribution framework

        NOTE: These are ESTIMATED based on real government frameworks.
        For actual executed budgets, parse CoB quarterly reports when available.
        """
        logger.info("💰 Generating realistic county budget allocations...")

        # Kenya's county equitable share for FY 2023/24 was ~385 billion KES
        # Distribution formula: 50% population, 18% poverty, 8% land area, etc.
        total_equitable_share = 385000000000  # 385 billion KES

        # Population data from KNBS 2019 census (total ~47.6 million)
        county_populations = {
            "Nairobi": 4397073,
            "Mombasa": 1208333,
            "Kwale": 866820,
            "Kilifi": 1453787,
            "Tana River": 315943,
            "Lamu": 143920,
            "Taita Taveta": 340671,
            "Garissa": 841353,
            "Wajir": 781263,
            "Mandera": 1200890,
            "Marsabit": 459785,
            "Isiolo": 268002,
            "Meru": 1545714,
            "Tharaka Nithi": 393177,
            "Embu": 608599,
            "Kitui": 1136187,
            "Machakos": 1421932,
            "Makueni": 987653,
            "Nyandarua": 638289,
            "Nyeri": 759164,
            "Kirinyaga": 610411,
            "Murang'a": 1056640,
            "Kiambu": 2417735,
            "Turkana": 926976,
            "West Pokot": 621241,
            "Samburu": 310327,
            "Trans Nzoia": 990341,
            "Uasin Gishu": 1163186,
            "Elgeyo Marakwet": 454480,
            "Nandi": 885711,
            "Baringo": 666763,
            "Laikipia": 518560,
            "Nakuru": 2162202,
            "Narok": 1157873,
            "Kajiado": 1117840,
            "Kericho": 901777,
            "Bomet": 875689,
            "Kakamega": 1867579,
            "Vihiga": 590013,
            "Bungoma": 1670570,
            "Busia": 893681,
            "Siaya": 993183,
            "Kisumu": 1155574,
            "Homa Bay": 1131950,
            "Migori": 1116436,
            "Kisii": 1266860,
            "Nyamira": 605576,
        }

        total_population = sum(county_populations.values())

        budget_records = []
        fiscal_year = "2023/2024"
        start_date = "2023-07-01"  # Kenya FY starts July 1
        end_date = "2024-06-30"  # Kenya FY ends June 30

        for county_name, population in county_populations.items():
            # Calculate allocation using simplified CRA formula
            # 50% based on population
            population_share = (
                (population / total_population) * 0.50 * total_equitable_share
            )

            # 50% equal share (base allocation) - approximately 4.1B per county
            equal_share = total_equitable_share * 0.50 / 47

            # Total allocation
            total_allocation = population_share + equal_share

            # Generate slug matching database format
            slug = county_name.lower().replace(" ", "-").replace("'", "") + "-county"

            # Create realistic sector breakdown (Health ~25%, Education ~20%, etc.)
            sectors = {
                "Health Services": total_allocation * 0.25,
                "Education": total_allocation * 0.20,
                "Roads and Public Works": total_allocation * 0.15,
                "Water and Sanitation": total_allocation * 0.10,
                "Agriculture": total_allocation * 0.08,
                "Administration": total_allocation * 0.07,
                "Trade and Industry": total_allocation * 0.05,
                "Environment": total_allocation * 0.04,
                "Social Services": total_allocation * 0.03,
                "Other": total_allocation * 0.03,
            }

            # Create records for each sector
            for sector, amount in sectors.items():
                record = {
                    "entity_slug": slug,
                    "entity": county_name,
                    "fiscal_year": fiscal_year,
                    "start_date": start_date,
                    "end_date": end_date,
                    "category": sector,
                    "allocated_amount": round(amount, 2),
                    "source": "Estimated based on CRA Equitable Share FY 2023/24",
                    "source_url": "https://www.crakenya.org/county-allocations/",
                    "data_quality": "estimated",
                    "notes": f"Allocation estimated using CRA formula (50% population-based, 50% equal share). Total county allocation: {round(total_allocation/1e9, 2)}B KES",
                }
                budget_records.append(record)

        # Save to JSON
        output_file = os.path.join(self.output_dir, "budgets.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(budget_records, f, indent=2)

        logger.info(
            f"✅ Generated {len(budget_records)} budget records for 47 counties"
        )
        logger.info(f"   Total allocation: {total_equitable_share/1e9:.1f}B KES")
        logger.info(f"   Records per county: {len(budget_records)//47} sectors")
        logger.info(f"   Saved to: {output_file}")

        return budget_records


if __name__ == "__main__":
    fetcher = RealBudgetDataFetcher()
    results = fetcher.fetch_county_budget_allocations()

    print(f"\n✅ Real budget data generated!")
    print(f"   Counties: 47")
    print(f"   Total records: {len(results)}")
    print(f"   Fiscal Year: 2023/2024")
    print("\n🎯 Data Quality: ESTIMATED based on real CRA framework")
    print("   Source: Commission on Revenue Allocation equitable share formula")
    print("   Formula: 50% population-based + 50% equal share across counties")
    print(
        "\n📝 Note: For actual executed budgets, integrate CoB PDF reports using CoBQuarterlyReportParser"
    )
