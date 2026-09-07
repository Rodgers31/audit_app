"""
KNBS Parser Module
Parses economic data from Kenya National Bureau of Statistics publications.
Extracts population data, GDP figures, inflation rates, poverty indices, and other economic indicators.
"""

import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# What a year is, and what a population is
#
# These bound two columns this parser reads by header substring. It
# matched the header "Years and abov" — a fragment of the shattered
# TITLE of Table 1.2.1 in a county Statistical Abstract — as a year
# column, and "f Population A" as a population column, then wrote
# whatever integers those columns held. That produced twelve rows for
# Samburu from source_document 524: eleven with years 130, 135, 220,
# 232, 252, 335, 396, 399, 531, 621 and 897, and one at 20,317,126
# people against the county's real 310,327.
# ──────────────────────────────────────────────────────────────────

#: KNBS publishes contemporary statistics; nothing it reports is dated
#: outside this range, so an integer outside it is not a year at all.
MIN_DATA_YEAR = 1900
MAX_DATA_YEAR = 2100

#: Kenya's largest county at the 2019 census is Nairobi, 4,397,073.
#: The ceiling carries headroom for growth. A larger figure inside a
#: single county's abstract is a national aggregate, a different
#: metric, or a column we misread — it is not that county's population.
MAX_COUNTY_POPULATION = 6_000_000

#: Kenya's own population, for documents that are about the country.
MIN_NATIONAL_POPULATION = 10_000_000
MAX_NATIONAL_POPULATION = 100_000_000

#: Below this a "population" is a sample, a household count or a stray
#: cell rather than the population of a place we publish.
MIN_PLAUSIBLE_POPULATION = 10_000


def _parse_calendar_year(cell: Any) -> Optional[int]:
    """The calendar year stated in ``cell``, or ``None`` if it states none.

    Accepts a bare year and the leading year of a range or fiscal label
    ("2019", "2019/20", "2019-20"). Returns ``None`` for anything else —
    an age, a count, a code — rather than coercing it with ``int()``.
    """
    if cell is None:
        return None
    text = str(cell).strip()
    if not text:
        return None
    match = re.search(r"\b(1[89]\d{2}|20\d{2})\b", text)
    if match is None:
        return None
    year = int(match.group(1))
    return year if MIN_DATA_YEAR <= year <= MAX_DATA_YEAR else None


def _column_holds_years(table: List[List], col: int) -> bool:
    """Whether column ``col`` actually contains calendar years.

    A header can only be trusted about its own column once the column
    agrees with it. Every non-empty cell must parse as a year, and there
    must be at least one — an empty column proves nothing.
    """
    seen = 0
    for row in table[1:]:
        if not row or len(row) <= col:
            continue
        cell = row[col]
        if cell is None or not str(cell).strip():
            continue
        seen += 1
        if _parse_calendar_year(cell) is None:
            return False
    return seen > 0


@dataclass
class EconomicIndicator:
    """Data class for economic indicator."""

    indicator_type: str
    value: float
    period: str  # "2025-Q2", "2025-05", "2025"
    county: Optional[str] = None
    unit: Optional[str] = None
    source_page: Optional[int] = None
    confidence: float = 1.0


@dataclass
class PopulationData:
    """Data class for population data."""

    total_population: int
    year: int
    county: Optional[str] = None
    male_population: Optional[int] = None
    female_population: Optional[int] = None
    urban_population: Optional[int] = None
    rural_population: Optional[int] = None
    population_density: Optional[float] = None
    source_page: Optional[int] = None


@dataclass
class GDPData:
    """Data class for GDP data."""

    gdp_value: float
    year: int
    quarter: Optional[str] = None
    growth_rate: Optional[float] = None
    county: Optional[str] = None  # For Gross County Product
    source_page: Optional[int] = None


class KNBSParser:
    """Parser for KNBS publications - extracts economic data from PDFs."""

    def __init__(self):
        self.counties = [
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

    def parse_document(self, document_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point for parsing a KNBS document.

        Args:
            document_metadata: Document metadata from KNBSExtractor

        Returns:
            Dict with parsed economic data
        """
        logger.info(f"📄 Parsing: {document_metadata.get('title', 'Unknown')}")

        doc_type = document_metadata.get("type", "unknown")
        url = document_metadata.get("url")

        if not url:
            logger.error("[ERROR] No URL provided")
            return {}

        # Download PDF
        pdf_content = self._download_pdf(url)
        if not pdf_content:
            return {}

        # Parse based on document type
        if doc_type == "economic_survey":
            return self.parse_economic_survey(pdf_content, document_metadata)
        elif doc_type == "statistical_abstract":
            return self.parse_statistical_abstract(pdf_content, document_metadata)
        elif doc_type == "county_statistical_abstract" or doc_type == "county_abstract":
            return self.parse_county_abstract(pdf_content, document_metadata)
        elif "gdp" in doc_type.lower() or doc_type == "quarterly_gdp":
            return self.parse_gdp_report(pdf_content, document_metadata)
        elif "cpi" in doc_type.lower() or "inflation" in doc_type.lower():
            return self.parse_cpi_inflation(pdf_content, document_metadata)
        elif doc_type == "facts_and_figures":
            return self.parse_facts_and_figures(pdf_content, document_metadata)
        else:
            return self.parse_general_publication(pdf_content, document_metadata)

    def parse_economic_survey(self, pdf_content: bytes, metadata: Dict) -> Dict:
        """Parse Economic Survey - comprehensive annual report."""
        logger.info("📊 Parsing Economic Survey...")

        extracted_data = {
            "document_type": "economic_survey",
            "year": metadata.get("year"),
            "population_data": [],
            "gdp_data": [],
            "economic_indicators": [],
            "raw_text_sample": None,
        }

        # Extract text from PDF (for narrative data)
        text = self._extract_text_from_pdf(pdf_content)
        if text:
            extracted_data["raw_text_sample"] = text[
                :20000
            ]  # First 20000 chars for verification

        # Extract key economic indicators from text
        indicators = self._extract_economic_indicators_from_text(
            text, metadata.get("year")
        )
        extracted_data["economic_indicators"].extend(indicators)

        # Extract population data from text
        population = self._extract_population_from_text(text, metadata.get("year"))
        if population:
            extracted_data["population_data"].append(population.__dict__)

        # Extract GDP data from text
        gdp = self._extract_gdp_from_text(text, metadata.get("year"))
        if gdp:
            extracted_data["gdp_data"].append(gdp.__dict__)

        # ALSO extract tables using pdfplumber (Economic Surveys have data in tables!)
        if pdfplumber:
            logger.info("📊 Extracting tables from Economic Survey...")
            tables = self._extract_tables_from_pdf(pdf_content)
            extracted_data["tables_extracted"] = len(tables)

            logger.info(f"📊 Found {len(tables)} tables in Economic Survey")

            # Process each table
            for table in tables:
                try:
                    # Try to identify and parse the table
                    self._process_economic_survey_table(table, extracted_data, metadata)
                except Exception as e:
                    logger.warning(f"[WARN] Error processing table: {e}")
                    continue

        logger.info(
            f"[OK] Extracted {len(extracted_data['economic_indicators'])} indicators, {len(extracted_data['population_data'])} population records, {len(extracted_data['gdp_data'])} GDP records from Economic Survey"
        )
        return extracted_data

    def parse_statistical_abstract(self, pdf_content: bytes, metadata: Dict) -> Dict:
        """Parse Statistical Abstract - summary tables."""
        logger.info("📊 Parsing Statistical Abstract...")

        extracted_data = {
            "document_type": "statistical_abstract",
            "year": metadata.get("year"),
            "county": metadata.get("county"),
            "population_data": [],
            "economic_indicators": [],
            "tables_extracted": 0,
        }

        # Extract tables using pdfplumber
        if pdfplumber:
            tables = self._extract_tables_from_pdf(pdf_content)
            extracted_data["tables_extracted"] = len(tables)

            # Process tables to find population, GDP, and other indicators
            for table in tables:
                self._process_statistical_table(table, extracted_data, metadata)

        logger.info(
            f"[OK] Extracted {extracted_data['tables_extracted']} tables from Statistical Abstract"
        )
        return extracted_data

    def parse_county_abstract(self, pdf_content: bytes, metadata: Dict) -> Dict:
        """Parse County Statistical Abstract."""
        logger.info(f"🗺️ Parsing County Abstract: {metadata.get('county', 'Unknown')}")

        extracted_data = {
            "document_type": "county_abstract",
            "year": metadata.get("year"),
            "county": metadata.get("county"),
            "population_data": [],
            "gdp_data": [],  # Gross County Product
            "economic_indicators": [],
            "tables_extracted": 0,
        }

        text = self._extract_text_from_pdf(pdf_content)

        # Extract county-specific population
        population = self._extract_population_from_text(
            text, metadata.get("year"), metadata.get("county")
        )
        if population:
            extracted_data["population_data"].append(population.__dict__)

        # Extract Gross County Product (GCP)
        gcp = self._extract_county_gdp_from_text(
            text, metadata.get("year"), metadata.get("county")
        )
        if gcp:
            extracted_data["gdp_data"].append(gcp.__dict__)

        # Extract structured tables (many county metrics live in tables)
        if pdfplumber:
            tables = self._extract_tables_from_pdf(pdf_content)
            extracted_data["tables_extracted"] = len(tables)

            for table in tables:
                try:
                    self._process_statistical_table(table, extracted_data, metadata)
                except Exception as exc:
                    logger.debug(
                        "Failed processing county table for %s: %s",
                        metadata.get("county"),
                        exc,
                    )

        logger.info(f"[OK] Parsed county data for {metadata.get('county')}")
        return extracted_data

    def parse_gdp_report(self, pdf_content: bytes, metadata: Dict) -> Dict:
        """Parse Quarterly GDP Report."""
        logger.info(
            f"📈 Parsing GDP Report: Q{metadata.get('quarter', '?')} {metadata.get('year')}"
        )

        extracted_data = {
            "document_type": "quarterly_gdp",
            "year": metadata.get("year"),
            "quarter": metadata.get("quarter"),
            "gdp_data": [],
        }

        text = self._extract_text_from_pdf(pdf_content)

        # Extract GDP value and growth rate
        gdp = self._extract_gdp_from_text(
            text, metadata.get("year"), metadata.get("quarter")
        )
        if gdp:
            extracted_data["gdp_data"].append(gdp.__dict__)

        logger.info(f"[OK] Parsed GDP data")
        return extracted_data

    def parse_cpi_inflation(self, pdf_content: bytes, metadata: Dict) -> Dict:
        """Parse CPI/Inflation Report."""
        logger.info(f"📊 Parsing CPI/Inflation Report: {metadata.get('period')}")

        extracted_data = {
            "document_type": "cpi_inflation",
            "period": metadata.get("period"),
            "year": metadata.get("year"),
            "economic_indicators": [],
        }

        text = self._extract_text_from_pdf(pdf_content)

        # Extract inflation rate
        inflation_rate = self._extract_inflation_rate(text, metadata.get("period"))
        if inflation_rate:
            extracted_data["economic_indicators"].append(inflation_rate.__dict__)

        logger.info(f"[OK] Parsed CPI/Inflation data")
        return extracted_data

    def parse_facts_and_figures(self, pdf_content: bytes, metadata: Dict) -> Dict:
        """Parse Facts and Figures - quick reference summary."""
        logger.info("📖 Parsing Facts and Figures...")

        extracted_data = {
            "document_type": "facts_and_figures",
            "year": metadata.get("year"),
            "population_data": [],
            "gdp_data": [],
            "economic_indicators": [],
        }

        text = self._extract_text_from_pdf(pdf_content)

        # Extract key statistics
        indicators = self._extract_economic_indicators_from_text(
            text, metadata.get("year")
        )
        extracted_data["economic_indicators"] = indicators

        population = self._extract_population_from_text(text, metadata.get("year"))
        if population:
            extracted_data["population_data"].append(population.__dict__)

        gdp = self._extract_gdp_from_text(text, metadata.get("year"))
        if gdp:
            extracted_data["gdp_data"].append(gdp.__dict__)

        logger.info(f"[OK] Parsed Facts and Figures")
        return extracted_data

    def parse_general_publication(self, pdf_content: bytes, metadata: Dict) -> Dict:
        """Parse general KNBS publication."""
        logger.info("📄 Parsing general publication...")

        extracted_data = {
            "document_type": "general",
            "economic_indicators": [],
            "raw_text_sample": None,
        }

        text = self._extract_text_from_pdf(pdf_content)
        if text:
            extracted_data["raw_text_sample"] = text[:500]

        # Try to extract any recognizable economic indicators
        indicators = self._extract_economic_indicators_from_text(
            text, metadata.get("year")
        )
        extracted_data["economic_indicators"] = indicators

        return extracted_data

    # ===== Helper Methods =====

    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download PDF content from URL."""
        try:
            logger.info(f"⬇️ Downloading: {url[:60]}...")
            response = requests.get(url, timeout=30, verify=False)

            if response.status_code == 200:
                logger.info(f"[OK] Downloaded {len(response.content)} bytes")
                return response.content
            else:
                logger.error(f"[ERROR] Download failed: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"[ERROR] Download error: {str(e)}")
            return None

    def _extract_text_from_pdf(self, pdf_content: bytes) -> str:
        """Extract text from PDF using pdfplumber or PyPDF2."""
        text = ""

        # Try pdfplumber first (better text extraction)
        if pdfplumber:
            try:
                with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                    for page in pdf.pages[:20]:  # First 20 pages
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n\n"
                logger.info(f"📄 Extracted {len(text)} characters using pdfplumber")
                return text
            except Exception as e:
                logger.warning(f"[WARN] pdfplumber failed: {str(e)}")

        # Fallback to PyPDF2
        if PdfReader:
            try:
                pdf = PdfReader(io.BytesIO(pdf_content))
                for page in pdf.pages[:20]:  # First 20 pages
                    text += page.extract_text() + "\n\n"
                logger.info(f"📄 Extracted {len(text)} characters using PyPDF2")
                return text
            except Exception as e:
                logger.warning(f"[WARN] PyPDF2 failed: {str(e)}")

        return text

    def _extract_tables_from_pdf(self, pdf_content: bytes) -> List[List[List]]:
        """Extract tables from PDF using pdfplumber."""
        tables = []

        if not pdfplumber:
            return tables

        try:
            table_signatures = set()

            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                max_pages = min(len(pdf.pages), 120)
                for page_num, page in enumerate(pdf.pages[:max_pages], 1):
                    # Default extraction
                    page_tables = page.extract_tables()
                    if page_tables:
                        for table in page_tables:
                            if table and len(table) > 1:
                                signature = tuple(tuple(row[:3]) for row in table[:2])
                                if signature not in table_signatures:
                                    tables.append(table)
                                    table_signatures.add(signature)

                    # Try additional strategies for complex layouts
                    advanced_settings = [
                        {
                            "vertical_strategy": "lines",
                            "horizontal_strategy": "lines",
                            "intersection_x_tolerance": 5,
                            "intersection_y_tolerance": 5,
                        },
                        {
                            "vertical_strategy": "lines",
                            "horizontal_strategy": "text",
                            "keep_blank_chars": True,
                        },
                        {
                            "vertical_strategy": "text",
                            "horizontal_strategy": "text",
                            "snap_tolerance": 3,
                        },
                    ]

                    for settings in advanced_settings:
                        try:
                            adv_table = page.extract_table(table_settings=settings)
                            if adv_table and len(adv_table) > 1:
                                signature = tuple(
                                    tuple(row[:3]) for row in adv_table[:2]
                                )
                                if signature not in table_signatures:
                                    tables.append(adv_table)
                                    table_signatures.add(signature)
                        except Exception:
                            continue

            logger.info(f"📊 Extracted {len(tables)} tables")
        except Exception as e:
            logger.error(f"[ERROR] Table extraction error: {str(e)}")

        return tables

    def _extract_population_from_text(
        self, text: str, year: Optional[int], county: Optional[str] = None
    ) -> Optional[PopulationData]:
        """Extract population data from text with enhanced patterns.

        National documents only. See the guard below for why a county's
        population is never taken from free text.
        """
        if not text or len(text) < 50:
            return None

        # A county's population is not recoverable from free text, so this
        # refuses rather than guesses.
        #
        # The patterns below are anchored on the word "population" only
        # optionally — pattern 2's trailing (people|persons|inhabitants) is
        # an optional group — so in practice the first comma-formatted number
        # in the document wins. Across a county Statistical Abstract that is
        # a lottery among sub-county counts, household counts, enrolment,
        # livestock and areas. Run against Samburu's, it returns 21,090, from
        # "covering an area of 21,090 square kilometers".
        #
        # The band that used to sit at the bottom of this method hid that by
        # being Kenya's — 10M to 100M — which for a single county rejects
        # every real figure and accepts only national-scale ones. That is not
        # a filter that happened to be wrong; for a county document it has no
        # correct output at all, and what it let through was 20,317,126 as
        # Samburu's population, published on the county page as "20.32M
        # residents" with a per-capita budget of KES 399.14.
        #
        # County populations come from a table, where the column can be
        # identified and checked — see
        # backend/seeding/extractors/knbs_census_population.py, which reads
        # Census Table 2.2 and gates on the table's own arithmetic.
        if county:
            logger.debug(
                "Not reading a population for %s out of free text: the "
                "county's own figure is not identifiable this way",
                county,
            )
            return None

        # Clean and normalize text
        text_clean = text.replace("\n", " ").replace("\r", " ")
        text_clean = re.sub(r"\s+", " ", text_clean)

        # Enhanced patterns for population numbers
        patterns = [
            # Pattern 1: "population: 47.6 million" or "47.6M"
            r"(?:total\s+)?population[:\s]+([0-9]+\.?[0-9]*)\s*(?:million|m\b)",
            # Pattern 2: "population of 47,564,296" or "47,564,296 people"
            r"(?:population[:\s]+of[:\s]+)?([0-9]{2,3}(?:,[0-9]{3})+)\s*(?:people|persons|inhabitants)?",
            # Pattern 3: "Kenya's population is 47.6" (in millions context)
            r"(?:kenya\'?s?\s+)?population\s+(?:is|was|stands\s+at|estimated\s+at)[:\s]+([0-9]+\.?[0-9]*)",
            # Pattern 4: Direct large numbers (likely population)
            r"\b([4-5][0-9]\.[0-9])\s*million\s+(?:people|kenyans|population)",
            # Pattern 5: Census data format
            r"(?:census|enumeration)[:\s]+(?:total[:\s]+)?([0-9]{2,3}(?:,[0-9]{3})+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                pop_str = match.group(1).replace(",", "")
                try:
                    # Determine if value is in millions
                    context = text_clean[
                        max(0, match.start() - 100) : match.end() + 100
                    ].lower()

                    if "million" in context or " m " in context or "mn" in context:
                        population = int(float(pop_str) * 1_000_000)
                    else:
                        population = int(float(pop_str))

                    # Sanity check: this is Kenya's population, and the guard
                    # at the top of the method has already ruled out anything
                    # county-scoped reaching here.
                    if MIN_NATIONAL_POPULATION <= population <= MAX_NATIONAL_POPULATION:
                        logger.info(
                            f"📊 Extracted population: {population:,} for {county or 'Kenya'}"
                        )
                        return PopulationData(
                            total_population=population,
                            year=year or datetime.now().year,
                            county=county,
                        )
                except Exception as e:
                    logger.debug(f"Failed to parse population from: {pop_str} - {e}")
                    continue

        return None

    def _extract_gdp_from_text(
        self, text: str, year: Optional[int], quarter: Optional[str] = None
    ) -> Optional[GDPData]:
        """Extract GDP data from text with enhanced patterns."""
        if not text or len(text) < 50:
            return None

        # Clean and normalize text
        text_clean = text.replace("\n", " ").replace("\r", " ")
        text_clean = re.sub(r"\s+", " ", text_clean)

        # Enhanced patterns for GDP
        patterns = [
            # Pattern 1: "GDP KSh 12.7 trillion"
            r"(?:gdp|gross\s+domestic\s+product)[:\s]+(?:ksh\.?|kshs?\.?)?[:\s]*([0-9]+\.?[0-9]*)\s*(?:trillion|tn|t\b)",
            # Pattern 2: "GDP of KSh 12,700 billion"
            r"(?:gdp|gross\s+domestic\s+product)[:\s]+(?:of\s+)?(?:ksh\.?|kshs?\.?)?[:\s]*([0-9,]+(?:\.[0-9]+)?)\s*(?:billion|bn|b\b)",
            # Pattern 3: "GDP stood at KSh 12,749,000 million"
            r"gdp\s+(?:stood\s+at|was|is|estimated\s+at)[:\s]+(?:ksh\.?)?[:\s]*([0-9,]+(?:\.[0-9]+)?)\s*(?:trillion|billion|million)",
            # Pattern 4: "the economy recorded KSh X trillion"
            r"economy\s+(?:recorded|grew\s+by|expanded\s+to)[:\s]+(?:ksh\.?)?[:\s]*([0-9]+\.?[0-9]*)\s*(?:trillion|tn)",
            # Pattern 5: "GDP growth of X%"
            r"(?:gdp\s+)?growth[:\s]+(?:of\s+|rate\s+of\s+)?([0-9]+\.?[0-9]*)%",
        ]

        gdp_value = None
        growth_rate = None

        for pattern in patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                val_str = match.group(1).replace(",", "")
                try:
                    if "growth" in pattern:
                        growth_rate = float(val_str)
                        logger.info(f"📈 Extracted GDP growth: {growth_rate}%")
                    else:
                        # Determine multiplier from context
                        context = text_clean[
                            max(0, match.start() - 50) : match.end() + 50
                        ].lower()

                        if (
                            "trillion" in context
                            or " tn" in context
                            or " t " in context
                        ):
                            gdp_value = float(val_str) * 1_000_000_000_000
                        elif (
                            "billion" in context or " bn" in context or " b " in context
                        ):
                            gdp_value = float(val_str) * 1_000_000_000
                        elif "million" in context:
                            gdp_value = float(val_str) * 1_000_000
                        else:
                            gdp_value = float(val_str)

                        # Sanity check: Kenya's GDP should be between 1 trillion and 50 trillion KSh
                        if 1_000_000_000_000 <= gdp_value <= 50_000_000_000_000:
                            logger.info(
                                f"💰 Extracted GDP: KSh {gdp_value/1_000_000_000_000:.2f} trillion"
                            )
                            break
                        else:
                            gdp_value = None
                except Exception as e:
                    logger.debug(f"Failed to parse GDP from: {val_str} - {e}")
                    continue

        if gdp_value or growth_rate:
            return GDPData(
                gdp_value=gdp_value or 0,
                year=year or datetime.now().year,
                quarter=quarter,
                growth_rate=growth_rate,
            )

        return None

    def _extract_county_gdp_from_text(
        self, text: str, year: Optional[int], county: Optional[str]
    ) -> Optional[GDPData]:
        """Extract Gross County Product from text."""
        gdp = self._extract_gdp_from_text(text, year)
        if gdp:
            gdp.county = county
        return gdp

    def _extract_inflation_rate(
        self, text: str, period: Optional[str]
    ) -> Optional[EconomicIndicator]:
        """Extract inflation rate from text."""
        if not text:
            return None

        patterns = [
            r"inflation rate[:\s]+([0-9]+\.[0-9]+)%",
            r"cpi[:\s]+([0-9]+\.[0-9]+)%",
            r"([0-9]+\.[0-9]+)%?\s+inflation",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    rate = float(match.group(1))
                    return EconomicIndicator(
                        indicator_type="inflation_rate",
                        value=rate,
                        period=period or datetime.now().strftime("%Y-%m"),
                        unit="percent",
                    )
                except:
                    continue

        return None

    def _extract_economic_indicators_from_text(
        self, text: str, year: Optional[int]
    ) -> List[Dict]:
        """Extract various economic indicators from text with enhanced patterns."""
        indicators = []

        if not text or len(text) < 50:
            return indicators

        # Clean and normalize text
        text_clean = text.replace("\n", " ").replace("\r", " ")
        text_clean = re.sub(r"\s+", " ", text_clean)

        # Inflation rate - multiple patterns
        inflation_patterns = [
            r"inflation[:\s]+(?:rate[:\s]+)?(?:was|is|stood\s+at|recorded\s+at)?[:\s]*([0-9]+\.?[0-9]*)%",
            r"(?:overall\s+)?inflation\s+(?:averaged|reached|was)[:\s]+([0-9]+\.?[0-9]*)%",
            r"cpi[:\s]+inflation[:\s]+(?:of\s+)?([0-9]+\.?[0-9]*)%",
            r"consumer\s+price\s+index[:\s]+([0-9]+\.?[0-9]*)%",
        ]

        for pattern in inflation_patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                try:
                    rate = float(match.group(1))
                    if 0 <= rate <= 50:  # Sanity check
                        logger.info(f"📊 Extracted inflation rate: {rate}%")
                        indicators.append(
                            {
                                "indicator_type": "inflation_rate",
                                "value": rate,
                                "period": (
                                    f"{year}" if year else datetime.now().strftime("%Y")
                                ),
                                "unit": "percent",
                                "county": None,
                            }
                        )
                        break
                except:
                    continue

        # GDP growth rate
        growth_patterns = [
            r"(?:gdp\s+)?growth[:\s]+(?:rate[:\s]+)?(?:of\s+|was\s+)?([0-9]+\.?[0-9]*)%",
            r"economy\s+(?:grew|expanded)\s+(?:by\s+)?([0-9]+\.?[0-9]*)%",
            r"growth\s+of\s+([0-9]+\.?[0-9]*)\s*(?:per\s+cent|percent)",
            r"real\s+gdp\s+growth[:\s]+([0-9]+\.?[0-9]*)%",
        ]

        for pattern in growth_patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                try:
                    rate = float(match.group(1))
                    if -10 <= rate <= 20:  # Sanity check
                        logger.info(f"📈 Extracted GDP growth: {rate}%")
                        indicators.append(
                            {
                                "indicator_type": "gdp_growth_rate",
                                "value": rate,
                                "period": (
                                    f"{year}" if year else datetime.now().strftime("%Y")
                                ),
                                "unit": "percent",
                                "county": None,
                            }
                        )
                        break
                except:
                    continue

        # Unemployment rate
        unemployment_patterns = [
            r"unemployment[:\s]+(?:rate[:\s]+)?(?:was|is|stood\s+at)?[:\s]*([0-9]+\.?[0-9]*)%",
            r"unemployment\s+(?:stood\s+at|was\s+at|recorded\s+at)[:\s]+([0-9]+\.?[0-9]*)%",
            r"([0-9]+\.?[0-9]*)%\s+unemployment",
        ]

        for pattern in unemployment_patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                try:
                    rate = float(match.group(1))
                    if 0 <= rate <= 50:  # Sanity check
                        logger.info(f"👔 Extracted unemployment: {rate}%")
                        indicators.append(
                            {
                                "indicator_type": "unemployment_rate",
                                "value": rate,
                                "period": (
                                    f"{year}" if year else datetime.now().strftime("%Y")
                                ),
                                "unit": "percent",
                                "county": None,
                            }
                        )
                        break
                except:
                    continue

        # Poverty rate
        poverty_patterns = [
            r"poverty[:\s]+(?:rate[:\s]+)?(?:was|is|stood\s+at)?[:\s]*([0-9]+\.?[0-9]*)%",
            r"([0-9]+\.?[0-9]*)%\s+(?:of\s+(?:the\s+)?population\s+)?(?:live|living)\s+(?:below|in)\s+poverty",
            r"poverty\s+(?:incidence|level)[:\s]+([0-9]+\.?[0-9]*)%",
        ]

        for pattern in poverty_patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                try:
                    rate = float(match.group(1))
                    if 0 <= rate <= 100:  # Sanity check
                        logger.info(f"💔 Extracted poverty rate: {rate}%")
                        indicators.append(
                            {
                                "indicator_type": "poverty_rate",
                                "value": rate,
                                "period": (
                                    f"{year}" if year else datetime.now().strftime("%Y")
                                ),
                                "unit": "percent",
                                "county": None,
                            }
                        )
                        break
                except:
                    continue

        return indicators

    def _process_statistical_table(
        self, table: List[List], extracted_data: Dict, metadata: Dict
    ):
        """Process a table from Statistical Abstract to extract data."""
        if not table or len(table) < 2:
            return

        try:
            headers = [str(h).lower().strip() if h else "" for h in table[0]]
            leading_rows = table[: min(len(table), 3)]
            leading_text = " ".join(
                " ".join(str(cell).lower() for cell in row if cell)
                for row in leading_rows
            )

            # Look for population tables
            if any("population" in h for h in headers):
                self._extract_population_from_table(table, extracted_data, metadata)

            # Look for GDP/economic tables (including Gross County Product layouts)
            elif any(
                "gdp" in h or "gross domestic" in h for h in headers
            ) or self._looks_like_gcp_table(leading_text, leading_rows):
                self._extract_gdp_from_table(table, extracted_data, metadata)

            # Look for indicator tables (inflation, unemployment, etc.)
            elif any(
                ind in " ".join(headers)
                for ind in ["inflation", "unemployment", "poverty", "cpi"]
            ):
                self._extract_indicators_from_table(table, extracted_data, metadata)

        except Exception as e:
            logger.debug(f"Error processing table: {e}")

    def _looks_like_gcp_table(
        self, flattened_text: str, leading_rows: List[List]
    ) -> bool:
        """Heuristically determine if a table represents Gross County Product data."""
        if not leading_rows:
            return False

        text = flattened_text or ""
        if "gross county product" in text or re.search(r"\bgcp\b", text):
            return True

        # Require the presence of year-like headers to avoid false positives
        has_years = any(
            re.search(r"(19|20)\d{2}", str(cell))
            for row in leading_rows
            for cell in row
            if cell
        )
        if not has_years:
            return False

        if "economic activities" not in text:
            return False

        first_row_text = " ".join(str(cell).lower() for cell in leading_rows[0] if cell)
        currency_keywords = [
            "ksh",
            "kes",
            "million",
            "milion",
            "billion",
            "shilling",
        ]
        return any(keyword in first_row_text for keyword in currency_keywords)

    def _extract_population_from_table(
        self, table: List[List], extracted_data: Dict, metadata: Dict
    ):
        """Extract population data from a table."""
        try:
            headers = [str(h).lower().strip() if h else "" for h in table[0]]

            # Find relevant columns
            year_col = None
            pop_col = None
            county_col = None

            for i, header in enumerate(headers):
                if "year" in header or "period" in header:
                    year_col = i
                elif "population" in header and "total" in header:
                    pop_col = i
                elif pop_col is None and "population" in header:
                    pop_col = i
                elif "county" in header or "region" in header:
                    county_col = i

            if pop_col is not None:
                # A column whose header matched "year"/"period" has to hold
                # years. pdfplumber shatters a table's title across the header
                # row — "Table 1.2.1. Distribution of Population Aged 5 Years
                # and above by Activity Status, Sex, County and Sub-County,
                # 2019" arrives as ['Table 1.2.1.', 'Distribution o',
                # 'f Population A', 'ged', '', '5', 'Years and abov', ...] —
                # so "Years and abov" is taken for a year column and
                # "f Population A" for a population column. Neither is one.
                #
                # If the year column holds no years then we have not
                # understood this table, and the population column is no more
                # trustworthy than the year column. Emit nothing: a figure we
                # cannot place in time is not a figure a reader can check.
                if year_col is not None and not _column_holds_years(
                    table, year_col
                ):
                    logger.warning(
                        "Rejecting table: header %r was read as a year column "
                        "but holds no calendar years — the table's columns "
                        "have not been identified, so no population row from "
                        "it can be published",
                        headers[year_col],
                    )
                    return

                # Which "too big" applies depends on what the document is
                # about. Kenya's band admits any county-sized figure AND any
                # national one, which is how 20,317,126 was published as
                # Samburu's population.
                max_population = (
                    MAX_COUNTY_POPULATION
                    if metadata.get("county")
                    else MAX_NATIONAL_POPULATION
                )

                for row in table[1:]:
                    if len(row) <= pop_col:
                        continue

                    try:
                        pop_value = row[pop_col]
                        if not pop_value or pop_value == "":
                            continue

                        # Clean and parse population value
                        pop_str = (
                            str(pop_value).replace(",", "").replace(" ", "").strip()
                        )
                        population = int(float(pop_str))

                        # Get year if available. The column has been shown to
                        # hold years, so a cell that still fails to parse is
                        # this row's own gap: fall back to the year the
                        # document is filed under, never to the raw cell.
                        year = metadata.get("year")
                        if year_col is not None and len(row) > year_col:
                            row_year = _parse_calendar_year(row[year_col])
                            if row_year is not None:
                                year = row_year

                        # Get county if available
                        county = metadata.get("county")
                        if county_col is not None and len(row) > county_col:
                            county = str(row[county_col]).strip()

                        # Sanity check, scoped to what this document is about
                        if MIN_PLAUSIBLE_POPULATION <= population <= max_population:
                            pop_data = {
                                "total_population": population,
                                "year": year,
                                "county": county,
                            }
                            extracted_data["population_data"].append(pop_data)
                            logger.info(
                                f"📊 Extracted from table: Population {population:,} ({year})"
                            )
                    except Exception as e:
                        continue

        except Exception as e:
            logger.debug(f"Error extracting population from table: {e}")

    def _extract_gdp_from_table(
        self, table: List[List], extracted_data: Dict, metadata: Dict
    ):
        """Extract GDP data from a table."""
        try:
            headers = [str(h).lower().strip() if h else "" for h in table[0]]

            def parse_year(cell: Any) -> Optional[int]:
                if cell is None:
                    return None
                text = str(cell).strip()
                if not text:
                    return None
                match = re.search(r"(19|20)\d{2}", text)
                if match:
                    try:
                        return int(match.group(0))
                    except ValueError:
                        return None
                return None

            def clean_numeric(value: Any) -> Optional[float]:
                if value is None:
                    return None
                text = str(value).strip()
                if not text:
                    return None
                text = text.replace(",", "").replace(" ", "")
                text = text.replace("\u2212", "-").replace("–", "-")
                negative = False
                if text.startswith("(") and text.endswith(")"):
                    negative = True
                    text = text[1:-1]
                if text in {"", "-", "--", "—"}:
                    return None
                if not re.search(r"\d", text):
                    return None
                try:
                    number = float(text)
                except ValueError:
                    return None
                if negative:
                    number *= -1
                return number

            # Map columns to explicit year values when tables are arranged by activity x years
            column_year_map: Dict[int, int] = {}
            for row in table[: min(len(table), 4)]:
                for idx, cell in enumerate(row):
                    year = parse_year(cell)
                    if year is not None and idx not in column_year_map:
                        column_year_map[idx] = year

            # Find GDP-related columns
            year_col = None
            gdp_col = None
            growth_col = None
            quarter_col = None

            for i, header in enumerate(headers):
                if "year" in header:
                    year_col = i
                elif "quarter" in header or "q1" in header or "q2" in header:
                    quarter_col = i
                elif "gdp" in header or "gross domestic" in header:
                    gdp_col = i
                elif "growth" in header and gdp_col is None:
                    growth_col = i

            # Handle multi-year Gross County Product tables without explicit GDP columns
            if gdp_col is None and growth_col is None and column_year_map:
                first_year_col = min(column_year_map.keys())
                label_columns = list(range(first_year_col))

                unit_text = " ".join(str(cell).lower() for cell in table[0] if cell)
                unit_multiplier = 1.0
                if any(keyword in unit_text for keyword in ["billion"]):
                    unit_multiplier = 1_000_000_000
                elif any(keyword in unit_text for keyword in ["million", "milion"]):
                    unit_multiplier = 1_000_000
                elif any(keyword in unit_text for keyword in ["thousand"]):
                    unit_multiplier = 1_000
                elif any(keyword in unit_text for keyword in ["ksh", "kes"]):
                    unit_multiplier = 1_000_000

                primary_label_columns = [idx for idx in label_columns if idx > 0]
                fallback_column = 0 if 0 in label_columns else None

                def build_label(row: List[Any]) -> str:
                    text_parts: List[str] = []
                    for idx in primary_label_columns:
                        if idx >= len(row):
                            continue
                        cell = row[idx]
                        if not cell:
                            continue
                        for segment in str(cell).split("\n"):
                            segment_clean = re.sub(r"\s+", " ", segment).strip()
                            if segment_clean:
                                text_parts.append(segment_clean)

                    if (
                        not text_parts
                        and fallback_column is not None
                        and fallback_column < len(row)
                    ):
                        cell = row[fallback_column]
                        if cell:
                            for segment in str(cell).split("\n"):
                                segment_clean = re.sub(r"\s+", " ", segment).strip()
                                if segment_clean:
                                    text_parts.append(segment_clean)

                    return " ".join(text_parts).strip()

                county_name = metadata.get("county")

                for row in table[1:]:
                    label = build_label(row)
                    if not label:
                        continue
                    label_lower = label.lower()
                    normalized_label = label_lower.replace("(", " ").replace(")", " ")
                    if not (
                        normalized_label.startswith("gcp")
                        or normalized_label.startswith("gross county product")
                        or normalized_label.startswith("gross value added")
                    ):
                        continue

                    for col_idx, year in column_year_map.items():
                        if col_idx >= len(row):
                            continue
                        numeric_value = clean_numeric(row[col_idx])
                        if numeric_value is None:
                            continue
                        gdp_value = numeric_value * unit_multiplier
                        gdp_data = {
                            "gdp_value": gdp_value,
                            "year": year,
                            "quarter": None,
                            "growth_rate": None,
                            "county": county_name,
                        }
                        extracted_data["gdp_data"].append(gdp_data)
                        logger.info(
                            "💰 Extracted from table: %s GCP %s = %.2fB KSh",
                            county_name or "County",
                            year,
                            gdp_value / 1_000_000_000,
                        )

                return

            if gdp_col is not None or growth_col is not None:
                for row in table[1:]:
                    try:
                        # Get year
                        year = metadata.get("year")
                        if year_col is not None and len(row) > year_col:
                            try:
                                year = int(str(row[year_col]).strip())
                            except:
                                pass

                        # Get quarter
                        quarter = None
                        if quarter_col is not None and len(row) > quarter_col:
                            quarter = str(row[quarter_col]).strip()

                        # Get GDP value
                        gdp_value = None
                        if gdp_col is not None and len(row) > gdp_col:
                            gdp_str = (
                                str(row[gdp_col])
                                .replace(",", "")
                                .replace(" ", "")
                                .strip()
                            )
                            try:
                                gdp_value = float(gdp_str)
                                # Assume billions if value is small
                                if gdp_value < 1000:
                                    gdp_value = gdp_value * 1_000_000_000
                            except:
                                pass

                        # Get growth rate
                        growth_rate = None
                        if growth_col is not None and len(row) > growth_col:
                            growth_str = str(row[growth_col]).replace("%", "").strip()
                            try:
                                growth_rate = float(growth_str)
                            except:
                                pass

                        if gdp_value or growth_rate:
                            gdp_data = {
                                "gdp_value": gdp_value or 0,
                                "year": year,
                                "quarter": quarter,
                                "growth_rate": growth_rate,
                            }
                            extracted_data["gdp_data"].append(gdp_data)
                            logger.info(
                                f"💰 Extracted from table: GDP {gdp_value/1e9:.2f}B ({year}{'-'+quarter if quarter else ''})"
                            )
                    except Exception as e:
                        continue

        except Exception as e:
            logger.debug(f"Error extracting GDP from table: {e}")

    def _extract_indicators_from_table(
        self, table: List[List], extracted_data: Dict, metadata: Dict
    ):
        """Extract economic indicators from a table."""
        try:
            headers = [str(h).lower().strip() if h else "" for h in table[0]]

            # Find indicator columns
            for row in table[1:]:
                try:
                    # Look for indicator name in first column
                    if not row or len(row) < 2:
                        continue

                    indicator_name = str(row[0]).lower().strip()

                    # Try to extract values from remaining columns
                    for col_idx in range(1, len(row)):
                        try:
                            value_str = (
                                str(row[col_idx])
                                .replace("%", "")
                                .replace(",", "")
                                .strip()
                            )
                            if not value_str or value_str == "":
                                continue

                            value = float(value_str)

                            # Determine indicator type
                            indicator_type = None
                            if "inflation" in indicator_name or "cpi" in indicator_name:
                                indicator_type = "inflation_rate"
                            elif "unemployment" in indicator_name:
                                indicator_type = "unemployment_rate"
                            elif "poverty" in indicator_name:
                                indicator_type = "poverty_rate"
                            elif "growth" in indicator_name:
                                indicator_type = "gdp_growth_rate"

                            if indicator_type and 0 <= value <= 100:
                                indicator_data = {
                                    "indicator_type": indicator_type,
                                    "value": value,
                                    "period": (
                                        f"{metadata.get('year')}"
                                        if metadata.get("year")
                                        else None
                                    ),
                                    "unit": "percent",
                                    "county": None,
                                }
                                extracted_data["economic_indicators"].append(
                                    indicator_data
                                )
                                logger.info(
                                    f"📊 Extracted from table: {indicator_type} = {value}%"
                                )
                                break
                        except:
                            continue
                except:
                    continue

        except Exception as e:
            logger.debug(f"Error extracting indicators from table: {e}")

    def _process_economic_survey_table(
        self, table: List[List], extracted_data: Dict, metadata: Dict
    ):
        """
        Process a table from an Economic Survey to extract economic data.

        Economic Surveys contain comprehensive tables with:
        - GDP by activity/sector
        - Population and demographics
        - Inflation and price indices
        - Employment and unemployment
        - Poverty rates
        """
        if not table or len(table) < 2:
            return

        # Get first row (headers)
        headers = [str(cell).lower().strip() if cell else "" for cell in table[0]]

        # Identify table type from headers or first column
        table_type = None

        # Check for GDP tables
        if any("gdp" in h or "gross domestic product" in h for h in headers):
            table_type = "gdp"
            self._extract_gdp_from_table(table, extracted_data, metadata)

        # Check for population tables
        elif any("population" in h for h in headers):
            table_type = "population"
            self._extract_population_from_table(table, extracted_data, metadata)

        # Check for inflation/CPI tables
        elif any("inflation" in h or "cpi" in h or "price" in h for h in headers):
            table_type = "inflation"
            self._extract_indicators_from_table(table, extracted_data, metadata)

        # Check for unemployment tables
        elif any(
            "unemployment" in h or "employment" in h or "labour" in h for h in headers
        ):
            table_type = "unemployment"
            self._extract_indicators_from_table(table, extracted_data, metadata)

        # Check for poverty tables
        elif any("poverty" in h for h in headers):
            table_type = "poverty"
            self._extract_indicators_from_table(table, extracted_data, metadata)

        # Generic indicator extraction (try all indicator types)
        else:
            # Check first column for indicator names
            first_col_values = [
                str(row[0]).lower() if row and row[0] else "" for row in table[1:]
            ]
            if any(
                indicator in " ".join(first_col_values)
                for indicator in ["inflation", "unemployment", "growth", "poverty"]
            ):
                self._extract_indicators_from_table(table, extracted_data, metadata)


# Example usage
if __name__ == "__main__":
    # Test with a sample document metadata
    parser = KNBSParser()

    sample_metadata = {
        "title": "2025 Economic Survey",
        "url": "https://www.knbs.or.ke/wp-content/uploads/2025/05/2025-Economic-Survey.pdf",
        "type": "economic_survey",
        "year": 2025,
    }

    # Note: This will actually try to download and parse the PDF
    # result = parser.parse_document(sample_metadata)
    # print(json.dumps(result, indent=2))

    print("[OK] KNBS Parser module created")
    print(
        "Ready to parse: Economic Survey, Statistical Abstract, County Abstracts, GDP/CPI reports"
    )
