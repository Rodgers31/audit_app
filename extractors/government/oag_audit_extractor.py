"""
Office of the Auditor-General (OAG) Audit Extractor
Discovers OAG audit report documents and reads what their titles state.

WITHDRAWN 2026-09-07 (issue #193): four methods that manufactured audit
findings about named county governments out of ``hash()``, and the parts of the
run summary computed from them.

    generate_county_audit_queries       149-241  2-5 "audit queries" per county,
                                                 each with an amount to KSh 50M,
                                                 a severity, a status, a
                                                 four-digit id and a date raised
    generate_missing_funds_analysis     243-280  1-3 "missing funds" cases per
                                                 county, to KSh 100M, each with
                                                 an MF#### case id and a
                                                 percentage of a budget that was
                                                 itself hash(county)
    _generate_missing_funds_description 348-357  chose the wording by hash()
    _generate_recovery_efforts          359-369  chose how many "recovery
                                                 efforts" to claim by
                                                 hash(str(time.time()))

None of it was extracted from anything. ``hash()`` on a ``str`` is salted per
process, so every county's figures changed on each restart; the last method was
seeded on the clock and so varied *within* one run. Counties are named public
bodies, and a fabricated finding against one — an amount, a severity, a case
id, a date it was raised — is a statement of fact about that body, which is the
issue #182/#183 concern in its stronger form. Unlike those, this file ships:
``Dockerfile:26`` copies ``extractors/`` into the production image.

What survives reads the OAG website and reports what it finds there:
``extract_oag_audit_reports`` and the five ``_extract``/``_categorize`` helpers
it calls, which parse report titles. They report nothing when they find
nothing, which is the correct answer when nothing was found.
``run_comprehensive_oag_extraction`` keeps its one real step and lost the two
generated ones, along with ``audit_statistics`` (every field of which counted
fabricated records) and the ``data_sources.coverage`` claim of "All 47 Kenya
Counties", which measured nothing — it restated the length of the name-matching
roster. ``_generate_recommendation`` is kept and is currently unreferenced: it
maps a query category to generic remediation advice, which is not a claim about
any county.
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OAGAuditExtractor:
    """Specialized extractor for Office of the Auditor-General audit reports."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        self.audit_reports = []
        self.national_audit_findings = []
        self.special_audit_reports = []

        # Kenya's 47 counties for matching
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

    def extract_oag_audit_reports(self):
        """Extract audit reports from OAG website."""
        logger.info("🏛️ Extracting OAG Audit Reports...")

        oag_urls = [
            "https://oagkenya.go.ke",
            "https://oagkenya.go.ke/index.php/reports/annual-reports",
            "https://oagkenya.go.ke/index.php/reports/county-audit-reports",
            "https://oagkenya.go.ke/index.php/reports/special-audit-reports",
            "https://oagkenya.go.ke/index.php/reports",
        ]

        extracted_reports = []

        for url in oag_urls:
            try:
                logger.info(f"🔍 Checking OAG URL: {url}")
                response = self.session.get(url, timeout=30)

                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")

                    # Find PDF links and report titles
                    pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))

                    for link in pdf_links:
                        pdf_url = link.get("href")
                        title = link.get_text(strip=True) or link.get(
                            "title", "Unknown Report"
                        )

                        # Categorize the report
                        report_type = self._categorize_audit_report(title, url)
                        audit_year = self._extract_year(title)

                        report_data = {
                            "title": title,
                            "url": pdf_url,
                            "type": report_type,
                            "year": audit_year,
                            "source_page": url,
                            "extracted_date": datetime.now().isoformat(),
                            "county": self._extract_county_name(title),
                            "audit_queries": self._extract_audit_queries(title),
                            "findings": self._extract_findings_summary(title),
                        }

                        extracted_reports.append(report_data)
                        logger.info(f"✅ Found: {title[:60]}...")

                else:
                    logger.warning(
                        f"⚠️ OAG URL failed: {url} - Status: {response.status_code}"
                    )

            except Exception as e:
                logger.error(f"❌ OAG extraction failed for {url}: {str(e)}")

        self.audit_reports = extracted_reports
        return extracted_reports

    def _categorize_audit_report(self, title: str, url: str) -> str:
        """Categorize audit report type."""
        title_lower = title.lower()
        url_lower = url.lower()

        if "county" in title_lower or "county" in url_lower:
            return "County Audit Report"
        elif "special" in title_lower or "special" in url_lower:
            return "Special Audit Report"
        elif "annual" in title_lower or "annual" in url_lower:
            return "Annual Audit Report"
        else:
            return "General Audit Report"

    def _extract_year(self, title: str) -> Optional[str]:
        """Extract year from report title."""
        year_match = re.search(r"20\d{2}", title)
        return year_match.group() if year_match else None

    def _extract_county_name(self, title: str) -> Optional[str]:
        """Extract county name from report title."""
        title_lower = title.lower()
        for county in self.counties:
            if county.lower() in title_lower:
                return county
        return None

    def _extract_audit_queries(self, title: str) -> List[str]:
        """Extract potential audit queries from title."""
        queries = []
        title_lower = title.lower()

        if "irregularity" in title_lower:
            queries.append("Financial irregularities identified")
        if "procurement" in title_lower:
            queries.append("Procurement non-compliance")
        if "missing" in title_lower:
            queries.append("Missing documentation")

        return queries

    def _extract_findings_summary(self, title: str) -> List[str]:
        """Extract findings summary from title."""
        findings = []
        title_lower = title.lower()

        if "qualified" in title_lower:
            findings.append("Qualified audit opinion")
        if "adverse" in title_lower:
            findings.append("Adverse audit opinion")
        if "disclaimer" in title_lower:
            findings.append("Disclaimer of opinion")

        return findings

    def _generate_recommendation(self, query_type: str) -> str:
        """Generate audit recommendation based on query type."""
        recommendations = {
            "Financial Irregularity": "Implement stronger internal controls and documentation procedures",
            "Procurement Issues": "Comply with procurement laws and maintain proper documentation",
            "Missing Funds": "Conduct immediate investigation and implement recovery procedures",
            "Payroll Issues": "Verify all staff records and implement biometric attendance system",
            "Asset Management": "Maintain proper asset register and conduct physical verification",
        }
        return recommendations.get(query_type, "Address the identified issues promptly")

    def run_comprehensive_oag_extraction(self):
        """Discover OAG audit reports and report what was actually found.

        Steps 2 and 3 of this method used to be "generate county audit queries"
        and "generate missing funds analysis"; they went with the methods
        behind them. See the module docstring.
        """
        logger.info("\n" + "=" * 80)
        logger.info("🏛️ OAG AUDIT REPORT DISCOVERY")
        logger.info("=" * 80)

        start_time = datetime.now()
        audit_reports = self.extract_oag_audit_reports()
        duration = (datetime.now() - start_time).total_seconds()

        results = {
            "extraction_summary": {
                "audit_reports_found": len(audit_reports),
                # The size of the name-matching roster. NOT a coverage claim:
                # how many counties are represented in the reports found is
                # whatever the OAG site listed, and this number cannot see it.
                "counties_in_name_matcher": len(self.counties),
                "extraction_duration": duration,
                "timestamp": datetime.now().isoformat(),
            },
            "audit_reports": audit_reports,
            "data_sources": {
                "primary": "Office of the Auditor-General Kenya (oagkenya.go.ke)",
                "report_types": [
                    "County Audit Reports",
                    "Annual Reports",
                    "Special Audits",
                ],
            },
        }

        logger.info("\n📋 OAG DISCOVERY COMPLETE:")
        logger.info(f"   📊 Audit Reports: {len(audit_reports)}")
        logger.info(f"   ⏱️ Duration: {duration:.1f} seconds")

        return results


def main():
    """Main function to run OAG audit report discovery."""
    extractor = OAGAuditExtractor()
    results = extractor.run_comprehensive_oag_extraction()

    # Save results
    with open("oag_audit_data.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n✅ OAG audit report discovery completed!")
    print(f"📊 Audit Reports: {len(results['audit_reports'])}")
    print("📁 Results saved to: oag_audit_data.json")


if __name__ == "__main__":
    main()
