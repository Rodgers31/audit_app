"""Source-access and document-link checks across four government publishers.

No financial observations are extracted by this legacy checker.
"""

import json
import logging
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ComprehensiveKenyaETL:
    """Source checker; financial extraction is unavailable."""

    def __init__(self):
        self.results = {
            "documents_fetched": 0,
            "entities_found": [],
            "sources_checked": [],
            "raw_data": [],
            "errors": [],
            "budget_data": [],
            "audit_findings": [],
            "procurement_data": [],
        }

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    def test_treasury_comprehensive(self):
        """Comprehensive test of Kenya National Treasury."""
        try:
            logger.info("🏛️  Testing Kenya National Treasury (Comprehensive)...")

            # Main treasury site
            response = self.session.get("https://treasury.go.ke", timeout=15)

            result = {
                "source": "Kenya National Treasury",
                "url": "https://treasury.go.ke",
                "status_code": response.status_code,
                "accessible": response.status_code == 200,
                "timestamp": datetime.now().isoformat(),
                "documents": [],
                "budget_documents": [],
                "debt_reports": [],
            }

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")
                result["page_title"] = (
                    soup.find("title").text.strip()
                    if soup.find("title")
                    else "No title"
                )

                # Find all document links
                links = soup.find_all("a", href=True)

                # Categorize documents
                budget_keywords = ["budget", "allocation", "appropriation", "estimates"]
                debt_keywords = ["debt", "loan", "borrowing", "bond"]
                financial_keywords = ["financial", "statement", "report", "expenditure"]

                for link in links:
                    href = link["href"]
                    text = link.get_text().lower()

                    if href.endswith(".pdf"):
                        doc_info = {
                            "url": urljoin("https://treasury.go.ke", href),
                            "title": link.get_text().strip(),
                            "type": "general",
                        }

                        # Categorize documents
                        if any(keyword in text for keyword in budget_keywords):
                            doc_info["type"] = "budget"
                            result["budget_documents"].append(doc_info)
                        elif any(keyword in text for keyword in debt_keywords):
                            doc_info["type"] = "debt"
                            result["debt_reports"].append(doc_info)
                        elif any(keyword in text for keyword in financial_keywords):
                            doc_info["type"] = "financial"

                        result["documents"].append(doc_info)

                result["total_documents"] = len(result["documents"])
                result["budget_documents_count"] = len(result["budget_documents"])
                result["debt_documents_count"] = len(result["debt_reports"])

                logger.info(f"✅ Treasury: Found {result['total_documents']} documents")
                logger.info(f"   📊 Budget docs: {result['budget_documents_count']}")
                logger.info(f"   💰 Debt docs: {result['debt_documents_count']}")

            self.results["sources_checked"].append(result)
            return result

        except Exception as e:
            error_result = {
                "source": "Kenya National Treasury",
                "error": str(e),
                "accessible": False,
                "timestamp": datetime.now().isoformat(),
            }
            logger.error(f"❌ Treasury error: {str(e)}")
            self.results["errors"].append(f"Treasury: {str(e)}")
            self.results["sources_checked"].append(error_result)
            return error_result

    def test_auditor_general_enhanced(self):
        """Enhanced test of Office of Auditor General with multiple attempts."""
        logger.info("🔍 Testing Office of Auditor General (Enhanced)...")

        # Try multiple URLs and approaches
        urls_to_try = [
            "https://oagkenya.go.ke",
            "http://oagkenya.go.ke",
            "https://www.oagkenya.go.ke",
        ]

        for url in urls_to_try:
            try:
                logger.info(f"   Trying: {url}")
                response = self.session.get(url, timeout=20)

                if response.status_code == 200:
                    result = {
                        "source": "Office of Auditor General",
                        "url": url,
                        "status_code": response.status_code,
                        "accessible": True,
                        "timestamp": datetime.now().isoformat(),
                        "audit_reports": [],
                        "special_audits": [],
                    }

                    soup = BeautifulSoup(response.content, "html.parser")
                    result["page_title"] = (
                        soup.find("title").text.strip()
                        if soup.find("title")
                        else "No title"
                    )

                    # Look for audit documents
                    links = soup.find_all("a", href=True)
                    audit_keywords = [
                        "audit",
                        "report",
                        "finding",
                        "compliance",
                        "performance",
                    ]

                    for link in links:
                        text = link.get_text().lower()
                        if any(keyword in text for keyword in audit_keywords):
                            if link["href"].endswith(".pdf"):
                                audit_doc = {
                                    "url": urljoin(url, link["href"]),
                                    "title": link.get_text().strip(),
                                    "type": "audit_report",
                                }
                                result["audit_reports"].append(audit_doc)

                    result["audit_reports_count"] = len(result["audit_reports"])
                    logger.info(
                        f"✅ Auditor General: Found {result['audit_reports_count']} audit reports"
                    )

                    self.results["sources_checked"].append(result)
                    return result

            except Exception as e:
                logger.warning(f"   ❌ Failed {url}: {str(e)}")
                continue

        # If all attempts failed
        error_result = {
            "source": "Office of Auditor General",
            "error": "All connection attempts failed",
            "accessible": False,
            "timestamp": datetime.now().isoformat(),
            "urls_attempted": urls_to_try,
        }
        logger.error("❌ Auditor General: All attempts failed")
        self.results["errors"].append("Auditor General: Connection failed")
        self.results["sources_checked"].append(error_result)
        return error_result

    def test_controller_of_budget(self):
        """Test Controller of Budget website."""
        try:
            logger.info("📋 Testing Controller of Budget...")

            urls_to_try = [
                "https://cob.go.ke",
                "http://cob.go.ke",
                "https://www.cob.go.ke",
            ]

            for url in urls_to_try:
                try:
                    logger.info(f"   Trying: {url}")
                    response = self.session.get(url, timeout=15)

                    if response.status_code == 200:
                        result = {
                            "source": "Controller of Budget",
                            "url": url,
                            "status_code": response.status_code,
                            "accessible": True,
                            "timestamp": datetime.now().isoformat(),
                            "budget_reviews": [],
                            "quarterly_reports": [],
                        }

                        soup = BeautifulSoup(response.content, "html.parser")
                        result["page_title"] = (
                            soup.find("title").text.strip()
                            if soup.find("title")
                            else "No title"
                        )

                        # Look for budget implementation documents
                        links = soup.find_all("a", href=True)
                        budget_keywords = [
                            "budget",
                            "implementation",
                            "review",
                            "quarterly",
                            "expenditure",
                        ]

                        for link in links:
                            text = link.get_text().lower()
                            if any(keyword in text for keyword in budget_keywords):
                                if link["href"].endswith(".pdf"):
                                    doc = {
                                        "url": urljoin(url, link["href"]),
                                        "title": link.get_text().strip(),
                                        "type": "budget_review",
                                    }
                                    result["budget_reviews"].append(doc)

                        result["budget_reviews_count"] = len(result["budget_reviews"])
                        logger.info(
                            f"✅ Controller of Budget: Found {result['budget_reviews_count']} budget reports"
                        )

                        self.results["sources_checked"].append(result)
                        return result

                except Exception as e:
                    logger.warning(f"   ❌ Failed {url}: {str(e)}")
                    continue

            # If all attempts failed
            error_result = {
                "source": "Controller of Budget",
                "error": "All connection attempts failed",
                "accessible": False,
                "timestamp": datetime.now().isoformat(),
            }
            logger.error("❌ Controller of Budget: All attempts failed")
            self.results["errors"].append("Controller of Budget: Connection failed")
            self.results["sources_checked"].append(error_result)
            return error_result

        except Exception as e:
            error_result = {
                "source": "Controller of Budget",
                "error": str(e),
                "accessible": False,
                "timestamp": datetime.now().isoformat(),
            }
            logger.error(f"❌ Controller of Budget error: {str(e)}")
            self.results["errors"].append(f"Controller of Budget: {str(e)}")
            self.results["sources_checked"].append(error_result)
            return error_result

    def test_parliament_budget_office(self):
        """Test Parliament Budget Office for additional budget data."""
        try:
            logger.info("🏛️  Testing Parliament Budget Office...")

            urls_to_try = [
                "https://www.parliament.go.ke",
                "http://www.parliament.go.ke",
            ]

            for url in urls_to_try:
                try:
                    response = self.session.get(url, timeout=15)

                    if response.status_code == 200:
                        result = {
                            "source": "Parliament Budget Office",
                            "url": url,
                            "status_code": response.status_code,
                            "accessible": True,
                            "timestamp": datetime.now().isoformat(),
                            "parliamentary_reports": [],
                        }

                        soup = BeautifulSoup(response.content, "html.parser")
                        result["page_title"] = (
                            soup.find("title").text.strip()
                            if soup.find("title")
                            else "No title"
                        )

                        # Look for budget-related parliamentary documents
                        links = soup.find_all("a", href=True)
                        for link in links:
                            text = link.get_text().lower()
                            if "budget" in text and link["href"].endswith(".pdf"):
                                doc = {
                                    "url": urljoin(url, link["href"]),
                                    "title": link.get_text().strip(),
                                    "type": "parliamentary_budget",
                                }
                                result["parliamentary_reports"].append(doc)

                        result["parliamentary_reports_count"] = len(
                            result["parliamentary_reports"]
                        )
                        logger.info(
                            f"✅ Parliament: Found {result['parliamentary_reports_count']} budget reports"
                        )

                        self.results["sources_checked"].append(result)
                        return result

                except Exception as e:
                    logger.warning(f"   ❌ Failed {url}: {str(e)}")
                    continue

            # If all attempts failed
            error_result = {
                "source": "Parliament Budget Office",
                "error": "Connection attempts failed",
                "accessible": False,
                "timestamp": datetime.now().isoformat(),
            }
            self.results["sources_checked"].append(error_result)
            return error_result

        except Exception as e:
            error_result = {
                "source": "Parliament Budget Office",
                "error": str(e),
                "accessible": False,
                "timestamp": datetime.now().isoformat(),
            }
            self.results["sources_checked"].append(error_result)
            return error_result

    def run_comprehensive_pipeline(self):
        """Check source access and discover links; no financial extraction exists."""
        self.results = {
            "documents_fetched": 0,
            "entities_found": [],
            "sources_checked": [],
            "raw_data": [],
            "errors": [],
        }
        sources = []
        for check in (
            self.test_treasury_comprehensive,
            self.test_auditor_general_enhanced,
            self.test_controller_of_budget,
            self.test_parliament_budget_office,
        ):
            sources.append(check())
            time.sleep(2)  # Preserve the legacy pause between publisher checks.
        self.results["sources_checked"] = sources
        failures = [s for s in sources if s.get("accessible") is not True]
        self.results["errors"] = [
            f"{s['source']}: {s.get('error', 'HTTP ' + str(s.get('status_code')))}"
            for s in failures
        ]
        return {
            "pipeline_status": (
                "source_checks_failed" if failures else "source_checks_completed"
            ),
            "timestamp": datetime.now().isoformat(),
            "sources_tested": len(sources),
            "sources_accessible": len(sources) - len(failures),
            "errors_encountered": len(failures),
            "financial_data": None,
            "financial_data_status": "not_extracted",
            "detailed_results": self.results,
        }


def main():
    """Save source observations; HTTP/link discovery is not financial data."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="comprehensive_etl_results.json")
    args = parser.parse_args()
    etl = ComprehensiveKenyaETL()
    results = etl.run_comprehensive_pipeline()
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Source observations saved to: {args.output}; financial data not extracted")
    return results


if __name__ == "__main__":
    sys.exit(1 if main()["errors_encountered"] else 0)
