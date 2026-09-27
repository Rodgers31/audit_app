"""
Live Data Fetcher - Fetches real data from Kenya government sources.

This module provides live data fetchers that replace hardcoded data.
It integrates with the existing ETL infrastructure to get actual data
from official government sources.

Sources:
- KNBS: Kenya National Bureau of Statistics - Economic indicators
- Treasury: National Treasury - Budget allocations, debt bulletins
- COB: Controller of Budget - County budget implementation

DATA PRIORITY:
1. Live scraping from government sites
2. ETL pipeline cached data (from previous successful scrapes)
3. Cached JSON files from manual data collection

Population and debt ingestion are owned by dedicated seeding domains.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


logger = logging.getLogger("live_data_fetcher")

# Add project root to path for imports
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


class KNBSDataFetcher:
    """
    Fetches live data from Kenya National Bureau of Statistics.

    Uses the existing KNBSExtractor and KNBSParser from the ETL infrastructure.
    """

    def __init__(self):
        self.base_url = "https://www.knbs.or.ke"
        self._extractor = None
        self._parser = None

    def _get_extractor(self):
        """Lazy load the KNBS extractor."""
        if self._extractor is None:
            try:
                from extractors.government.knbs_extractor import KNBSExtractor

                self._extractor = KNBSExtractor()
            except ImportError as e:
                logger.warning(f"[KNBS] Could not import KNBSExtractor: {e}")
        return self._extractor

    def _get_parser(self):
        """Lazy load the KNBS parser."""
        if self._parser is None:
            try:
                from etl.knbs_parser import KNBSParser

                self._parser = KNBSParser()
            except ImportError as e:
                logger.warning(f"[KNBS] Could not import KNBSParser: {e}")
        return self._parser

    async def fetch_economic_indicators(self) -> Dict[str, Any]:
        """
        Fetch latest economic indicators from KNBS.

        Returns:
            Dict with GDP, inflation, and other economic data
        """
        logger.info("[KNBS] Fetching live economic indicators...")

        result = {
            "gdp_kes": None,
            "gdp_usd": None,
            "gdp_year": None,
            "gdp_growth_rate": None,
            "inflation_rate": None,
            "inflation_period": None,
            "unemployment_rate": None,
            "indicators": [],
            "source": "Kenya National Bureau of Statistics",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fetch_success": False,
        }

        extractor = self._get_extractor()
        parser = self._get_parser()

        if extractor:
            try:
                # discover_documents() is synchronous — run in thread
                documents = await asyncio.to_thread(extractor.discover_documents)

                # Look for economic survey, GDP reports, CPI
                for doc in documents:
                    title = doc.get("title", "").lower()
                    doc_type = doc.get("type", "")

                    if any(
                        kw in title
                        for kw in ["economic survey", "gdp", "cpi", "inflation"]
                    ):
                        logger.info(
                            f"[KNBS] Found economic document: {doc.get('title')}"
                        )

                        if parser:
                            parsed = await asyncio.to_thread(parser.parse_document, doc)
                            if parsed:
                                # Extract GDP data
                                for gdp in parsed.get("gdp_data", []):
                                    result["gdp_kes"] = gdp.get("gdp_value")
                                    result["gdp_year"] = gdp.get("year")
                                    result["gdp_growth_rate"] = gdp.get("growth_rate")

                                # Extract other indicators
                                for indicator in parsed.get("economic_indicators", []):
                                    result["indicators"].append(indicator)
                                    if indicator.get("indicator_type") == "inflation":
                                        result["inflation_rate"] = indicator.get(
                                            "value"
                                        )
                                        result["inflation_period"] = indicator.get(
                                            "period"
                                        )

                if (
                    result["gdp_kes"]
                    or result["inflation_rate"]
                    or result["indicators"]
                ):
                    result["fetch_success"] = True

            except Exception as e:
                logger.error(f"[KNBS] Error fetching economic indicators: {e}")
                result["error"] = str(e)

        return result

    async def fetch_county_data(self) -> List[Dict[str, Any]]:
        """
        Fetch county-level data from KNBS county statistical abstracts.

        NOTE: PDF parsing is slow, so this is designed for background refresh,
        not startup. For startup, we rely on existing database data.

        Returns:
            List of county data dictionaries
        """
        logger.info("[KNBS] County data fetch - checking for cached data...")

        # For now, return empty list - county entities are created from
        # KENYA_COUNTY_CODES and population data comes from census JSON
        # Full PDF parsing should happen in background, not startup

        # TODO: In a background task, use extract_county_statistical_abstracts()
        # to download and parse county PDFs for fresh data

        return []


class TreasuryDataFetcher:
    """
    Fetches budget and fiscal data from National Treasury.

    Uses the existing ETL pipeline's _discover_treasury() method.
    """

    def __init__(self):
        self.base_url = "https://www.treasury.go.ke"
        self._pipeline = None

    def _get_pipeline(self):
        """Lazy load the Kenya data pipeline."""
        if self._pipeline is None:
            try:
                from etl.kenya_pipeline import KenyaDataPipeline

                self._pipeline = KenyaDataPipeline()
            except ImportError as e:
                logger.warning(f"[Treasury] Could not import KenyaDataPipeline: {e}")
        return self._pipeline

    async def fetch_budget_data(self) -> Dict[str, Any]:
        """
        Fetch latest budget allocation data from Treasury.

        Returns:
            Dict with budget data including county allocations
        """
        logger.info("[Treasury] Fetching budget allocation data...")

        result = {
            "fiscal_year": None,
            "total_budget_kes": None,
            "county_allocations": [],
            "source": "National Treasury",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fetch_success": False,
        }

        pipeline = self._get_pipeline()

        if pipeline:
            try:
                # discover_budget_documents is synchronous — run in thread
                documents = await asyncio.to_thread(
                    pipeline.discover_budget_documents, "treasury"
                )

                for doc in documents:
                    title = doc.get("title", "").lower()

                    if any(
                        kw in title
                        for kw in [
                            "allocation",
                            "budget",
                            "cara",
                            "division of revenue",
                        ]
                    ):
                        logger.info(
                            f"[Treasury] Found budget document: {doc.get('title')}"
                        )

                        # Would process document here
                        # For now, mark as discovered
                        result["documents_found"] = result.get("documents_found", 0) + 1

                if result.get("documents_found", 0) > 0:
                    result["fetch_success"] = True

            except Exception as e:
                logger.error(f"[Treasury] Error fetching budget data: {e}")
                result["error"] = str(e)

        return result


class COBDataFetcher:
    """
    Fetches budget implementation data from Controller of Budget.

    Uses the existing ETL pipeline's _discover_cob() method.
    """

    def __init__(self):
        self.base_url = "https://www.cob.go.ke"
        self._pipeline = None

    def _get_pipeline(self):
        """Lazy load the Kenya data pipeline."""
        if self._pipeline is None:
            try:
                from etl.kenya_pipeline import KenyaDataPipeline

                self._pipeline = KenyaDataPipeline()
            except ImportError as e:
                logger.warning(f"[COB] Could not import KenyaDataPipeline: {e}")
        return self._pipeline

    async def fetch_county_budgets(self) -> List[Dict[str, Any]]:
        """
        Fetch county budget implementation reports from COB.

        Returns:
            List of county budget data
        """
        logger.info("[COB] Fetching county budget implementation data...")

        counties = []

        pipeline = self._get_pipeline()

        if pipeline:
            try:
                # discover_budget_documents is synchronous (uses requests lib)
                # so we MUST run it in a thread to avoid blocking the event loop.
                documents = await asyncio.to_thread(
                    pipeline.discover_budget_documents, "cob"
                )

                for doc in documents:
                    title = doc.get("title", "").lower()

                    # COB reports often have county names
                    if "county" in title or "implementation" in title:
                        logger.info(f"[COB] Found budget report: {doc.get('title')}")

            except Exception as e:
                logger.error(f"[COB] Error fetching county budgets: {e}")

        return counties


class LiveDataAggregator:
    """
    Aggregates data from all live fetchers.

    This is the main interface for the auto_seeder to get fresh data.
    """

    def __init__(self):
        self.knbs = KNBSDataFetcher()
        self.treasury = TreasuryDataFetcher()
        self.cob = COBDataFetcher()

    async def fetch_all_economic_data(self) -> Dict[str, Any]:
        """Fetch consolidated economic indicators."""
        return await self.knbs.fetch_economic_indicators()

    async def fetch_all_county_data(self) -> Tuple[List[Dict], List[Dict]]:
        """
        Fetch all county data from multiple sources.

        Returns:
            Tuple of (KNBS county data, COB budget data)
        """
        knbs_counties = await self.knbs.fetch_county_data()
        cob_budgets = await self.cob.fetch_county_budgets()
        return knbs_counties, cob_budgets


# Global instance
live_data_aggregator = LiveDataAggregator()
