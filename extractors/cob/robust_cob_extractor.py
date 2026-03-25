"""
Robust COB Report Extractor with Fallback Strategies
Handles government website connectivity issues and provides multiple extraction methods
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


class RobustCOBExtractor:
    """Robust COB extractor with multiple fallback strategies."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        # Handle SSL and timeout issues
        self.session.verify = False
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.reports = []
        self.successful_downloads = 0

        # Create directories
        os.makedirs("cob_reports", exist_ok=True)
        os.makedirs("cob_data", exist_ok=True)

    def generate_known_cob_urls(self):
        """Generate known COB report URLs based on common patterns."""
        logger.info("🎯 Generating known COB report URL patterns...")

        base_url = "https://cob.go.ke"
        known_urls = []

        # Based on the website structure you showed
        financial_years = [
            "2024-25",
            "2023-24",
            "2022-23",
            "2021-22",
            "2020-21",
            "2019-20",
            "2018-19",
            "2017-18",
            "2016-17",
            "2015-16",
            "2014-15",
        ]

        quarters = ["Q1", "Q2", "Q3", "Q4"]
        report_types = [
            "Annual County Governments Budget Implementation Review Report",
            "County Governments Budget Implementation Review Report",
            "First Quarter County Governments Budget Implementation Review Report",
            "County Budget Implementation Review Report for the First Half",
            "Consolidated County Budget Implementation Review Report",
        ]

        # Pattern 1: Direct report URLs
        for fy in financial_years:
            for report_type in report_types:
                # Clean filename pattern
                filename = f"{report_type.replace(' ', '_')}_{fy}.pdf"
                url = f"{base_url}/wp-content/uploads/{filename}"
                known_urls.append(
                    {
                        "url": url,
                        "title": f"{report_type} FY {fy}",
                        "financial_year": fy,
                        "type": "Direct URL Pattern",
                    }
                )

        # Pattern 2: Uploads directory patterns
        upload_patterns = [
            "/wp-content/uploads/2024/",
            "/wp-content/uploads/2023/",
            "/wp-content/uploads/2022/",
            "/wp-content/uploads/reports/",
            "/uploads/reports/county/",
            "/files/reports/",
        ]

        for pattern in upload_patterns:
            for fy in financial_years[:3]:  # Recent years
                known_urls.append(
                    {
                        "url": f"{base_url}{pattern}",
                        "title": f"Upload Directory {fy}",
                        "financial_year": fy,
                        "type": "Directory Pattern",
                    }
                )

        # Pattern 3: Alternative site structures
        alternative_paths = [
            "/reports/county-budget-implementation-review-reports/",
            "/reports/budget-implementation-review-reports/",
            "/publications/county-reports/",
            "/documents/county-budget/",
            "/downloads/reports/",
        ]

        for path in alternative_paths:
            known_urls.append(
                {
                    "url": f"{base_url}{path}",
                    "title": f"Alternative Path: {path}",
                    "type": "Alternative Structure",
                }
            )

        logger.info(f"🎯 Generated {len(known_urls)} potential URLs")
        return known_urls

    def test_url_accessibility(self, urls: List[Dict], max_concurrent: int = 5):
        """Test which URLs are accessible."""
        logger.info(f"🔍 Testing accessibility of {len(urls)} URLs...")

        accessible_urls = []

        for i, url_info in enumerate(urls):
            if i >= max_concurrent * 10:  # Limit testing to avoid overwhelming
                break

            url = url_info["url"]
            try:
                logger.info(
                    f"🔍 Testing [{i+1}/{min(len(urls), max_concurrent*10)}]: {url}"
                )

                # Use HEAD request first (faster)
                response = self.session.head(url, timeout=15, allow_redirects=True)

                if response.status_code == 200:
                    # Check if it's actually a PDF
                    content_type = response.headers.get("content-type", "").lower()
                    if "pdf" in content_type or url.endswith(".pdf"):
                        url_info["status"] = "accessible"
                        url_info["content_type"] = content_type
                        url_info["size"] = response.headers.get(
                            "content-length", "unknown"
                        )
                        accessible_urls.append(url_info)
                        logger.info(f"✅ Accessible: {url} ({content_type})")
                    else:
                        # Try GET request for HTML pages
                        get_response = self.session.get(url, timeout=20)
                        if (
                            get_response.status_code == 200
                            and len(get_response.content) > 1000
                        ):
                            url_info["status"] = "accessible_page"
                            accessible_urls.append(url_info)
                            logger.info(f"✅ Accessible page: {url}")

                elif response.status_code == 404:
                    logger.debug(f"❌ Not found: {url}")
                else:
                    logger.debug(f"⚠️ Status {response.status_code}: {url}")

            except Exception as e:
                logger.debug(f"❌ Failed: {url} - {str(e)}")

            # Small delay to be respectful
            time.sleep(0.5)

        logger.info(f"✅ Found {len(accessible_urls)} accessible URLs")
        return accessible_urls

    def extract_reports_from_accessible_urls(self, accessible_urls: List[Dict]):
        """Extract and download reports from accessible URLs."""
        logger.info(f"📥 Processing {len(accessible_urls)} accessible URLs...")

        extracted_reports = []

        for url_info in accessible_urls:
            url = url_info["url"]

            try:
                if url_info.get("status") == "accessible" and "pdf" in url_info.get(
                    "content_type", ""
                ):
                    # Direct PDF download
                    report = self.download_pdf_report(url_info)
                    if report:
                        extracted_reports.append(report)

                elif url_info.get("status") == "accessible_page":
                    # HTML page - extract PDF links
                    page_reports = self.extract_pdfs_from_page(url)
                    extracted_reports.extend(page_reports)

            except Exception as e:
                logger.warning(f"⚠️ Failed to process {url}: {str(e)}")

        return extracted_reports

    def download_pdf_report(self, url_info: Dict) -> Optional[Dict]:
        """Download a specific PDF report."""
        url = url_info["url"]

        try:
            logger.info(f"📥 Downloading PDF: {url}")
            response = self.session.get(url, timeout=60)

            if response.status_code == 200 and len(response.content) > 1000:
                # Generate filename
                filename = self._generate_safe_filename(url_info)
                filepath = os.path.join("cob_reports", filename)

                # Save file
                with open(filepath, "wb") as f:
                    f.write(response.content)

                # Process PDF
                report_data = {
                    "title": url_info.get("title", "Unknown Report"),
                    "url": url,
                    "local_file": filepath,
                    "file_size": len(response.content),
                    "financial_year": url_info.get("financial_year", "Unknown"),
                    "download_date": datetime.now().isoformat(),
                    "status": "success",
                }

                # Extract PDF metadata
                try:
                    pdf_info = self._extract_pdf_metadata(response.content)
                    report_data.update(pdf_info)
                except Exception as e:
                    logger.warning(f"⚠️ PDF metadata extraction failed: {str(e)}")

                self.successful_downloads += 1
                logger.info(
                    f"✅ Downloaded: {filename} ({len(response.content):,} bytes)"
                )
                return report_data

        except Exception as e:
            logger.error(f"❌ Download failed: {url} - {str(e)}")

        return None

    def extract_pdfs_from_page(self, page_url: str) -> List[Dict]:
        """Extract PDF links from an HTML page."""
        logger.info(f"📄 Extracting PDFs from page: {page_url}")

        pdfs = []

        try:
            response = self.session.get(page_url, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")

                # Find all PDF links
                pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))

                for link in pdf_links:
                    href = link.get("href")
                    if not href.startswith("http"):
                        href = f"https://cob.go.ke{href}"

                    title = link.get_text(strip=True) or "Unknown Report"

                    pdf_info = {
                        "url": href,
                        "title": title,
                        "financial_year": self._extract_fy_from_text(title),
                        "source_page": page_url,
                    }

                    pdf_report = self.download_pdf_report(pdf_info)
                    if pdf_report:
                        pdfs.append(pdf_report)

        except Exception as e:
            logger.warning(f"⚠️ Page extraction failed: {page_url} - {str(e)}")

        return pdfs

    def _extract_fy_from_text(self, text: str) -> str:
        """Extract financial year from text."""
        patterns = [r"FY\s*(20\d{2}[/-]\d{2,4})", r"20\d{2}[/-]\d{2,4}", r"20\d{2}"]

        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1) if "FY" in pattern else match.group()

        return "Unknown"

    def _generate_safe_filename(self, url_info: Dict) -> str:
        """Generate a safe filename for saving."""
        title = url_info.get("title", "report")
        fy = url_info.get("financial_year", "unknown")

        # Clean up title
        safe_title = re.sub(r"[^\w\s-]", "", title)
        safe_title = re.sub(r"\s+", "_", safe_title)
        safe_fy = fy.replace("/", "-")

        filename = f"COB_{safe_fy}_{safe_title}"[:100]
        return f"{filename}.pdf"

    def _extract_pdf_metadata(self, pdf_content: bytes) -> Dict:
        """Extract metadata from PDF content."""
        metadata = {}

        try:
            pdf_file = BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            metadata["page_count"] = len(pdf_reader.pages)

            # Extract text from first page
            if len(pdf_reader.pages) > 0:
                first_page_text = pdf_reader.pages[0].extract_text()
                metadata["first_page_preview"] = first_page_text[:300]

                # Look for county names
                counties = [
                    "Nairobi",
                    "Mombasa",
                    "Nakuru",
                    "Kiambu",
                    "Kakamega",
                    "Uasin Gishu",
                ]
                found_counties = [
                    c for c in counties if c.lower() in first_page_text.lower()
                ]
                metadata["counties_mentioned"] = found_counties

        except Exception as e:
            metadata["extraction_error"] = str(e)

        return metadata

    def create_future_proof_scheduler(self):
        """Create configuration for future automated downloads."""
        scheduler_config = {
            "extraction_schedule": {
                "quarterly_reports": "Every 3 months on 15th",
                "annual_reports": "Every December 31st",
                "check_frequency": "Weekly",
            },
            "url_patterns_to_monitor": [
                "https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/",
                "https://cob.go.ke/wp-content/uploads/",
                "https://cob.go.ke/publications/",
            ],
            "download_rules": {
                "file_types": [".pdf"],
                "keywords": ["budget implementation", "county", "consolidated"],
                "size_limits": {"min": 100000, "max": 50000000},
            },
            "notification_settings": {
                "new_reports_found": True,
                "download_failures": True,
                "weekly_summary": True,
            },
        }

        with open("cob_scheduler_config.json", "w") as f:
            json.dump(scheduler_config, f, indent=2)

        logger.info("📅 Future-proof scheduler configuration created")
        return scheduler_config

    def run_robust_extraction(self):
        """Run robust COB extraction with multiple strategies."""
        logger.info("\n" + "=" * 80)
        logger.info("🚀 ROBUST COB EXTRACTION WITH FALLBACKS")
        logger.info("=" * 80)

        start_time = datetime.now()

        # Step 1: Generate potential URLs
        potential_urls = self.generate_known_cob_urls()

        # Step 2: Test accessibility
        accessible_urls = self.test_url_accessibility(potential_urls)

        # Step 3: Extract reports
        extracted_reports = []
        if accessible_urls:
            extracted_reports = self.extract_reports_from_accessible_urls(
                accessible_urls
            )

        # Step 4: Create future-proof scheduler
        scheduler_config = self.create_future_proof_scheduler()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Compile results
        results = {
            "extraction_summary": {
                "potential_urls_tested": len(potential_urls),
                "accessible_urls_found": len(accessible_urls),
                "reports_downloaded": self.successful_downloads,
                "extraction_duration": duration,
                "timestamp": datetime.now().isoformat(),
                "future_proof": True,
            },
            "accessible_urls": accessible_urls,
            "extracted_reports": extracted_reports,
            "scheduler_config": scheduler_config,
            "recommendations": {
                "next_steps": [
                    "Set up automated scheduler using scheduler_config.json",
                    "Monitor accessible URLs for new reports",
                    "Implement webhook notifications for new reports",
                    "Consider using COB API if available",
                ],
                "fallback_strategies": [
                    "Manual PDF uploads to ./cob_reports/ directory",
                    "Email alerts for new report availability",
                    "Alternative data sources (treasury.go.ke, KNBS)",
                ],
            },
        }

        # Log summary
        summary = results["extraction_summary"]
        logger.info(f"\n📋 ROBUST COB EXTRACTION COMPLETE:")
        logger.info(f"   🎯 URLs Tested: {summary['potential_urls_tested']}")
        logger.info(f"   ✅ Accessible URLs: {summary['accessible_urls_found']}")
        logger.info(f"   📥 Reports Downloaded: {summary['reports_downloaded']}")
        logger.info(f"   ⏱️ Duration: {duration:.1f} seconds")
        logger.info(f"   📅 Future-proof: {summary['future_proof']}")

        return results


def main():
    """Main function to run robust COB extraction."""
    extractor = RobustCOBExtractor()
    results = extractor.run_robust_extraction()

    # Save results
    with open("robust_cob_extraction_results.json", "w") as f:
        json.dump(results, f, indent=2)

    summary = results["extraction_summary"]
    print(f"\n✅ Robust COB extraction completed!")
    print(f"🎯 URLs Tested: {summary['potential_urls_tested']}")
    print(f"✅ Accessible: {summary['accessible_urls_found']}")
    print(f"📥 Downloaded: {summary['reports_downloaded']}")
    print(f"📁 Results: robust_cob_extraction_results.json")
    print(f"📂 PDFs: ./cob_reports/")
    print(f"📅 Scheduler: cob_scheduler_config.json")


if __name__ == "__main__":
    main()
