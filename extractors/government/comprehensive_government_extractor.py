"""
Comprehensive Government Reports Extractor
Discovers County and National government report documents from COB, Treasury
and OAG, and downloads the ones it is asked for.

WITHDRAWN 2026-09-07 (issue #193): three methods that typed in a national
government database, and a block that graded the run's own coverage.

    generate_national_government_issues  170-209  seventeen typed figures
    _generate_ministry_performance       212-247  fifteen ministries' money
                                                  from hash(ministry)
    _generate_ministry_issues            249-281  named findings against named
                                                  ministries
    coverage_analysis (in the results)   545-551  "Complete - All 47 counties
                                                  covered", transparency_score 95

The seventeen were an execution rate of 78.5% (development 65.2, recurrent
89.1), 156 audit queries, 45 high-priority issues, KSh 12.5Bn of "irregular
expenditure" and 8.3Bn "unsupported", 23 pending investigations, a debt block
of 10.2T at 67.8% of GDP split 6.1T external / 4.1T domestic, and a revenue
block of 2.8T targeted against 2.45T collected at 87.5%, of which 1.96T tax.
None was read from any document this module fetches. Several were already known
to be invented under other names: 78.5 and 156 are issue #183's, 87.5 is
#188's, and "irregular expenditure" is the classification #182 established the
pipeline does not produce at all. The debt block repeats #188's defects
independently — 10.2T against CBK's 10,925.3Bn for 2024 in
``backend/seeding/real_data/debt_timeline.json``, 67.8% against that fixture's
62.3%, and 59.8% of the stock on the external side where CBK's 2024 share is
46.3% and this repo's own loan register is 47.4% on ``outstanding``.

``_generate_ministry_performance`` was the worse of the two hash-driven
generators in this tree, because #188's drove rates and this one drove money:
each ministry's ``budget_allocation`` was ``(hash(name) % 500000000000) +
100000000000`` and its ``pending_bills`` ``(hash(name) % 10000000000) +
1000000000``. ``hash()`` on a ``str`` is salted per process, so three runs put
Health at KSh 116.4Bn, 147.3Bn and 338.1Bn.

``coverage_analysis`` went for a different reason. It sat in the same dict as
``extraction_summary``, whose ``county_reports`` is ``len(cob_reports.get(
"county", []))`` — a real count. Being literals, it could report "Complete -
All 47 counties covered" and a transparency score of 95 while that count was
zero, and ``:574`` logged the 95 as the run's headline. A self-assessment that
cannot disagree with the thing it assesses reports healthy because it measured
nothing.

WITHDRAWN 2026-09-07 (issue #196): the rest of the self-assessment, twelve
lines below where ``coverage_analysis`` had been.

    api_integration (in the results)     472-482  ``ready_for_ui: True`` and an
                                                  endpoints_available list

``ready_for_ui`` was a literal. It could not become False whatever the run
found, which makes it the same shape as the block above it, and it was the last
of the self-grading in this module.

The endpoint list was worse than unmeasured, because it had become wrong. It
advertised six paths, and three of them — ``/national/issues``,
``/national/ministries`` and ``/national/debt`` — were deleted by PR #191 when
it withdrew the six methods that typed in the national debt. Nothing in the
repo has served them since. The other three do resolve:
``/counties/{county_name}`` at ``apis/modernized_api.py:228``,
``/audit/queries`` at ``:286``, and ``/analytics/summary`` at
``apis/county_analytics_api.py:371``.

``backend/tests/test_advertised_endpoints_are_served.py`` now checks every
advertised path against the routes this repo registers, so a list that outlives
its endpoints fails rather than shipping.

What survives fetches pages, finds document links, downloads them and reports
how many of each it got. Those counts are measurements and they are already in
``extraction_summary``.
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional

import PyPDF2
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ComprehensiveGovernmentExtractor:
    """Comprehensive extractor for both county and national government reports."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        # Handle government site issues
        self.session.verify = False
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.county_reports = []
        self.national_reports = []
        self.treasury_reports = []
        self.oag_national_reports = []

        # Create directories
        os.makedirs("reports/county", exist_ok=True)
        os.makedirs("reports/national", exist_ok=True)
        os.makedirs("reports/treasury", exist_ok=True)
        os.makedirs("reports/oag", exist_ok=True)

    def extract_cob_reports_comprehensive(self):
        """Extract both county and national reports from COB."""
        logger.info("🏛️ Extracting COB County and National Reports...")

        # COB report categories from the website structure
        cob_report_urls = {
            "county_reports": [
                "https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/",
                "https://cob.go.ke/publications/county-budget-implementation-review-reports/",
                "https://cob.go.ke/publications/county-reports/",
            ],
            "national_reports": [
                "https://cob.go.ke/publications/national-reports/",
                "https://cob.go.ke/publications/budget-implementation-review-reports/",
                "https://cob.go.ke/publications/national-government-budget-implementation/",
                "https://cob.go.ke/publications/",
            ],
            "other_reports": [
                "https://cob.go.ke/publications/other-reports/",
                "https://cob.go.ke/publications/expenditure-templates/",
            ],
        }

        extracted_reports = {"county": [], "national": [], "other": []}

        for category, urls in cob_report_urls.items():
            logger.info(f"📊 Processing {category}...")

            for url in urls:
                try:
                    logger.info(f"🔍 Checking: {url}")
                    response = self.session.get(url, timeout=60)

                    if response.status_code == 200:
                        logger.info(f"✅ Accessible: {url}")
                        page_reports = self._extract_reports_from_page(url, category)

                        if category == "county_reports":
                            extracted_reports["county"].extend(page_reports)
                        elif category == "national_reports":
                            extracted_reports["national"].extend(page_reports)
                        else:
                            extracted_reports["other"].extend(page_reports)

                        logger.info(
                            f"📋 Found {len(page_reports)} reports in {category}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Failed: {url} - Status: {response.status_code}"
                        )

                except Exception as e:
                    logger.warning(f"⚠️ Error accessing {url}: {str(e)}")
                    continue

        return extracted_reports

    def extract_treasury_national_reports(self):
        """Extract national budget and fiscal reports from Treasury."""
        logger.info("💰 Extracting National Treasury Reports...")

        treasury_urls = [
            "https://treasury.go.ke/publications/",
            "https://treasury.go.ke/budget/",
            "https://treasury.go.ke/fiscal-and-debt-reports/",
            "https://treasury.go.ke/budget-documents/",
            "https://treasury.go.ke/national-budget/",
        ]

        treasury_reports = []

        for url in treasury_urls:
            try:
                logger.info(f"🔍 Checking Treasury: {url}")
                response = self.session.get(url, timeout=45)

                if response.status_code == 200:
                    logger.info(f"✅ Treasury accessible: {url}")
                    reports = self._extract_reports_from_page(url, "national_treasury")
                    treasury_reports.extend(reports)
                    logger.info(f"📋 Found {len(reports)} Treasury reports")

            except Exception as e:
                logger.warning(f"⚠️ Treasury error {url}: {str(e)}")

        return treasury_reports

    def extract_oag_national_reports(self):
        """Extract national audit reports from OAG."""
        logger.info("🔍 Extracting OAG National Audit Reports...")

        oag_urls = [
            "https://oagkenya.go.ke/index.php/reports/annual-reports",
            "https://oagkenya.go.ke/index.php/reports/special-audit-reports",
            "https://oagkenya.go.ke/index.php/reports/performance-audit-reports",
            "https://oagkenya.go.ke/index.php/reports/financial-audit-reports",
            "https://oagkenya.go.ke/index.php/reports",
        ]

        oag_reports = []

        for url in oag_urls:
            try:
                logger.info(f"🔍 Checking OAG: {url}")
                response = self.session.get(url, timeout=45)

                if response.status_code == 200:
                    logger.info(f"✅ OAG accessible: {url}")
                    reports = self._extract_reports_from_page(url, "national_audit")
                    oag_reports.extend(reports)
                    logger.info(f"📋 Found {len(reports)} OAG reports")

            except Exception as e:
                logger.warning(f"⚠️ OAG error {url}: {str(e)}")

        return oag_reports

    def _extract_reports_from_page(self, url: str, category: str) -> List[Dict]:
        """Extract report links from a webpage."""
        reports = []

        try:
            response = self.session.get(url, timeout=45)
            if response.status_code != 200:
                return reports

            soup = BeautifulSoup(response.content, "html.parser")

            # Find PDF and document links
            doc_links = soup.find_all(
                "a", href=re.compile(r"\.(pdf|xlsx?|docx?)$", re.I)
            )

            for link in doc_links:
                href = link.get("href")
                if not href.startswith("http"):
                    if href.startswith("/"):
                        base_url = f"https://{url.split('/')[2]}"
                        href = f"{base_url}{href}"
                    else:
                        href = f"{url.rstrip('/')}/{href}"

                title = link.get_text(strip=True) or "Unknown Report"

                report_data = {
                    "title": title,
                    "url": href,
                    "category": category,
                    "source_page": url,
                    "file_type": self._get_file_extension(href),
                    "financial_year": self._extract_financial_year(title),
                    "report_type": self._classify_report_type(title, category),
                    "extracted_date": datetime.now().isoformat(),
                    "download_status": "pending",
                }

                reports.append(report_data)

            # Also look for text content that might contain embedded data
            text_content = soup.get_text()
            if any(
                keyword in text_content.lower()
                for keyword in ["budget", "expenditure", "revenue", "audit"]
            ):
                # Extract any numerical data from the page
                data_summary = self._extract_numerical_data(text_content)
                if data_summary:
                    reports.append(
                        {
                            "title": f"Page Data Summary - {category}",
                            "url": url,
                            "category": f"{category}_data",
                            "source_page": url,
                            "file_type": "text_data",
                            "extracted_data": data_summary,
                            "extracted_date": datetime.now().isoformat(),
                        }
                    )

        except Exception as e:
            logger.warning(f"⚠️ Page extraction failed: {url} - {str(e)}")

        return reports

    def _get_file_extension(self, url: str) -> str:
        """Get file extension from URL."""
        return url.split(".")[-1].lower() if "." in url else "unknown"

    def _extract_financial_year(self, text: str) -> str:
        """Extract financial year from text."""
        patterns = [r"FY\s*(20\d{2}[/-]\d{2,4})", r"20\d{2}[/-]\d{2,4}", r"20\d{2}"]

        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1) if "FY" in pattern else match.group()

        return "Unknown"

    def _classify_report_type(self, title: str, category: str) -> str:
        """Classify report type based on title and category."""
        title_lower = title.lower()

        if category == "national_treasury":
            if "budget" in title_lower:
                return "National Budget Document"
            elif "debt" in title_lower:
                return "Debt Management Report"
            elif "fiscal" in title_lower:
                return "Fiscal Report"
            else:
                return "Treasury Document"

        elif category == "national_audit":
            if "annual" in title_lower:
                return "Annual Audit Report"
            elif "special" in title_lower:
                return "Special Audit Report"
            elif "performance" in title_lower:
                return "Performance Audit"
            else:
                return "Audit Report"

        elif category == "national_reports":
            return "National Government Report"

        else:
            return "Government Document"

    def _extract_numerical_data(self, text: str) -> Dict:
        """Extract numerical data from text content."""
        data = {}

        # Look for budget figures
        budget_pattern = r"budget[:\s]*([0-9,]+\.?\d*)"
        budget_match = re.search(budget_pattern, text, re.I)
        if budget_match:
            data["budget_mentioned"] = budget_match.group(1)

        # Look for percentages
        percent_pattern = r"(\d+\.?\d*)%"
        percentages = re.findall(percent_pattern, text)
        if percentages:
            data["percentages_found"] = percentages[:5]  # First 5 percentages

        # Look for years
        year_pattern = r"20\d{2}"
        years = list(set(re.findall(year_pattern, text)))
        if years:
            data["years_mentioned"] = sorted(years)

        return data

    def download_priority_reports(self, all_reports: Dict, max_downloads: int = 20):
        """Download highest priority reports."""
        logger.info(f"📥 Downloading up to {max_downloads} priority reports...")

        # Prioritize recent reports
        priority_reports = []

        for category, reports in all_reports.items():
            for report in reports:
                if report.get("file_type") in ["pdf", "xlsx", "xls"]:
                    fy = report.get("financial_year", "")
                    if any(year in fy for year in ["2024", "2023", "2022"]):
                        priority_reports.append(report)

        # Sort by year (most recent first)
        priority_reports.sort(key=lambda x: x.get("financial_year", ""), reverse=True)

        downloaded_reports = []

        for i, report in enumerate(priority_reports[:max_downloads]):
            try:
                logger.info(
                    f"📥 Downloading [{i+1}/{min(len(priority_reports), max_downloads)}]: {report['title'][:50]}..."
                )

                response = self.session.get(report["url"], timeout=60)
                if response.status_code == 200 and len(response.content) > 1000:

                    # Determine save directory
                    if "county" in report["category"]:
                        save_dir = "reports/county"
                    elif (
                        "national" in report["category"]
                        or "treasury" in report["category"]
                    ):
                        save_dir = "reports/national"
                    elif "audit" in report["category"]:
                        save_dir = "reports/oag"
                    else:
                        save_dir = "reports"

                    # Generate filename
                    filename = self._generate_safe_filename(report)
                    filepath = os.path.join(save_dir, filename)

                    # Save file
                    with open(filepath, "wb") as f:
                        f.write(response.content)

                    report["local_file"] = filepath
                    report["file_size"] = len(response.content)
                    report["download_status"] = "success"

                    downloaded_reports.append(report)
                    logger.info(
                        f"✅ Downloaded: {filename} ({len(response.content):,} bytes)"
                    )

                time.sleep(1)  # Be respectful to servers

            except Exception as e:
                logger.warning(f"⚠️ Download failed: {report['title'][:30]} - {str(e)}")
                report["download_status"] = f"failed: {str(e)}"

        return downloaded_reports

    def _generate_safe_filename(self, report: Dict) -> str:
        """Generate safe filename."""
        title = re.sub(r"[^\w\s-]", "", report["title"])
        title = re.sub(r"\s+", "_", title)
        category = report["category"].replace("_", "-")
        fy = report.get("financial_year", "unknown").replace("/", "-")
        ext = report.get("file_type", "pdf")

        filename = f"{category}_{fy}_{title}"[:100]
        return f"{filename}.{ext}"

    def run_comprehensive_extraction(self):
        """Run comprehensive government reports extraction."""
        logger.info("\n" + "=" * 80)
        logger.info("🏛️ COMPREHENSIVE GOVERNMENT REPORTS EXTRACTION")
        logger.info("=" * 80)

        start_time = datetime.now()

        # Step 1: Extract COB reports (county + national)
        cob_reports = self.extract_cob_reports_comprehensive()

        # Step 2: Extract Treasury national reports
        treasury_reports = self.extract_treasury_national_reports()

        # Step 3: Extract OAG national audit reports
        oag_reports = self.extract_oag_national_reports()

        # Step 4: Download priority reports
        all_reports = {
            **cob_reports,
            "treasury": treasury_reports,
            "oag_national": oag_reports,
        }

        downloaded_reports = self.download_priority_reports(all_reports)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Compile comprehensive results
        results = {
            "extraction_summary": {
                "total_reports_found": sum(
                    len(reports) for reports in all_reports.values()
                ),
                "reports_downloaded": len(downloaded_reports),
                "county_reports": len(cob_reports.get("county", [])),
                "national_reports": len(cob_reports.get("national", []))
                + len(treasury_reports)
                + len(oag_reports),
                "extraction_duration": duration,
                "timestamp": datetime.now().isoformat(),
            },
            "discovered_reports": all_reports,
            "downloaded_reports": downloaded_reports,
        }

        # Log comprehensive summary
        summary = results["extraction_summary"]
        logger.info(f"\n📋 COMPREHENSIVE EXTRACTION COMPLETE:")
        logger.info(f"   📊 Total Reports Found: {summary['total_reports_found']}")
        logger.info(f"   🏛️ County Reports: {summary['county_reports']}")
        logger.info(f"   🇰🇪 National Reports: {summary['national_reports']}")
        logger.info(f"   💾 Downloaded: {summary['reports_downloaded']}")
        logger.info(f"   ⏱️ Duration: {duration:.1f} seconds")

        return results


def main():
    """Main function for comprehensive extraction."""
    extractor = ComprehensiveGovernmentExtractor()
    results = extractor.run_comprehensive_extraction()

    # Save results
    with open("comprehensive_government_reports.json", "w") as f:
        json.dump(results, f, indent=2)

    summary = results["extraction_summary"]
    print(f"\n✅ Comprehensive government extraction completed!")
    print(f"📊 Total Reports: {summary['total_reports_found']}")
    print(
        f"🏛️ County: {summary['county_reports']} | 🇰🇪 National: {summary['national_reports']}"
    )
    print(f"💾 Downloaded: {summary['reports_downloaded']}")
    print(f"📁 Results: comprehensive_government_reports.json")
    print(f"📂 Files: ./reports/ directory")


if __name__ == "__main__":
    main()
