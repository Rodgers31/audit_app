"""Source-access and document-link checks for Kenya government websites.

No financial observations are extracted by this legacy checker.
"""

import json
import logging
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleKenyaETL:
    """Source checker; financial extraction is unavailable."""

    def __init__(self):
        self.results = {
            "documents_fetched": 0,
            "entities_found": [],
            "sources_checked": [],
            "raw_data": [],
            "errors": [],
        }

    def test_treasury_connection(self):
        """Test connection to Kenya National Treasury website."""
        try:
            logger.info("Testing Kenya National Treasury connection...")
            response = requests.get("https://treasury.go.ke", timeout=10)

            result = {
                "source": "Kenya National Treasury",
                "url": "https://treasury.go.ke",
                "status_code": response.status_code,
                "accessible": response.status_code == 200,
                "response_size": len(response.content),
                "timestamp": datetime.now().isoformat(),
            }

            if response.status_code == 200:
                # Try to extract some basic info
                soup = BeautifulSoup(response.content, "html.parser")
                title = soup.find("title")
                result["page_title"] = title.text.strip() if title else "No title found"

                # Look for document links
                links = soup.find_all("a", href=True)
                pdf_links = [
                    link["href"] for link in links if "pdf" in link["href"].lower()
                ]
                result["pdf_documents_found"] = len(pdf_links)
                result["sample_pdfs"] = pdf_links[:5]  # First 5 PDFs

                logger.info(f"✅ Successfully connected to {result['source']}")
                logger.info(f"   - Page title: {result['page_title']}")
                logger.info(
                    f"   - PDF documents found: {result['pdf_documents_found']}"
                )
            else:
                logger.warning(f"❌ Connection failed: HTTP {response.status_code}")

            self.results["sources_checked"].append(result)
            return result

        except Exception as e:
            error_result = {
                "source": "Kenya National Treasury",
                "error": str(e),
                "accessible": False,
                "timestamp": datetime.now().isoformat(),
            }
            logger.error(f"❌ Connection failed: {str(e)}")
            self.results["sources_checked"].append(error_result)
            self.results["errors"].append(str(e))
            return error_result

    def test_auditor_general_connection(self):
        """Test connection to Office of Auditor General website."""
        try:
            logger.info("Testing Office of Auditor General connection...")
            response = requests.get("https://oagkenya.go.ke", timeout=10)

            result = {
                "source": "Office of Auditor General",
                "url": "https://oagkenya.go.ke",
                "status_code": response.status_code,
                "accessible": response.status_code == 200,
                "timestamp": datetime.now().isoformat(),
            }

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")
                title = soup.find("title")
                result["page_title"] = title.text.strip() if title else "No title found"

                # Look for audit reports
                links = soup.find_all("a", href=True)
                audit_links = [
                    link["href"]
                    for link in links
                    if any(
                        word in link.get_text().lower()
                        for word in ["audit", "report", "finding"]
                    )
                ]
                result["audit_documents_found"] = len(audit_links)

                logger.info(f"✅ Successfully connected to {result['source']}")
                logger.info(
                    f"   - Audit documents found: {result['audit_documents_found']}"
                )
            else:
                logger.warning(f"❌ Connection failed: HTTP {response.status_code}")

            self.results["sources_checked"].append(result)
            return result

        except Exception as e:
            error_result = {
                "source": "Office of Auditor General",
                "error": str(e),
                "accessible": False,
                "timestamp": datetime.now().isoformat(),
            }
            logger.error(f"❌ Connection failed: {str(e)}")
            self.results["sources_checked"].append(error_result)
            return error_result

    def run_full_pipeline(self):
        """Check source access and discover links; no financial extraction exists."""
        self.results = {
            "documents_fetched": 0,
            "entities_found": [],
            "sources_checked": [],
            "raw_data": [],
            "errors": [],
        }
        sources = [
            self.test_treasury_connection(),
            self.test_auditor_general_connection(),
        ]
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
    parser.add_argument("--output", default="etl_test_results.json")
    args = parser.parse_args()
    etl = SimpleKenyaETL()
    results = etl.run_full_pipeline()
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Source observations saved to: {args.output}; financial data not extracted")
    return results


if __name__ == "__main__":
    sys.exit(1 if main()["errors_encountered"] else 0)
