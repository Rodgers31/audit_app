"""
Controller of Budget (COB) Report Extractor
Discovers COB county budget implementation review documents on cob.go.ke and
reads what their titles and page text state.

WITHDRAWN 2026-09-07 (issue #196): two methods that derived a named county
government's entire budget, execution rate and expenditure — and the failings
attributed to it — from ``hash()``, and the parts of the run summary computed
from them.

    generate_county_implementation_data  167-238  every one of the 47 counties'
                                                  total budget, development and
                                                  recurrent split, expenditure,
                                                  absorption rate, revenue
                                                  target, transfers and pending
                                                  bills ratio, all from
                                                  ``hash(county) % 100``
    _generate_implementation_challenges  366-392  2-5 named failings ("Delayed
                                                  procurement processes", "Weak
                                                  revenue collection") picked
                                                  for a named county by
                                                  ``hash(county)``

``hash()`` on a ``str`` is salted per process, so none of it was attached to
the county it named. Three runs of the withdrawn lines put Nairobi's budget at
KSh 73.0 Bn, then 51.0 Bn, then 24.0 Bn — and in the second run Turkana
received exactly the figures Nairobi had held in the first. The identities were
interchangeable between processes.

A county is a named public body. Its budget and its execution rate are
statements of fact about it, and an attributed failing more so — the same
concern issues #182/#183 raised about rankings, in its stronger form. This file
ships: ``Dockerfile:26`` copies ``extractors/`` into the production image.

What survives fetches and parses. ``extract_cob_consolidated_reports`` reads
the COB publication pages; ``_extract_budget_implementation_data``,
``_find_county_section`` and ``_extract_budget_figures`` pull figures out of
page text with regular expressions; the six ``_extract``/``_get``/``_is``
helpers read report titles. They report nothing when they find nothing, which
is the correct answer when nothing was found.

``run_comprehensive_cob_extraction`` keeps its one real step and lost the
generated one, along with ``implementation_statistics`` — whose
``average_implementation_rate``, ``total_budget_allocation`` and
``best_performers`` ranking of five named counties were all arithmetic over
fabricated records — and ``data_sources.coverage``'s "All 47 Kenya Counties",
which measured nothing: it restated the length of the name-matching roster.
``_generate_cob_recommendations`` is kept and is currently unreferenced,
following the same call made for ``_generate_recommendation`` in
``oag_audit_extractor.py`` under issue #193: it maps a performance band to
generic remediation advice, which is not a claim about any county.
"""

import json
import logging
import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class COBReportExtractor:
    """Specialized extractor for Controller of Budget reports."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        # Disable SSL verification for problematic government sites
        self.session.verify = False
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.cob_reports = []

        # Kenya's 47 counties
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

    def extract_cob_consolidated_reports(self):
        """Extract consolidated county budget implementation review reports."""
        logger.info("📊 Extracting COB Consolidated County Budget Reports...")

        cob_urls = [
            "https://cob.go.ke",
            "https://cob.go.ke/publications/",
            "https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/",
            "https://cob.go.ke/publications/county-budget-implementation-review-reports/",
            "https://cob.go.ke/publications/budget-implementation-review-reports/",
            "https://cob.go.ke/reports/",  # legacy fallback
        ]

        extracted_reports = []

        for url in cob_urls:
            try:
                logger.info(f"🔍 Checking COB URL: {url}")
                response = self.session.get(url, timeout=45)

                if response.status_code == 200:
                    logger.info(f"✅ COB URL accessible: {url}")
                    soup = BeautifulSoup(response.content, "html.parser")

                    # Find PDF links and Excel files
                    document_links = soup.find_all(
                        "a", href=re.compile(r"\.(pdf|xlsx?|doc|docx)$", re.I)
                    )

                    for link in document_links:
                        doc_url = link.get("href")
                        title = link.get_text(strip=True) or link.get(
                            "title", "Unknown Report"
                        )

                        # Focus on county budget implementation reports
                        if self._is_county_budget_report(title, doc_url):
                            report_data = {
                                "title": title,
                                "url": doc_url,
                                "type": "County Budget Implementation Review",
                                "year": self._extract_year(title),
                                "quarter": self._extract_quarter(title),
                                "county": self._extract_county_name(title),
                                "source_page": url,
                                "extracted_date": datetime.now().isoformat(),
                                "file_type": self._get_file_type(doc_url),
                                "budget_period": self._extract_budget_period(title),
                            }

                            extracted_reports.append(report_data)
                            logger.info(f"✅ Found COB Report: {title[:60]}...")

                    # Also look for any text content with budget implementation data
                    text_content = soup.get_text()
                    if "budget implementation" in text_content.lower():
                        budget_data = self._extract_budget_implementation_data(
                            text_content, url
                        )
                        if budget_data:
                            extracted_reports.extend(budget_data)

                else:
                    logger.warning(
                        f"⚠️ COB URL failed: {url} - Status: {response.status_code}"
                    )

            except Exception as e:
                logger.warning(f"⚠️ COB extraction failed for {url}: {str(e)}")
                # Continue with other URLs even if one fails
                continue

        self.cob_reports = extracted_reports
        return extracted_reports

    def _is_county_budget_report(self, title: str, url: str) -> bool:
        """Check if document is a county budget implementation report."""
        keywords = [
            "county budget implementation",
            "consolidated county",
            "budget review",
            "implementation review",
            "county performance",
            "budget absorption",
        ]

        text = f"{title} {url}".lower()
        return any(keyword in text for keyword in keywords)

    def _extract_year(self, title: str) -> Optional[str]:
        """Extract financial year from title."""
        # Look for patterns like 2024/25, 2024-25, FY 2024
        year_patterns = [
            r"20\d{2}/\d{2}",
            r"20\d{2}-\d{2}",
            r"FY\s*20\d{2}",
            r"20\d{2}",
        ]

        for pattern in year_patterns:
            match = re.search(pattern, title)
            if match:
                return match.group()
        return None

    def _extract_quarter(self, title: str) -> Optional[str]:
        """Extract quarter from title."""
        quarter_match = re.search(r"Q[1-4]|Quarter\s*[1-4]", title, re.I)
        return quarter_match.group() if quarter_match else None

    def _extract_county_name(self, title: str) -> Optional[str]:
        """Extract county name from title."""
        title_lower = title.lower()
        for county in self.counties:
            if county.lower() in title_lower:
                return county
        return None

    def _get_file_type(self, url: str) -> str:
        """Get file type from URL."""
        if url.endswith(".pdf"):
            return "PDF"
        elif url.endswith((".xlsx", ".xls")):
            return "Excel"
        elif url.endswith((".docx", ".doc")):
            return "Word"
        else:
            return "Unknown"

    def _extract_budget_period(self, title: str) -> str:
        """Extract budget period from title."""
        if "quarter" in title.lower() or "q" in title.lower():
            return "Quarterly"
        elif "annual" in title.lower():
            return "Annual"
        elif "mid-year" in title.lower():
            return "Mid-Year"
        else:
            return "Periodic"

    def _extract_budget_implementation_data(self, text: str, url: str) -> List[Dict]:
        """Extract budget implementation data from text content."""
        data = []

        # Look for county names and associated budget figures
        for county in self.counties:
            if county.lower() in text.lower():
                # Try to find budget figures near county name
                county_section = self._find_county_section(text, county)
                if county_section:
                    budget_figures = self._extract_budget_figures(county_section)
                    if budget_figures:
                        data.append(
                            {
                                "title": f"{county} Budget Implementation Data",
                                "county": county,
                                "type": "Budget Implementation Data",
                                "source_page": url,
                                "data": budget_figures,
                                "extracted_date": datetime.now().isoformat(),
                            }
                        )

        return data

    def _find_county_section(self, text: str, county: str) -> str:
        """Find text section related to specific county."""
        lines = text.split("\n")
        county_lines = []
        county_found = False

        for line in lines:
            if county.lower() in line.lower():
                county_found = True
                county_lines.append(line)
            elif county_found and len(county_lines) < 10:
                county_lines.append(line)
            elif county_found and len(county_lines) >= 10:
                break

        return "\n".join(county_lines)

    def _extract_budget_figures(self, text: str) -> Dict:
        """Extract budget figures from text."""
        figures = {}

        # Look for common budget terms and associated numbers
        patterns = {
            "budget": r"budget[:\s]*([0-9,]+)",
            "expenditure": r"expenditure[:\s]*([0-9,]+)",
            "allocation": r"allocation[:\s]*([0-9,]+)",
            "absorption": r"absorption[:\s]*([0-9.]+)%?",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.I)
            if match:
                figures[key] = match.group(1)

        return figures

    def _generate_cob_recommendations(self, rate: float) -> List[str]:
        """Generate COB recommendations based on performance."""
        if rate >= 80:
            return [
                "Maintain current performance levels",
                "Focus on quality of service delivery",
                "Share best practices with other counties",
            ]
        elif rate >= 60:
            return [
                "Improve procurement planning and processes",
                "Strengthen project monitoring systems",
                "Enhance revenue collection mechanisms",
            ]
        else:
            return [
                "Urgent review of budget implementation processes",
                "Capacity building for county staff",
                "Implement emergency measures to improve absorption",
                "Establish county implementation committee",
            ]

    def run_comprehensive_cob_extraction(self):
        """Run comprehensive COB report extraction."""
        logger.info("\n" + "=" * 80)
        logger.info("📊 COMPREHENSIVE COB EXTRACTION")
        logger.info("=" * 80)

        start_time = datetime.now()

        cob_reports = self.extract_cob_consolidated_reports()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Compile results
        results = {
            "extraction_summary": {
                "cob_reports_found": len(cob_reports),
                "extraction_duration": duration,
                "timestamp": datetime.now().isoformat(),
            },
            "cob_reports": cob_reports,
            "data_sources": {
                "primary": "Controller of Budget Kenya (cob.go.ke)",
                "report_types": [
                    "Consolidated County Budget Implementation Review",
                    "County Performance Reports",
                ],
                "data_focus": "Budget implementation, absorption rates, revenue performance",
            },
        }

        # Log summary
        logger.info(f"\n📋 COB EXTRACTION COMPLETE:")
        logger.info(f"   📊 COB Reports: {len(cob_reports)}")
        logger.info(f"   ⏱️ Duration: {duration:.1f} seconds")

        return results


def main():
    """Main function to run COB extraction."""
    extractor = COBReportExtractor()
    results = extractor.run_comprehensive_cob_extraction()

    # Save results
    with open("cob_budget_implementation_data.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ COB extraction completed!")
    print(f"📊 COB Reports: {len(results['cob_reports'])}")
    print(f"📁 Results saved to: cob_budget_implementation_data.json")


if __name__ == "__main__":
    main()
