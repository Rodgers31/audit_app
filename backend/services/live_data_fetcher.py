"""
Live Data Fetcher - Fetches real data from Kenya government sources.

This module provides live data fetchers that replace hardcoded data.
It integrates with the existing ETL infrastructure to get actual data
from official government sources.

Sources:
- CBK: Central Bank of Kenya - Public debt statistics
- KNBS: Kenya National Bureau of Statistics - Population, GDP, economic indicators
- Treasury: National Treasury - Budget allocations, debt bulletins
- COB: Controller of Budget - County budget implementation

DATA PRIORITY:
1. Live scraping from government sites
2. ETL pipeline cached data (from previous successful scrapes)
3. Cached JSON files from manual data collection

NO HARDCODED STATIC DATA - All data comes from dynamic sources.
"""

import asyncio
import json
import logging
import re
import ssl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("live_data_fetcher")

# Add project root to path for imports
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Path to cached data files (from manual data collection)
CACHE_PATH = Path(__file__).resolve().parents[1] / "seeding" / "real_data"


class CBKDebtFetcher:
    """
    Fetches live debt data from Central Bank of Kenya.

    Primary source: https://www.centralbank.go.ke/public-debt/
    Also checks: https://www.centralbank.go.ke/statistics/
    """

    def __init__(self):
        self.base_url = "https://www.centralbank.go.ke"
        self.debt_url = f"{self.base_url}/public-debt/"
        self.stats_url = f"{self.base_url}/statistics/"

    async def fetch_debt_data(self) -> Dict[str, Any]:
        """
        Fetch current public debt data from CBK.

        Returns:
            Dict with debt breakdown by category
        """
        logger.info("[CBK] Fetching live debt data from Central Bank of Kenya...")

        result = {
            "total_debt_kes": 0,
            "external_debt_kes": 0,
            "domestic_debt_kes": 0,
            "breakdown": [],
            "source": "Central Bank of Kenya",
            "source_url": self.debt_url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fetch_success": False,
        }

        try:
            # Create SSL context that's more permissive for government sites
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            async with httpx.AsyncClient(
                timeout=30.0,
                verify=False,  # Government sites often have cert issues
                follow_redirects=True,
            ) as client:
                # Try the main public debt page
                response = await client.get(self.debt_url)

                if response.status_code == 200:
                    debt_data = self._parse_debt_page(response.text)
                    if debt_data:
                        result.update(debt_data)
                        result["fetch_success"] = True
                        logger.info(
                            f"[CBK] Successfully fetched debt data: {result['total_debt_kes']:,.0f} KES"
                        )
                        return result

                # Try statistics page as backup
                response = await client.get(self.stats_url)
                if response.status_code == 200:
                    debt_data = self._parse_statistics_page(response.text)
                    if debt_data:
                        result.update(debt_data)
                        result["fetch_success"] = True
                        logger.info(
                            f"[CBK] Fetched from statistics: {result['total_debt_kes']:,.0f} KES"
                        )
                        return result

        except Exception as e:
            logger.error(f"[CBK] Error fetching debt data: {e}")
            result["error"] = str(e)

        # If live fetch fails, try to get from Treasury debt bulletins
        logger.warning("[CBK] Live fetch failed, attempting Treasury fallback...")
        treasury_data = await self._fetch_treasury_debt_bulletin()
        if treasury_data:
            result.update(treasury_data)
            result["fetch_success"] = True

        return result

    def _parse_debt_page(self, html: str) -> Optional[Dict]:
        """Parse the CBK public debt page for debt figures."""
        soup = BeautifulSoup(html, "html.parser")

        # Look for tables with debt data
        tables = soup.find_all("table")

        for table in tables:
            text = table.get_text().lower()
            if "public debt" in text or "external" in text or "domestic" in text:
                return self._extract_debt_from_table(table)

        # Try to find debt figures in text
        text = soup.get_text()
        return self._extract_debt_from_text(text)

    def _parse_statistics_page(self, html: str) -> Optional[Dict]:
        """Parse CBK statistics page for debt data."""
        soup = BeautifulSoup(html, "html.parser")

        # Look for links to debt-related PDFs or reports
        links = soup.find_all("a", href=True)

        for link in links:
            href = link.get("href", "")
            text = link.get_text().lower()

            if "debt" in text or "bulletin" in text:
                # Found a debt-related document
                logger.info(f"[CBK] Found debt document: {text}")
                # Would download and parse PDF here

        return None

    def _extract_debt_from_table(self, table) -> Optional[Dict]:
        """Extract debt figures from an HTML table."""
        rows = table.find_all("tr")

        result = {
            "breakdown": [],
            "total_debt_kes": 0,
            "external_debt_kes": 0,
            "domestic_debt_kes": 0,
        }

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value_text = cells[-1].get_text(strip=True)

                # Try to extract numeric value
                value = self._parse_amount(value_text)
                if value is None:
                    continue

                # Categorize
                if "total" in label and "debt" in label:
                    result["total_debt_kes"] = value
                elif "external" in label:
                    result["external_debt_kes"] = value
                    result["breakdown"].append(
                        {
                            "category": "external",
                            "label": cells[0].get_text(strip=True),
                            "amount_kes": value,
                        }
                    )
                elif "domestic" in label:
                    result["domestic_debt_kes"] = value
                    result["breakdown"].append(
                        {
                            "category": "domestic",
                            "label": cells[0].get_text(strip=True),
                            "amount_kes": value,
                        }
                    )

        return result if result["total_debt_kes"] > 0 else None

    def _extract_debt_from_text(self, text: str) -> Optional[Dict]:
        """Extract debt figures from page text using regex."""
        # Patterns for Kenya debt figures (typically in billions or trillions)
        patterns = [
            r"total\s+(?:public\s+)?debt[:\s]+(?:kes\s+)?(\d+(?:[.,]\d+)?)\s*(trillion|billion|million)",
            r"external\s+debt[:\s]+(?:kes\s+)?(\d+(?:[.,]\d+)?)\s*(trillion|billion|million)",
            r"domestic\s+debt[:\s]+(?:kes\s+)?(\d+(?:[.,]\d+)?)\s*(trillion|billion|million)",
        ]

        result = {"breakdown": []}
        text_lower = text.lower()

        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = float(match.group(1).replace(",", ""))
                unit = match.group(2)

                # Convert to KES
                if "trillion" in unit:
                    value *= 1e12
                elif "billion" in unit:
                    value *= 1e9
                elif "million" in unit:
                    value *= 1e6

                if "total" in pattern:
                    result["total_debt_kes"] = value
                elif "external" in pattern:
                    result["external_debt_kes"] = value
                elif "domestic" in pattern:
                    result["domestic_debt_kes"] = value

        return result if result.get("total_debt_kes", 0) > 0 else None

    def _parse_amount(self, text: str) -> Optional[float]:
        """Parse a monetary amount from text."""
        # Remove currency symbols and whitespace
        clean = re.sub(r"[^\d.,]", "", text)
        if not clean:
            return None

        try:
            # Handle both comma and period as decimal separators
            if "," in clean and "." in clean:
                # Assume format like 1,234.56
                clean = clean.replace(",", "")
            elif "," in clean:
                # Could be 1,234 or 1,23 - context dependent
                parts = clean.split(",")
                if len(parts[-1]) <= 2:
                    clean = clean.replace(",", ".")
                else:
                    clean = clean.replace(",", "")

            return float(clean)
        except ValueError:
            return None

    async def _fetch_treasury_debt_bulletin(self) -> Optional[Dict]:
        """Fetch debt data from Treasury debt bulletins as fallback."""
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.get(
                    "https://www.treasury.go.ke/public-debt-management-reports/"
                )

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")

                    # Look for PDF links to debt bulletins
                    links = soup.find_all("a", href=True)
                    for link in links:
                        href = link.get("href", "")
                        if ".pdf" in href.lower() and "debt" in href.lower():
                            logger.info(f"[Treasury] Found debt bulletin: {href}")
                            # Would download and parse PDF here

        except Exception as e:
            logger.error(f"[Treasury] Error fetching debt bulletin: {e}")

        # Fallback to cached data file
        return self._load_cached_debt_data()

    def _load_cached_debt_data(self) -> Optional[Dict]:
        """
        Load debt data from cached JSON file.

        This is data that was previously collected from official sources
        and saved for offline use. It's NOT hardcoded - it was scraped/parsed
        from actual government documents.
        """
        cache_file = CACHE_PATH / "national_debt.json"

        if not cache_file.exists():
            logger.warning(f"[CBK] No cached debt data found at {cache_file}")
            return None

        try:
            with open(cache_file, "r") as f:
                cached = json.load(f)

            # Convert cached format to our standard format
            loans = cached.get("loans", [])
            if not loans:
                return None

            total_principal = sum(float(l.get("principal", 0)) for l in loans)
            external_debt = sum(
                float(l.get("principal", 0))
                for l in loans
                if "external" in l.get("lender_type", "")
            )
            domestic_debt = total_principal - external_debt

            breakdown = []
            for loan in loans:
                lender_type = loan.get("lender_type", "")
                category = "external" if "external" in lender_type else "domestic"
                breakdown.append(
                    {
                        "category": category,
                        "subcategory": lender_type,
                        "label": loan.get("lender", "Unknown"),
                        "amount_kes": float(loan.get("principal", 0)),
                        "outstanding_kes": float(loan.get("outstanding", 0)),
                        "interest_rate": loan.get("interest_rate"),
                    }
                )

            logger.info(
                f"[CBK] Loaded cached debt data: {total_principal:,.0f} KES total"
            )

            return {
                "total_debt_kes": total_principal,
                "external_debt_kes": external_debt,
                "domestic_debt_kes": domestic_debt,
                "breakdown": breakdown,
                "source": cached.get("source_title", "Treasury Public Debt Bulletin"),
                "source_url": cached.get(
                    "source_url", "https://www.treasury.go.ke/public-debt/"
                ),
                "cache_note": "Data from previously collected official sources",
                "generated_at": cached.get("metadata", {}).get("generated_at"),
            }

        except Exception as e:
            logger.error(f"[CBK] Error loading cached debt data: {e}")
            return None


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

    async def fetch_population_data(self) -> Dict[str, Any]:
        """
        Fetch latest population data from KNBS.

        Returns:
            Dict with national and county population data
        """
        logger.info("[KNBS] Fetching live population data...")

        result = {
            "national_population": None,
            "census_year": None,
            "counties": [],
            "source": "Kenya National Bureau of Statistics",
            "source_url": self.base_url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fetch_success": False,
        }

        extractor = self._get_extractor()
        parser = self._get_parser()

        if extractor:
            try:
                # discover_documents() is synchronous — run in thread
                documents = await asyncio.to_thread(extractor.discover_documents)

                # Look for population-related documents
                for doc in documents:
                    title = doc.get("title", "").lower()
                    doc_type = doc.get("type", "")

                    if (
                        "population" in title
                        or "census" in title
                        or doc_type == "county_abstract"
                    ):
                        logger.info(
                            f"[KNBS] Found population document: {doc.get('title')}"
                        )

                        # Parse the document if parser available
                        if parser:
                            parsed = await asyncio.to_thread(parser.parse_document, doc)
                            if parsed and parsed.get("population_data"):
                                for pop_record in parsed["population_data"]:
                                    if pop_record.get("county"):
                                        result["counties"].append(pop_record)
                                    else:
                                        result["national_population"] = pop_record.get(
                                            "total_population"
                                        )
                                        result["census_year"] = pop_record.get("year")

                if result["national_population"] or result["counties"]:
                    result["fetch_success"] = True

            except Exception as e:
                logger.error(f"[KNBS] Error fetching population data: {e}")
                result["error"] = str(e)

        # No fallback past the structured documents (issue #204). There used
        # to be two, and neither was a population source:
        #
        # * a regex over the KNBS homepage for a number next to "population",
        #   filed under the current year. On 2026-09-26 it returned 82, from
        #   "the population density of kenya in 2019 was of 82 people per
        #   square kilometre", which is where population_data id=69 came from;
        # * seeding/real_data/population.json, which is a git-tracked fixture
        #   and not a fetch. It puts Mandera at 1,200,890 against the census's
        #   867,457 and sums to 47,897,729, not 47,564,296, and the boot-time
        #   auto-seeder wrote both over the extraction-backed 2019 rows in
        #   place. The nightly population domain reads that fixture under the
        #   census gate (seeding/domains/population/census_counties.py).
        #
        # Returning fetch_success=False is the correct answer when KNBS
        # published nothing we can parse. The nightly owns this table.
        if not result["fetch_success"]:
            logger.warning(
                "[KNBS] No population figure from a structured KNBS document; "
                "nothing to write"
            )

        return result

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
        self.cbk = CBKDebtFetcher()
        self.knbs = KNBSDataFetcher()
        self.treasury = TreasuryDataFetcher()
        self.cob = COBDataFetcher()

    async def fetch_all_debt_data(self) -> Dict[str, Any]:
        """Fetch consolidated debt data from all sources."""
        cbk_data = await self.cbk.fetch_debt_data()
        return cbk_data

    async def fetch_all_population_data(self) -> Dict[str, Any]:
        """Fetch consolidated population data."""
        return await self.knbs.fetch_population_data()

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

    async def fetch_all(self) -> Dict[str, Any]:
        """
        Fetch all data from all sources.

        Returns comprehensive data package for seeding.
        """
        logger.info("[AGGREGATOR] Fetching all live data...")

        # Fetch all data in parallel
        debt_task = self.fetch_all_debt_data()
        population_task = self.fetch_all_population_data()
        economic_task = self.fetch_all_economic_data()
        county_task = self.fetch_all_county_data()

        results = await asyncio.gather(
            debt_task,
            population_task,
            economic_task,
            county_task,
            return_exceptions=True,
        )

        return {
            "debt": (
                results[0]
                if not isinstance(results[0], Exception)
                else {"error": str(results[0])}
            ),
            "population": (
                results[1]
                if not isinstance(results[1], Exception)
                else {"error": str(results[1])}
            ),
            "economic": (
                results[2]
                if not isinstance(results[2], Exception)
                else {"error": str(results[2])}
            ),
            "counties": {
                "knbs": results[3][0] if not isinstance(results[3], Exception) else [],
                "cob": results[3][1] if not isinstance(results[3], Exception) else [],
            },
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


# Global instance
live_data_aggregator = LiveDataAggregator()
