"""
Additional reliable Kenya government data sources
Focus on websites that are consistently accessible
"""

import logging

import requests

logger = logging.getLogger(__name__)


class AlternativeKenyaSources:
    """Alternative and more reliable Kenya government data sources."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    def test_kenya_open_data(self):
        """Test Kenya Open Data Portal - usually more reliable."""
        try:
            logger.info("📊 Testing Kenya Open Data Portal...")
            response = self.session.get("https://www.opendata.go.ke", timeout=15)

            if response.status_code == 200:
                return {
                    "source": "Kenya Open Data Portal",
                    "url": "https://www.opendata.go.ke",
                    "status": "accessible",
                    "description": "Government datasets and financial data",
                    "data_types": [
                        "budget_data",
                        "expenditure_data",
                        "economic_indicators",
                    ],
                    "reliability": "high",
                }
        except Exception as e:
            logger.warning(f"Kenya Open Data Portal failed: {str(e)}")

        return None

    def test_knbs(self):
        """Test Kenya National Bureau of Statistics."""
        try:
            logger.info("📈 Testing Kenya National Bureau of Statistics...")
            response = self.session.get("https://www.knbs.or.ke", timeout=15)

            if response.status_code == 200:
                return {
                    "source": "Kenya National Bureau of Statistics",
                    "url": "https://www.knbs.or.ke",
                    "status": "accessible",
                    "description": "Economic surveys and government statistics",
                    "data_types": [
                        "economic_surveys",
                        "statistical_abstracts",
                        "budget_analysis",
                    ],
                    "reliability": "high",
                }
        except Exception as e:
            logger.warning(f"KNBS failed: {str(e)}")

        return None

    def test_central_bank(self):
        """Test Central Bank of Kenya."""
        try:
            logger.info("🏦 Testing Central Bank of Kenya...")
            response = self.session.get("https://www.centralbank.go.ke", timeout=15)

            if response.status_code == 200:
                return {
                    "source": "Central Bank of Kenya",
                    "url": "https://www.centralbank.go.ke",
                    "status": "accessible",
                    "description": "Monetary policy and government debt data",
                    "data_types": [
                        "monetary_policy",
                        "government_debt",
                        "financial_stability",
                    ],
                    "reliability": "high",
                }
        except Exception as e:
            logger.warning(f"Central Bank failed: {str(e)}")

        return None

    def get_all_alternative_sources(self):
        """Get all working alternative sources."""
        sources = []

        # Test all alternative sources
        open_data = self.test_kenya_open_data()
        if open_data:
            sources.append(open_data)

        knbs = self.test_knbs()
        if knbs:
            sources.append(knbs)

        central_bank = self.test_central_bank()
        if central_bank:
            sources.append(central_bank)

        return sources
