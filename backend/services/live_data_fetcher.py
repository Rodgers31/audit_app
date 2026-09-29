"""Legacy discovery helpers used by the web worker's county reference refresh.

Population, debt and economic indicators are owned by dedicated seeding domains.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


logger = logging.getLogger("live_data_fetcher")


class KNBSDataFetcher:
    """County reference fetcher; population belongs to the census domain."""

    def __init__(self):
        self.base_url = "https://www.knbs.or.ke"

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
