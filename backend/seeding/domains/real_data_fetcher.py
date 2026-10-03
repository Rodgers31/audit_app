"""
Real Data Fetcher - DEPRECATED

This script was used to generate initial fixture files from hardcoded data.
It is no longer the primary data source.

The unsupported legacy inflation alias is retired and is deliberately omitted
from this historical fixture generator. Maintained inflation comes from the
economic_indicators domain's World Bank and CBK fetchers, not these literals.

The seeding pipeline now fetches live data from:
- World Bank API (population, GDP, inflation, unemployment, CPI)
- CBK website (debt bulletins via PDF scraping)
- COB website (budget implementation reports via PDF scraping)
- OAG website (audit reports via PDF scraping)

Fixture files in seeding/real_data/ serve only as FALLBACKS when
live APIs are unreachable. See each domain's fetcher.py for details.

To refresh fixture files from live sources, use:
    python -m seeding.cli seed --all --dry-run
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RealDataFetcher:
    """Fetches real Kenya government data for seeding domains."""

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or str(
            project_root / "backend" / "seeding" / "real_data"
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_knbs_economic_indicators(self) -> List[Dict]:
        """
        Fetch real economic indicators from KNBS.

        Returns list of economic indicator records in seeding-compatible format:
        {
            "indicator_type": "gdp_growth_rate",
            "date": "2023-09-30",
            "value": 5.4,
            "unit": "percent",
            "source_url": "https://www.knbs.or.ke/...",
            "source": "KNBS Quarterly GDP Report Q3 2023"
        }
        """
        logger.info("📊 Fetching KNBS economic indicators...")

        # For MVP: Use recent actual figures from KNBS reports
        # These are REAL figures from published KNBS reports
        indicators = [
            {
                "indicator_type": "gdp_growth_rate",
                "date": "2023-09-30",  # Q3 2023 end date
                "value": 5.4,
                "unit": "percent",
                "source_url": "https://www.knbs.or.ke/download/quarterly-gross-domestic-product-report-third-quarter-2023/",
                "source": "KNBS Quarterly GDP Report Q3 2023",
                "data_quality": "official",
                "notes": "Real growth rate from KNBS published report",
            },
            {
                "indicator_type": "total_national_gdp",
                "date": "2023-12-31",  # Annual 2023
                "value": 13896000,  # 13.896 trillion KES represented in millions
                "unit": "KES_millions",
                "source_url": "https://www.knbs.or.ke/economic-survey-2024/",
                "source": "KNBS Economic Survey 2024",
                "data_quality": "official",
                "notes": "Nominal GDP in Kenya Shillings (value in millions: 13,896,000 million = 13.896 trillion)",
            },
            {
                "indicator_type": "unemployment_rate",
                "date": "2023-12-31",  # Annual 2023
                "value": 5.6,
                "unit": "percent",
                "source_url": "https://www.knbs.or.ke/labour-force-basic-report/",
                "source": "KNBS Labour Force Report 2023",
                "data_quality": "official",
                "notes": "National unemployment rate",
            },
        ]

        # Save to JSON
        output_file = os.path.join(self.output_dir, "economic_indicators.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(indicators, f, indent=2)

        logger.info(f"✅ Saved {len(indicators)} economic indicators to {output_file}")
        return indicators

    def generate_all_real_data(self):
        """Generate all available real data from government sources."""
        logger.info("🏛️ GENERATING ALL REAL KENYA GOVERNMENT DATA")
        logger.info("=" * 80)

        results = {
            "economic_indicators": self.fetch_knbs_economic_indicators(),
        }

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("✅ REAL DATA GENERATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"📈 Economic indicators: {len(results['economic_indicators'])}")
        logger.info(f"📁 Output directory: {self.output_dir}")
        logger.info("\nNext steps:")
        logger.info("1. Update .env to point seeding domains to these files")
        logger.info(
            "3. Run 'python -m backend.seeding.cli seed --domain economic_indicators'"
        )
        logger.info("4. Verify database contains real government data")

        return results


if __name__ == "__main__":
    fetcher = RealDataFetcher()
    results = fetcher.generate_all_real_data()

    print(f"\n✅ Real data files generated in: {fetcher.output_dir}/")
    print(
        f"   - economic_indicators.json ({len(results['economic_indicators'])} records)"
    )
    print("\n🎯 This is REAL Kenya government data, not test fixtures!")
