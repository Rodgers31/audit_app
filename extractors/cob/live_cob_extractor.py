"""
Enhanced COB Report Extractor - Live Website Integration
Automatically extracts and processes real COB reports from cob.go.ke
Builds a future-proof system for continuous report monitoring
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional

import pandas as pd
import PyPDF2
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LiveCOBExtractor:
    """Live extractor for COB reports with automatic PDF processing."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )

        # Handle SSL issues with government sites
        self.session.verify = False
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.reports = []
        self.pdf_cache = {}
        self.county_data = {}

        # Create reports directory
        os.makedirs("cob_reports", exist_ok=True)
        os.makedirs("cob_data", exist_ok=True)

    def discover_cob_report_structure(self):
        """Discover the current COB website structure and available reports."""
        logger.info("🔍 Discovering COB website structure...")

        base_url = "https://cob.go.ke"
        discovered_urls = []

        try:
            # Start with main reports page
            main_response = self.session.get(f"{base_url}/reports/", timeout=30)
            if main_response.status_code == 200:
                soup = BeautifulSoup(main_response.content, "html.parser")

                # Find all report category links
                report_links = soup.find_all("a", href=True)
                for link in report_links:
                    href = link.get("href", "")
                    text = link.get_text(strip=True).lower()

                    # Look for county budget implementation related links
                    if any(
                        keyword in text
                        for keyword in [
                            "county budget implementation",
                            "consolidated county",
                            "budget implementation review",
                            "county budget review",
                            "implementation report",
                        ]
                    ):
                        full_url = (
                            href if href.startswith("http") else f"{base_url}{href}"
                        )
                        discovered_urls.append(
                            {
                                "url": full_url,
                                "title": link.get_text(strip=True),
                                "category": "County Budget Implementation",
                            }
                        )
                        logger.info(
                            f"📊 Found report category: {link.get_text(strip=True)}"
                        )

                # Also check for direct PDF links in main page
                pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))
                for pdf_link in pdf_links:
                    pdf_url = pdf_link.get("href")
                    if not pdf_url.startswith("http"):
                        pdf_url = f"{base_url}{pdf_url}"

                    discovered_urls.append(
                        {
                            "url": pdf_url,
                            "title": pdf_link.get_text(strip=True),
                            "category": "Direct PDF",
                            "file_type": "PDF",
                        }
                    )

        except Exception as e:
            logger.warning(f"⚠️ Main discovery failed: {str(e)}")

        # Try the specific consolidated reports URL you showed
        consolidated_url = "https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/"
        try:
            logger.info(f"🔍 Checking consolidated reports: {consolidated_url}")
            response = self.session.get(consolidated_url, timeout=45)
            if response.status_code == 200:
                discovered_urls.append(
                    {
                        "url": consolidated_url,
                        "title": "Consolidated County Budget Implementation Review Reports",
                        "category": "Primary Target",
                        "priority": "high",
                    }
                )
                logger.info("✅ Found consolidated reports page!")
            else:
                logger.warning(
                    f"⚠️ Consolidated reports page returned: {response.status_code}"
                )
        except Exception as e:
            logger.warning(f"⚠️ Consolidated reports check failed: {str(e)}")

        return discovered_urls

    def extract_reports_from_page(self, page_url: str, category: str = "Unknown"):
        """Extract all available reports from a specific page."""
        logger.info(f"📄 Extracting reports from: {page_url}")

        extracted_reports = []

        try:
            response = self.session.get(page_url, timeout=45)
            if response.status_code != 200:
                logger.warning(
                    f"⚠️ Page failed: {page_url} - Status: {response.status_code}"
                )
                return extracted_reports

            soup = BeautifulSoup(response.content, "html.parser")

            # Look for financial year sections (like FY 2021/2022, etc.)
            fy_sections = soup.find_all(
                ["div", "section", "h2", "h3"], string=re.compile(r"FY\s*20\d{2}", re.I)
            )

            for section in fy_sections:
                fy_text = section.get_text(strip=True)
                fy_match = re.search(r"FY\s*(20\d{2}[/-]\d{2,4})", fy_text, re.I)
                financial_year = fy_match.group(1) if fy_match else "Unknown"

                logger.info(f"📅 Found financial year section: {financial_year}")

                # Find all PDF links in this section
                parent = section.parent or section
                pdf_links = parent.find_all("a", href=re.compile(r"\.pdf$", re.I))

                for pdf_link in pdf_links:
                    pdf_url = pdf_link.get("href")
                    if not pdf_url.startswith("http"):
                        pdf_url = f"https://cob.go.ke{pdf_url}"

                    title = pdf_link.get_text(strip=True) or "Unknown Report"

                    report_data = {
                        "title": title,
                        "url": pdf_url,
                        "financial_year": financial_year,
                        "category": category,
                        "source_page": page_url,
                        "report_type": self._classify_report_type(title),
                        "quarter": self._extract_quarter(title),
                        "extracted_date": datetime.now().isoformat(),
                        "file_size": None,
                        "download_status": "pending",
                    }

                    extracted_reports.append(report_data)
                    logger.info(f"📋 Found report: {title[:50]}... ({financial_year})")

            # Also look for any standalone PDF links
            standalone_pdfs = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))
            for pdf_link in standalone_pdfs:
                if pdf_link not in [
                    r
                    for reports in extracted_reports
                    for r in reports
                    if "pdf_link" in r
                ]:
                    pdf_url = pdf_link.get("href")
                    if not pdf_url.startswith("http"):
                        pdf_url = f"https://cob.go.ke{pdf_url}"

                    title = pdf_link.get_text(strip=True) or "Unknown Report"

                    report_data = {
                        "title": title,
                        "url": pdf_url,
                        "financial_year": self._extract_fy_from_title(title),
                        "category": f"{category} - Standalone",
                        "source_page": page_url,
                        "report_type": self._classify_report_type(title),
                        "quarter": self._extract_quarter(title),
                        "extracted_date": datetime.now().isoformat(),
                        "download_status": "pending",
                    }

                    extracted_reports.append(report_data)

        except Exception as e:
            logger.error(f"❌ Failed to extract from {page_url}: {str(e)}")

        return extracted_reports

    def download_and_process_pdf(self, report: Dict) -> Dict:
        """Download PDF and extract basic information."""
        logger.info(f"📥 Downloading: {report['title'][:50]}...")

        try:
            response = self.session.get(report["url"], timeout=60)
            if response.status_code == 200:
                # Save PDF file
                filename = self._generate_filename(report)
                filepath = os.path.join("cob_reports", filename)

                with open(filepath, "wb") as f:
                    f.write(response.content)

                report["local_file"] = filepath
                report["file_size"] = len(response.content)
                report["download_status"] = "success"

                # Try to extract basic info from PDF
                try:
                    pdf_info = self._extract_pdf_info(response.content)
                    report.update(pdf_info)
                except Exception as e:
                    logger.warning(
                        f"⚠️ PDF processing failed for {report['title']}: {str(e)}"
                    )

                logger.info(
                    f"✅ Downloaded: {filename} ({len(response.content):,} bytes)"
                )

            else:
                report["download_status"] = f"failed - HTTP {response.status_code}"
                logger.warning(f"⚠️ Download failed: {report['url']}")

        except Exception as e:
            report["download_status"] = f"error - {str(e)}"
            logger.error(f"❌ Download error: {str(e)}")

        return report

    def _classify_report_type(self, title: str) -> str:
        """Classify the type of report based on title."""
        title_lower = title.lower()

        if "annual" in title_lower:
            return "Annual Report"
        elif any(q in title_lower for q in ["first quarter", "q1", "quarter 1"]):
            return "Q1 Report"
        elif any(q in title_lower for q in ["second quarter", "q2", "quarter 2"]):
            return "Q2 Report"
        elif any(q in title_lower for q in ["third quarter", "q3", "quarter 3"]):
            return "Q3 Report"
        elif any(q in title_lower for q in ["fourth quarter", "q4", "quarter 4"]):
            return "Q4 Report"
        elif "half" in title_lower:
            return "Half-Year Report"
        elif "consolidated" in title_lower:
            return "Consolidated Report"
        else:
            return "General Report"

    def _extract_quarter(self, title: str) -> Optional[str]:
        """Extract quarter information from title."""
        quarter_patterns = [
            r"first\s+quarter|q1|quarter\s+1",
            r"second\s+quarter|q2|quarter\s+2",
            r"third\s+quarter|q3|quarter\s+3",
            r"fourth\s+quarter|q4|quarter\s+4",
        ]

        quarters = ["Q1", "Q2", "Q3", "Q4"]

        for i, pattern in enumerate(quarter_patterns):
            if re.search(pattern, title, re.I):
                return quarters[i]

        return None

    def _extract_fy_from_title(self, title: str) -> str:
        """Extract financial year from title."""
        fy_patterns = [r"FY\s*(20\d{2}[/-]\d{2,4})", r"20\d{2}[/-]\d{2,4}", r"20\d{2}"]

        for pattern in fy_patterns:
            match = re.search(pattern, title, re.I)
            if match:
                return match.group(1) if "FY" in pattern else match.group()

        return "Unknown"

    def _generate_filename(self, report: Dict) -> str:
        """Generate a clean filename for the PDF."""
        title = re.sub(r"[^\w\s-]", "", report["title"])
        title = re.sub(r"\s+", "_", title)
        fy = report.get("financial_year", "Unknown").replace("/", "-")
        quarter = report.get("quarter", "")

        filename = f"COB_{fy}_{quarter}_{title}"[:100]  # Limit length
        return f"{filename}.pdf"

    def _extract_pdf_info(self, pdf_content: bytes) -> Dict:
        """Extract basic information from PDF content."""
        info = {}

        try:
            pdf_file = BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            info["page_count"] = len(pdf_reader.pages)

            # Try to extract some text from first few pages
            text_content = ""
            for i in range(min(3, len(pdf_reader.pages))):
                page = pdf_reader.pages[i]
                text_content += page.extract_text()

            info["preview_text"] = text_content[:500]  # First 500 characters

            # Look for county names in content
            counties_found = []
            for county in [
                "Nairobi",
                "Mombasa",
                "Nakuru",
                "Kiambu",
                "Kakamega",
            ]:  # Sample counties
                if county.lower() in text_content.lower():
                    counties_found.append(county)

            info["counties_mentioned"] = counties_found

        except Exception as e:
            logger.warning(f"⚠️ PDF info extraction failed: {str(e)}")
            info["extraction_error"] = str(e)

        return info

    def run_comprehensive_live_extraction(self):
        """Run comprehensive live extraction from COB website."""
        logger.info("\n" + "=" * 80)
        logger.info("🔥 LIVE COB COMPREHENSIVE EXTRACTION")
        logger.info("=" * 80)

        start_time = datetime.now()

        # Step 1: Discover website structure
        discovered_pages = self.discover_cob_report_structure()
        logger.info(f"🔍 Discovered {len(discovered_pages)} report pages/categories")

        all_reports = []

        # Step 2: Extract reports from each discovered page
        for page_info in discovered_pages:
            page_url = page_info["url"]
            category = page_info.get("category", "Unknown")

            if page_url.endswith(".pdf"):
                # Direct PDF link
                report_data = {
                    "title": page_info["title"],
                    "url": page_url,
                    "financial_year": self._extract_fy_from_title(page_info["title"]),
                    "category": category,
                    "source_page": "Direct Link",
                    "report_type": self._classify_report_type(page_info["title"]),
                    "quarter": self._extract_quarter(page_info["title"]),
                    "extracted_date": datetime.now().isoformat(),
                    "download_status": "pending",
                }
                all_reports.append(report_data)
            else:
                # Page with multiple reports
                page_reports = self.extract_reports_from_page(page_url, category)
                all_reports.extend(page_reports)

        logger.info(f"📊 Found {len(all_reports)} total reports")

        # Step 3: Download and process PDFs (limit to recent reports for demo)
        processed_reports = []
        recent_reports = [
            r
            for r in all_reports
            if "2024" in str(r.get("financial_year", ""))
            or "2023" in str(r.get("financial_year", ""))
        ][
            :10
        ]  # Limit to 10 recent reports

        for report in recent_reports:
            processed_report = self.download_and_process_pdf(report)
            processed_reports.append(processed_report)
            time.sleep(2)  # Be respectful to the server

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Compile results
        results = {
            "extraction_summary": {
                "total_reports_discovered": len(all_reports),
                "reports_downloaded": len(
                    [
                        r
                        for r in processed_reports
                        if r.get("download_status") == "success"
                    ]
                ),
                "failed_downloads": len(
                    [
                        r
                        for r in processed_reports
                        if "failed" in str(r.get("download_status", ""))
                    ]
                ),
                "pages_discovered": len(discovered_pages),
                "extraction_duration": duration,
                "timestamp": datetime.now().isoformat(),
            },
            "discovered_pages": discovered_pages,
            "all_reports": all_reports,
            "processed_reports": processed_reports,
            "report_statistics": {
                "by_year": self._group_reports_by_year(all_reports),
                "by_type": self._group_reports_by_type(all_reports),
                "by_quarter": self._group_reports_by_quarter(all_reports),
            },
            "data_sources": {
                "primary": "Controller of Budget Kenya (cob.go.ke)",
                "extraction_method": "Live website scraping",
                "future_proof": True,
                "automatic_updates": "Possible with scheduling",
            },
        }

        # Log summary
        summary = results["extraction_summary"]
        logger.info(f"\n📋 LIVE COB EXTRACTION COMPLETE:")
        logger.info(f"   📊 Reports Discovered: {summary['total_reports_discovered']}")
        logger.info(f"   💾 Successfully Downloaded: {summary['reports_downloaded']}")
        logger.info(f"   ❌ Failed Downloads: {summary['failed_downloads']}")
        logger.info(f"   🔍 Pages Processed: {summary['pages_discovered']}")
        logger.info(f"   ⏱️ Duration: {duration:.1f} seconds")

        return results

    def _group_reports_by_year(self, reports: List[Dict]) -> Dict:
        """Group reports by financial year."""
        by_year = {}
        for report in reports:
            year = report.get("financial_year", "Unknown")
            if year not in by_year:
                by_year[year] = 0
            by_year[year] += 1
        return by_year

    def _group_reports_by_type(self, reports: List[Dict]) -> Dict:
        """Group reports by type."""
        by_type = {}
        for report in reports:
            report_type = report.get("report_type", "Unknown")
            if report_type not in by_type:
                by_type[report_type] = 0
            by_type[report_type] += 1
        return by_type

    def _group_reports_by_quarter(self, reports: List[Dict]) -> Dict:
        """Group reports by quarter."""
        by_quarter = {}
        for report in reports:
            quarter = report.get("quarter", "Annual/Other")
            if quarter not in by_quarter:
                by_quarter[quarter] = 0
            by_quarter[quarter] += 1
        return by_quarter


def main():
    """Main function to run live COB extraction."""
    extractor = LiveCOBExtractor()
    results = extractor.run_comprehensive_live_extraction()

    # Save results
    with open("live_cob_extraction_results.json", "w") as f:
        json.dump(results, f, indent=2)

    summary = results["extraction_summary"]
    print(f"\n✅ Live COB extraction completed!")
    print(f"📊 Reports Discovered: {summary['total_reports_discovered']}")
    print(f"💾 Downloaded: {summary['reports_downloaded']}")
    print(f"📁 Results saved to: live_cob_extraction_results.json")
    print(f"📂 PDFs saved to: ./cob_reports/")


if __name__ == "__main__":
    main()
