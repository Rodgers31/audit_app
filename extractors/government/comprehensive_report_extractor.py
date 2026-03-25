"""
Comprehensive Kenya Government Report Extraction System
Extracts ALL reports based on official reporting periods and frequencies
Caches locally to avoid reliance on slow/unreliable government sites
"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KenyaReportExtractor:
    """Comprehensive extractor for all Kenya government reports."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )

        # Create cache directory
        self.cache_dir = "report_cache"
        os.makedirs(self.cache_dir, exist_ok=True)

        # Reporting periods and frequencies
        self.reporting_schedule = {
            "treasury": {
                "budget_statements": {"frequency": "annual", "period": "June"},
                "supplementary_budgets": {
                    "frequency": "quarterly",
                    "period": "every_3_months",
                },
                "debt_reports": {"frequency": "quarterly", "period": "every_3_months"},
                "programme_budgets": {"frequency": "annual", "period": "June"},
            },
            "cob": {
                "county_implementation_reviews": {
                    "frequency": "quarterly",
                    "period": "every_3_months",
                },
                "budget_implementation_reports": {
                    "frequency": "monthly",
                    "period": "monthly",
                },
            },
            "oag": {
                "annual_audit_reports": {"frequency": "annual", "period": "December"},
                "county_audit_reports": {"frequency": "annual", "period": "December"},
                "special_audit_reports": {"frequency": "ad_hoc", "period": "irregular"},
            },
            "knbs": {
                "economic_surveys": {"frequency": "annual", "period": "May"},
                "statistical_abstracts": {"frequency": "annual", "period": "December"},
                "quarterly_bulletins": {
                    "frequency": "quarterly",
                    "period": "every_3_months",
                },
            },
        }

        self.results = {
            "extraction_summary": {},
            "treasury_reports": [],
            "cob_reports": [],
            "oag_reports": [],
            "knbs_reports": [],
            "cache_status": {},
            "errors": [],
        }

    def extract_treasury_comprehensive(self):
        """Extract ALL Treasury reports comprehensively."""
        logger.info("🏛️ COMPREHENSIVE Treasury Extraction...")

        treasury_urls = [
            "https://treasury.go.ke",
            "https://treasury.go.ke/budget/",
            "https://treasury.go.ke/publications/",
            "https://treasury.go.ke/debt-management/",
        ]

        all_documents = []

        for base_url in treasury_urls:
            try:
                logger.info(f"📊 Scanning {base_url}...")
                response = self.session.get(base_url, timeout=30)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")

                    # Find all PDF links
                    links = soup.find_all("a", href=True)

                    for link in links:
                        href = link["href"]
                        text = link.get_text().strip()

                        if href.endswith(".pdf") or "pdf" in href.lower():
                            full_url = urljoin(base_url, href)

                            doc_info = {
                                "title": text,
                                "url": full_url,
                                "source_page": base_url,
                                "type": self._categorize_treasury_document(text),
                                "reporting_period": self._extract_reporting_period(
                                    text
                                ),
                                "financial_year": self._extract_financial_year(text),
                                "document_hash": hashlib.md5(
                                    full_url.encode()
                                ).hexdigest(),
                            }

                            all_documents.append(doc_info)

                # Add delay to avoid overwhelming the server
                time.sleep(2)

            except Exception as e:
                logger.warning(f"❌ Treasury URL {base_url} failed: {str(e)}")
                self.results["errors"].append(f"Treasury {base_url}: {str(e)}")

        # Remove duplicates
        unique_docs = []
        seen_hashes = set()

        for doc in all_documents:
            if doc["document_hash"] not in seen_hashes:
                unique_docs.append(doc)
                seen_hashes.add(doc["document_hash"])

        self.results["treasury_reports"] = unique_docs
        logger.info(f"✅ Treasury: Found {len(unique_docs)} unique documents")

        return unique_docs

    def extract_cob_comprehensive(self):
        """Extract ALL Controller of Budget reports."""
        logger.info("🏛️ COMPREHENSIVE COB Extraction...")

        cob_urls = [
            "https://cob.go.ke",
            "https://cob.go.ke/publications/",
            "https://cob.go.ke/county-budget-implementation-review-reports/",
            "https://cob.go.ke/reports/",  # legacy fallback
        ]

        all_documents = []

        for base_url in cob_urls:
            try:
                logger.info(f"📊 Scanning {base_url}...")
                response = self.session.get(base_url, timeout=30)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")

                    # Find all PDF links and download links
                    links = soup.find_all("a", href=True)

                    for link in links:
                        href = link["href"]
                        text = link.get_text().strip()

                        if (
                            href.endswith(".pdf")
                            or "pdf" in href.lower()
                            or "download" in href.lower()
                            or "report" in text.lower()
                        ):

                            full_url = urljoin(base_url, href)

                            doc_info = {
                                "title": text,
                                "url": full_url,
                                "source_page": base_url,
                                "type": self._categorize_cob_document(text),
                                "county": self._extract_county_name(text),
                                "reporting_period": self._extract_reporting_period(
                                    text
                                ),
                                "financial_year": self._extract_financial_year(text),
                                "document_hash": hashlib.md5(
                                    full_url.encode()
                                ).hexdigest(),
                            }

                            all_documents.append(doc_info)

                time.sleep(3)  # COB is particularly slow

            except Exception as e:
                logger.warning(f"❌ COB URL {base_url} failed: {str(e)}")
                self.results["errors"].append(f"COB {base_url}: {str(e)}")

        # Remove duplicates
        unique_docs = []
        seen_hashes = set()

        for doc in all_documents:
            if doc["document_hash"] not in seen_hashes:
                unique_docs.append(doc)
                seen_hashes.add(doc["document_hash"])

        self.results["cob_reports"] = unique_docs
        logger.info(f"✅ COB: Found {len(unique_docs)} unique documents")

        return unique_docs

    def extract_oag_comprehensive(self):
        """Extract ALL Auditor General reports."""
        logger.info("🏛️ COMPREHENSIVE OAG Extraction...")

        oag_urls = [
            "https://oagkenya.go.ke",
            "https://oagkenya.go.ke/index.php/reports",
            "https://oagkenya.go.ke/index.php/reports/annual-reports",
            "https://oagkenya.go.ke/index.php/reports/special-audit-reports",
            "https://oagkenya.go.ke/index.php/reports/county-audit-reports",
        ]

        all_documents = []

        for base_url in oag_urls:
            try:
                logger.info(f"📊 Scanning {base_url}...")
                response = self.session.get(base_url, timeout=30)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")

                    # Find all PDF links
                    links = soup.find_all("a", href=True)

                    for link in links:
                        href = link["href"]
                        text = link.get_text().strip()

                        if (
                            href.endswith(".pdf")
                            or "pdf" in href.lower()
                            or "audit" in text.lower()
                            or "report" in text.lower()
                        ):

                            full_url = urljoin(base_url, href)

                            doc_info = {
                                "title": text,
                                "url": full_url,
                                "source_page": base_url,
                                "type": self._categorize_oag_document(text),
                                "audit_type": self._extract_audit_type(text),
                                "entity_audited": self._extract_audited_entity(text),
                                "reporting_period": self._extract_reporting_period(
                                    text
                                ),
                                "financial_year": self._extract_financial_year(text),
                                "document_hash": hashlib.md5(
                                    full_url.encode()
                                ).hexdigest(),
                            }

                            all_documents.append(doc_info)

                time.sleep(3)  # OAG can be slow

            except Exception as e:
                logger.warning(f"❌ OAG URL {base_url} failed: {str(e)}")
                self.results["errors"].append(f"OAG {base_url}: {str(e)}")

        # Remove duplicates
        unique_docs = []
        seen_hashes = set()

        for doc in all_documents:
            if doc["document_hash"] not in seen_hashes:
                unique_docs.append(doc)
                seen_hashes.add(doc["document_hash"])

        self.results["oag_reports"] = unique_docs
        logger.info(f"✅ OAG: Found {len(unique_docs)} unique documents")

        return unique_docs

    def extract_knbs_comprehensive(self):
        """Extract ALL KNBS statistical reports."""
        logger.info("🏛️ COMPREHENSIVE KNBS Extraction...")

        knbs_urls = [
            "https://www.knbs.or.ke",
            "https://www.knbs.or.ke/publications/",
            "https://www.knbs.or.ke/economic-surveys/",
            "https://www.knbs.or.ke/statistical-abstracts/",
            "https://www.knbs.or.ke/quarterly-gross-domestic-product-report/",
        ]

        all_documents = []

        for base_url in knbs_urls:
            try:
                logger.info(f"📊 Scanning {base_url}...")
                # KNBS has SSL issues, so we might need to handle this
                response = self.session.get(base_url, timeout=30, verify=False)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")

                    # Find all PDF links
                    links = soup.find_all("a", href=True)

                    for link in links:
                        href = link["href"]
                        text = link.get_text().strip()

                        if (
                            href.endswith(".pdf")
                            or "pdf" in href.lower()
                            or any(
                                keyword in text.lower()
                                for keyword in [
                                    "survey",
                                    "abstract",
                                    "bulletin",
                                    "report",
                                ]
                            )
                        ):

                            full_url = urljoin(base_url, href)

                            doc_info = {
                                "title": text,
                                "url": full_url,
                                "source_page": base_url,
                                "type": self._categorize_knbs_document(text),
                                "statistical_category": self._extract_statistical_category(
                                    text
                                ),
                                "reporting_period": self._extract_reporting_period(
                                    text
                                ),
                                "year": self._extract_year(text),
                                "document_hash": hashlib.md5(
                                    full_url.encode()
                                ).hexdigest(),
                            }

                            all_documents.append(doc_info)

                time.sleep(2)

            except Exception as e:
                logger.warning(f"❌ KNBS URL {base_url} failed: {str(e)}")
                self.results["errors"].append(f"KNBS {base_url}: {str(e)}")

        # Remove duplicates
        unique_docs = []
        seen_hashes = set()

        for doc in all_documents:
            if doc["document_hash"] not in seen_hashes:
                unique_docs.append(doc)
                seen_hashes.add(doc["document_hash"])

        self.results["knbs_reports"] = unique_docs
        logger.info(f"✅ KNBS: Found {len(unique_docs)} unique documents")

        return unique_docs

    def _categorize_treasury_document(self, title: str) -> str:
        """Categorize treasury documents."""
        title_lower = title.lower()

        if any(
            keyword in title_lower
            for keyword in ["budget statement", "programme budget"]
        ):
            return "budget_statement"
        elif any(keyword in title_lower for keyword in ["supplementary", "additional"]):
            return "supplementary_budget"
        elif any(keyword in title_lower for keyword in ["debt", "borrowing", "bond"]):
            return "debt_report"
        elif "policy" in title_lower:
            return "policy_document"
        else:
            return "general_treasury"

    def _categorize_cob_document(self, title: str) -> str:
        """Categorize COB documents."""
        title_lower = title.lower()

        if "county" in title_lower:
            return "county_implementation_review"
        elif "budget implementation" in title_lower:
            return "budget_implementation_report"
        else:
            return "general_cob"

    def _categorize_oag_document(self, title: str) -> str:
        """Categorize OAG documents."""
        title_lower = title.lower()

        if "special audit" in title_lower:
            return "special_audit"
        elif "county" in title_lower:
            return "county_audit"
        elif "annual" in title_lower:
            return "annual_audit"
        else:
            return "general_audit"

    def _categorize_knbs_document(self, title: str) -> str:
        """Categorize KNBS documents."""
        title_lower = title.lower()

        if "economic survey" in title_lower:
            return "economic_survey"
        elif "statistical abstract" in title_lower:
            return "statistical_abstract"
        elif "quarterly" in title_lower:
            return "quarterly_bulletin"
        else:
            return "general_statistics"

    def _extract_reporting_period(self, title: str) -> Optional[str]:
        """Extract reporting period from document title."""
        # Look for quarters
        quarter_match = re.search(
            r"Q[1-4]|Quarter [1-4]|[1-4]st|[1-4]nd|[1-4]rd|[1-4]th",
            title,
            re.IGNORECASE,
        )
        if quarter_match:
            return quarter_match.group()

        # Look for months
        months = [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        for month in months:
            if month.lower() in title.lower():
                return month

        return None

    def _extract_financial_year(self, title: str) -> Optional[str]:
        """Extract financial year from document title."""
        # Look for patterns like 2024/25, 2024-25, FY 2024/25
        fy_match = re.search(r"(?:FY\s*)?(\d{4})[/-](\d{2,4})", title, re.IGNORECASE)
        if fy_match:
            return fy_match.group()

        # Look for single years
        year_match = re.search(r"\b(20\d{2})\b", title)
        if year_match:
            return year_match.group()

        return None

    def _extract_county_name(self, title: str) -> Optional[str]:
        """Extract county name from title."""
        kenya_counties = [
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

        for county in kenya_counties:
            if county.lower() in title.lower():
                return county

        return None

    def _extract_audit_type(self, title: str) -> Optional[str]:
        """Extract audit type from title."""
        title_lower = title.lower()

        if "performance audit" in title_lower:
            return "performance"
        elif "financial audit" in title_lower:
            return "financial"
        elif "compliance audit" in title_lower:
            return "compliance"
        elif "special audit" in title_lower:
            return "special"
        else:
            return "general"

    def _extract_audited_entity(self, title: str) -> Optional[str]:
        """Extract the entity being audited."""
        # Look for ministry patterns
        ministry_match = re.search(r"Ministry of [\w\s]+", title, re.IGNORECASE)
        if ministry_match:
            return ministry_match.group()

        # Look for county patterns
        county = self._extract_county_name(title)
        if county:
            return f"{county} County"

        return None

    def _extract_statistical_category(self, title: str) -> Optional[str]:
        """Extract statistical category for KNBS documents."""
        title_lower = title.lower()

        if "gdp" in title_lower or "gross domestic" in title_lower:
            return "gdp"
        elif "inflation" in title_lower or "price" in title_lower:
            return "inflation"
        elif "employment" in title_lower or "labour" in title_lower:
            return "employment"
        elif "agriculture" in title_lower:
            return "agriculture"
        else:
            return "general"

    def _extract_year(self, title: str) -> Optional[str]:
        """Extract year from title."""
        year_match = re.search(r"\b(20\d{2})\b", title)
        if year_match:
            return year_match.group()
        return None

    def run_comprehensive_extraction(self):
        """Run comprehensive extraction from all sources."""
        logger.info("\n" + "=" * 80)
        logger.info("🚀 COMPREHENSIVE KENYA GOVERNMENT REPORT EXTRACTION")
        logger.info("=" * 80)

        start_time = datetime.now()

        # Extract from all sources
        treasury_docs = self.extract_treasury_comprehensive()
        cob_docs = self.extract_cob_comprehensive()
        oag_docs = self.extract_oag_comprehensive()
        knbs_docs = self.extract_knbs_comprehensive()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Calculate summary
        total_documents = (
            len(treasury_docs) + len(cob_docs) + len(oag_docs) + len(knbs_docs)
        )

        self.results["extraction_summary"] = {
            "total_documents_found": total_documents,
            "treasury_documents": len(treasury_docs),
            "cob_documents": len(cob_docs),
            "oag_documents": len(oag_docs),
            "knbs_documents": len(knbs_docs),
            "extraction_duration_seconds": duration,
            "errors_encountered": len(self.results["errors"]),
            "timestamp": datetime.now().isoformat(),
        }

        # Log summary
        logger.info(f"\n📋 EXTRACTION COMPLETE:")
        logger.info(f"   💰 Treasury: {len(treasury_docs)} documents")
        logger.info(f"   🏛️ COB: {len(cob_docs)} documents")
        logger.info(f"   📊 OAG: {len(oag_docs)} documents")
        logger.info(f"   📈 KNBS: {len(knbs_docs)} documents")
        logger.info(f"   📑 Total: {total_documents} documents")
        logger.info(f"   ⏱️ Duration: {duration:.1f} seconds")
        logger.info(f"   ❌ Errors: {len(self.results['errors'])}")

        return self.results


def main():
    """Main function to run comprehensive extraction."""
    extractor = KenyaReportExtractor()
    results = extractor.run_comprehensive_extraction()

    # Save results
    with open("comprehensive_report_extraction.json", "w") as f:
        json.dump(results, f, indent=2)

    summary = results["extraction_summary"]
    print(f"\n✅ Comprehensive extraction completed!")
    print(f"📑 Total documents found: {summary['total_documents_found']}")
    print(f"📁 Results saved to: comprehensive_report_extraction.json")


if __name__ == "__main__":
    main()
