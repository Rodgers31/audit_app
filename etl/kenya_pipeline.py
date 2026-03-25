"""
Enhanced data ingestion pipeline for MVP
Focuses on actual Kenyan government data sources
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import warnings
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

try:
    from .cob_headless import fetch_cob_download, headless_allowed  # type: ignore
except Exception:
    try:
        from etl.cob_headless import fetch_cob_download  # type: ignore
        from etl.cob_headless import headless_allowed
    except Exception:  # fallback stubs

        def headless_allowed():  # type: ignore
            return False

        async def fetch_cob_download(url: str):  # type: ignore
            return None


from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import boto3  # type: ignore
    from botocore.exceptions import ClientError  # type: ignore
except Exception:  # boto3 optional
    boto3 = None  # type: ignore
    ClientError = Exception  # type: ignore

# Import pipeline dependencies; handle optional DB loader gracefully
try:
    from .audit_parser import AuditParser
except Exception:
    from etl.audit_parser import AuditParser  # type: ignore

# Database loader is optional; if it fails to import (e.g., DB models error), use Noop later
try:
    from .database_loader import DatabaseLoader  # type: ignore
except Exception:
    DatabaseLoader = None  # type: ignore

try:
    from .extractor import DocumentExtractor
except Exception:
    from etl.extractor import DocumentExtractor  # type: ignore

try:
    from .normalizer import DataNormalizer
except Exception:
    from etl.normalizer import DataNormalizer  # type: ignore

try:
    from .source_registry import registry
except Exception:
    from etl.source_registry import registry  # type: ignore

# Import KNBS extractor and parser for economic data
try:
    from extractors.government.knbs_extractor import KNBSExtractor
except Exception:
    try:
        from ..extractors.government.knbs_extractor import KNBSExtractor  # type: ignore
    except Exception:
        KNBSExtractor = None  # type: ignore

try:
    from .knbs_parser import KNBSParser
except Exception:
    try:
        from etl.knbs_parser import KNBSParser  # type: ignore
    except Exception:
        KNBSParser = None  # type: ignore

# Import smart scheduler for calendar-aware ETL scheduling
try:
    from .smart_scheduler import SmartScheduler
except Exception:
    try:
        from etl.smart_scheduler import SmartScheduler  # type: ignore
    except Exception:
        # Provide stub scheduler if import fails
        logger.warning("SmartScheduler not available, using always-run fallback")

        class SmartScheduler:  # type: ignore
            def should_run(self, source):
                return (True, "Fallback: always run")

            def generate_schedule_report(self):
                return {}


# Import validators for data quality checks
try:
    import sys
    from pathlib import Path as _Path

    # Add backend to path for validator imports
    _backend_path = _Path(__file__).parent.parent / "backend"
    if str(_backend_path) not in sys.path:
        sys.path.insert(0, str(_backend_path))
    from validators.data_validator import ConfidenceFilter, DataValidator
except Exception as e:
    logger.warning(f"Could not import validators: {e}")

    # Provide stub validators if imports fail
    class DataValidator:  # type: ignore
        def validate_budget_data(self, data):
            from dataclasses import dataclass

            @dataclass
            class ValidationResult:
                is_valid: bool = True
                confidence: float = 1.0
                errors: list = None
                warnings: list = None
                metadata: dict = None

                def __post_init__(self):
                    self.errors = self.errors or []
                    self.warnings = self.warnings or []
                    self.metadata = self.metadata or {}

            return ValidationResult()

        def validate_audit_data(self, data):
            from dataclasses import dataclass

            @dataclass
            class ValidationResult:
                is_valid: bool = True
                confidence: float = 1.0
                errors: list = None
                warnings: list = None
                metadata: dict = None

                def __post_init__(self):
                    self.errors = self.errors or []
                    self.warnings = self.warnings or []
                    self.metadata = self.metadata or {}

            return ValidationResult()

    class ConfidenceFilter:  # type: ignore
        def __init__(self, min_confidence=0.6):
            self.min_confidence = min_confidence

        def should_accept(self, extraction):
            return True


class NoopDatabaseLoader:
    async def load_audit_findings_document(self, document_record, findings):
        return 1

    async def load_document(self, document_record, normalized_data):
        return 1


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KenyaDataPipeline:
    """
    MVP implementation for Kenya-specific data sources:
    - National Treasury (budget documents)
    - Office of the Controller of Budget (county implementation)
    - Office of the Auditor General (audit reports)
    """

    def __init__(self, storage_path: str = None):
        # Default to a downloads folder alongside this file so backend can read it
        default_storage = Path(__file__).parent / "downloads"
        self.storage_path = Path(storage_path) if storage_path else default_storage
        self.storage_path.mkdir(exist_ok=True)
        self.manifest_path = self.storage_path / "processed_manifest.json"
        self.processed_manifest = self._load_manifest()
        self.extractor = DocumentExtractor()
        self.normalizer = DataNormalizer()
        self.audit_parser = AuditParser()

        # Initialize data validators for quality assurance (Week 1 Task 2)
        self.data_validator = DataValidator()
        self.confidence_filter = ConfidenceFilter(min_confidence=0.7)
        logger.info("Data validators initialized with min_confidence=0.7")

        # Initialize smart scheduler for calendar-aware ETL (Week 3 Task 1)
        self.scheduler = SmartScheduler()
        logger.info("Smart scheduler initialized for calendar-aware ETL runs")

        # Database loader is optional; fall back to a no-op when DB models aren't available
        try:
            self.db_loader = (
                DatabaseLoader() if DatabaseLoader else NoopDatabaseLoader()
            )
        except Exception:
            logger.warning(
                "DatabaseLoader unavailable; using NoopDatabaseLoader for this run"
            )
            self.db_loader = NoopDatabaseLoader()

        # HTTP session with a reasonable User-Agent; we'll allow per-host SSL fallback
        self.http = requests.Session()
        self.http.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            }
        )
        retry_strategy = Retry(
            total=5,
            connect=5,
            read=5,
            status=5,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods={"GET", "HEAD"},
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy, pool_maxsize=16, pool_block=True
        )
        self.http.mount("https://", adapter)
        self.http.mount("http://", adapter)
        # Silence SSL warnings only for our explicit insecure fallbacks
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)

        # Optional object storage (S3-compatible)
        self.s3 = None
        self.s3_bucket = os.getenv("AWS_BUCKET_NAME")
        self.s3_region = os.getenv("AWS_REGION", "us-east-1")
        if boto3 and self.s3_bucket and os.getenv("AWS_ACCESS_KEY_ID"):
            try:
                self.s3 = boto3.client(
                    "s3",
                    region_name=self.s3_region,
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                )
            except Exception:
                self.s3 = None

        # Known Kenya government URLs (as of MVP)
        self.kenya_sources = {
            "treasury": {
                "name": "National Treasury Kenya",
                # Treasury migrated from WordPress to Drupal (~2024).
                # Primary site is now newsite.treasury.go.ke; old domain still resolves some paths.
                "base_url": "https://newsite.treasury.go.ke",
                "legacy_base_url": "https://www.treasury.go.ke",
                "budget_url": "https://newsite.treasury.go.ke/budget",
                "documents": [
                    "budget-statement",
                    "programme-based-budget",
                    "county-allocation",
                    "debt-management",
                    "quarterly-economic-and-budgetary-review-report",
                    "budget-books",
                    "budget-policy-statement",
                ],
            },
            "cob": {
                "name": "Controller of Budget",
                "base_url": "https://cob.go.ke",
                "reports_url": "https://cob.go.ke/publications/",
                "county_reports_url": "https://cob.go.ke/publications/county-government-budget-implementation-review-reports/",
                "national_reports_url": "https://cob.go.ke/publications/national-government-budget-implementation-review-reports/",
                "documents": [
                    "county-budget-implementation",
                    "quarterly-reports",
                    "annual-reports",
                ],
            },
            "oag": {
                "name": "Office of the Auditor General",
                # Use the www host to match the site's TLS certificate and avoid SSL hostname mismatch
                "base_url": "https://www.oagkenya.go.ke",
                # Point to a canonical audits section; discovery will include county/specialized
                "reports_url": "https://www.oagkenya.go.ke/national-government-audit-reports/",
                "documents": [
                    "county-audit-reports",
                    "national-audit-reports",
                    "special-audits",
                ],
            },
            "knbs": {
                "name": "Kenya National Bureau of Statistics",
                "base_url": "https://www.knbs.or.ke",
                "reports_url": "https://www.knbs.or.ke/publications/",
                "documents": [
                    "economic-survey",
                    "statistical-abstract",
                    "county-statistical-abstract",
                    "gdp-reports",
                    "cpi-inflation",
                    "facts-and-figures",
                ],
            },
        }

        # Initialize KNBS extractor if available
        self.knbs_extractor = None
        if KNBSExtractor:
            try:
                self.knbs_extractor = KNBSExtractor()
                logger.info("[OK] KNBS extractor initialized")
            except Exception as e:
                logger.warning(f"[WARN] Could not initialize KNBS extractor: {e}")

        # Initialize KNBS parser if available
        self.knbs_parser = None
        if KNBSParser:
            try:
                self.knbs_parser = KNBSParser()
                logger.info("[OK] KNBS parser initialized")
            except Exception as e:
                logger.warning(f"[WARN] Could not initialize KNBS parser: {e}")

        # Resolve KNBS certificate bundle for pinned TLS verification
        bundle_path = (
            Path(__file__).resolve().parent.parent
            / "config"
            / "certs"
            / "knbs_trust_store.pem"
        )
        self.knbs_ca_bundle = bundle_path if bundle_path.exists() else None
        if self.knbs_ca_bundle:
            logger.info(
                "[CERT] KNBS downloads will use pinned certificate bundle at %s",
                self.knbs_ca_bundle,
            )

    def _load_manifest(self) -> Dict[str, Any]:
        try:
            if self.manifest_path.exists():
                import json as _json

                return _json.loads(self.manifest_path.read_text())
        except Exception:
            pass
        return {"by_md5": {}}

    def _save_manifest(self) -> None:
        try:
            import json as _json

            self.manifest_path.write_text(
                _json.dumps(self.processed_manifest, indent=2)
            )
        except Exception:
            pass

    def _ssl_verify_for(self, source_key: str, insecure: bool = False):
        """Resolve verify parameter for requests based on source and security policy."""
        if insecure:
            return False
        if source_key == "knbs" and self.knbs_ca_bundle:
            return str(self.knbs_ca_bundle)
        return True

    def _fetch_html(self, url: str, source_key: str) -> Optional[BeautifulSoup]:
        """Fetch HTML with appropriate SSL policy; return soup or None."""
        verify = self._ssl_verify_for(source_key, insecure=False)
        try:
            resp = self.http.get(url, timeout=60, verify=verify)
            resp.raise_for_status()
            return BeautifulSoup(resp.content, "html.parser")
        except requests.exceptions.SSLError as ssl_err:
            if source_key == "knbs" and self.knbs_ca_bundle:
                logger.error(
                    "KNBS SSL validation failed with pinned bundle %s: %s",
                    self.knbs_ca_bundle,
                    ssl_err,
                )
                return None
        except Exception as e:
            # SSL fallback for tricky hosts
            if source_key in {"oag", "cob"}:
                try:
                    resp = self.http.get(url, timeout=60, verify=False)
                    resp.raise_for_status()
                    return BeautifulSoup(resp.content, "html.parser")
                except Exception as e2:
                    logger.error(f"{source_key} fetch failed (insecure): {e2}")
                    return None
            logger.error(f"Fetch failed: {e}")
            return None
        return None

    def _resolve_pdfs_on_page(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Return list of absolute file URLs (pdf/xls/xlsx/csv/doc/docx/zip).
        Only include anchors that clearly reference files or recognized download endpoints/plugins.
        """
        pdfs: List[str] = []
        from urllib.parse import urlparse as _urlparse

        base_host = ""
        try:
            base_host = _urlparse(base_url).netloc.replace("www.", "")
        except Exception:
            base_host = ""
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = (a.get_text(strip=True) or "").lower()
            # Guard against broken placeholders like bare http(s) or root/home/hash/js links
            hlow = href.lower()
            if hlow in {"http://", "https://", "/", "#", ""}:
                continue
            if hlow.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            has_plugin_flag = (
                ("mdocs-file=" in hlow)
                or ("wpdmpro=" in hlow)
                or (a.has_attr("data-file") and bool(a["data-file"]))
            )
            is_file_ext = bool(
                re.search(r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", href, re.I)
            )
            is_download_endpoint = "/download/" in hlow

            # Only accept if it's a clear file ref or recognized download endpoint/plugin
            if not (is_file_ext or is_download_endpoint or has_plugin_flag):
                continue

            resolved = self._resolve_url(href, base_url)
            # Some plugins store direct file url in data-file attribute
            if a.has_attr("data-file") and a["data-file"]:
                try:
                    df = str(a["data-file"]).strip()
                    if df:
                        resolved = self._resolve_url(df, base_url)
                except Exception:
                    pass
            # Enforce same host
            try:
                if (
                    base_host
                    and _urlparse(resolved).netloc.replace("www.", "") != base_host
                ):
                    continue
            except Exception:
                pass
            # Skip obvious non-report assets and theme/plugin files
            path_lower = (urlparse(resolved).path or "").lower()
            if any(
                bad in path_lower
                for bad in [
                    "/wp-includes/",
                    "/wp-content/themes/",
                    "/wp-content/plugins/",
                    "/assets/",
                    "/images/",
                    "/img/",
                ]
            ):
                continue
            # Deprioritize/skip files that look like logos or stationery
            if any(
                x in path_lower for x in ["logo", "letterhead", "branding", "favicon"]
            ):
                continue
            pdfs.append(resolved)
        # Deduplicate
        seen = set()
        out = []
        for u in pdfs:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def _discover_oag(self) -> List[Dict[str, Any]]:
        """Discover OAG Financial Audit reports across nested National/County sections with breadcrumbs and level metadata."""
        source = self.kenya_sources["oag"]
        base = source["base_url"]
        host = urlparse(base).netloc.replace("www.", "")

        section_levels = [
            (
                "https://www.oagkenya.go.ke/national-government-audit-reports/",
                "national",
            ),
            ("https://www.oagkenya.go.ke/county-governments-reports/", "county"),
            ("https://www.oagkenya.go.ke/specialized-audit-reports/", "specialized"),
            ("https://www.oagkenya.go.ke/special-audit-report/", "special"),
            # Performance audits (standalone page)
            ("https://www.oagkenya.go.ke/performance-audit-report/", "performance"),
            # Annual corporate reports
            ("https://www.oagkenya.go.ke/annual-corporate-report/", "corporate"),
        ]

        q = deque(
            [
                {"url": u, "level": lvl, "breadcrumbs": [lvl]}
                for (u, lvl) in section_levels
            ]
        )
        for u, lvl in section_levels:
            for i in range(2, 8):
                q.append(
                    {
                        "url": u.rstrip("/") + f"/page/{i}/",
                        "level": lvl,
                        "breadcrumbs": [lvl],
                    }
                )

        # Focused category seeds (skip known 404s: national-government-funds, ng-cdf, universities, tvets, etc.)
        for u in [
            # National
            "https://www.oagkenya.go.ke/ministries-departments-and-agencies/",
            "https://www.oagkenya.go.ke/state-corporations/",
            "https://www.oagkenya.go.ke/political-parties/",
            "https://www.oagkenya.go.ke/implementation-of-audit-recommendations/",
        ]:
            q.append({"url": u, "level": "national", "breadcrumbs": ["national"]})
        for u in [
            # County — expanded subcategories discovered Feb 2026
            "https://www.oagkenya.go.ke/county-executives-assemblies-reports/",
            "https://www.oagkenya.go.ke/county-funds/",
            "https://www.oagkenya.go.ke/county-revenue-funds/",
            "https://www.oagkenya.go.ke/county-receivers-of-revenue-audit-reports/",
            "https://www.oagkenya.go.ke/county-municipalities-audit-reports/",
            "https://www.oagkenya.go.ke/level-4-5-hospitals-audit-reports/",
            "https://www.oagkenya.go.ke/county-water-companies-audit-reports/",
            "https://www.oagkenya.go.ke/county-revenue-funds-audit-reports/",
        ]:
            q.append({"url": u, "level": "county", "breadcrumbs": ["county"]})

        # FY-specific landing pages under /county-governments-reports/ (OAG now
        # structures document listings into FY pages within each subcategory)
        for fy_start in range(2018, 2026):
            fy_end = fy_start + 1
            for sub_path in [
                f"/{fy_start}-{fy_end}-county-government-audit-reports/",
                f"/{fy_start}-{fy_end}-county-executives-assemblies-audit-reports/",
                f"/{fy_start}-{fy_end}-ministries-departments-and-agencies-audit-reports/",
            ]:
                q.append(
                    {
                        "url": f"https://www.oagkenya.go.ke{sub_path}",
                        "level": "county",
                        "breadcrumbs": ["county", f"FY{fy_start}/{fy_end}"],
                    }
                )

        seen_pages: set[str] = set()
        collected: List[Dict[str, Any]] = []
        max_pages = 700
        pages = 0

        def same_host(u: str) -> bool:
            try:
                p = urlparse(u)
            except Exception:
                return False
            return (
                p.scheme in ("http", "https") and p.netloc.replace("www.", "") == host
            )

        def is_http_link(href: str) -> bool:
            if not href:
                return False
            h = href.strip().lower()
            if h.startswith(("#", "mailto:", "tel:", "javascript:")):
                return False
            return True

        generic_nav = {
            "home",
            "about us",
            "contact us",
            "media center",
            "publications",
            "tenders",
        }
        known_paths = [
            "/national-government-audit-reports",
            "/county-governments-reports",
            "/specialized-audit-reports",
            "/special-audit-report",
            "/ministries-departments-and-agencies",
            "/state-corporations",
            "/political-parties",
            "/implementation-of-audit-recommendations",
            "/county-executives-assemblies-reports",
            "/county-funds",
            "/county-revenue-funds",
        ]
        card_terms = {
            "ministries",
            "departments",
            "agencies",
            "national government funds",
            "ng-cdf",
            "state corporations",
            "sagas",
            "universities",
            "universities enterprises",
            "tvets",
            "polytechnics",
            "political parties",
            "schools",
            "implementation of audit recommendations",
            "county executives",
            "assemblies",
            "county receivers of revenue",
            "municipalities",
            "boards",
            "county funds",
            "hospitals",
            "water companies",
            "county revenue funds",
        }

        def should_enqueue(resolved: str, text: str) -> bool:
            path = (urlparse(resolved).path or "/").lower()
            t = (text or "").lower()
            if any(k in path for k in ["/page/", "/audit", "/reports/", "/category/"]):
                return True
            if re.search(r"\b(fy\s*20\d{2}|20\d{2}\s*[/–-]\s*20\d{2})\b", t):
                return True
            if re.search(r"/(fy\s*20\d{2}|20\d{2})([/–-]|$)", path) or re.search(
                r"20\d{2}\s*[/–-]\s*20\d{2}", path
            ):
                return True
            if any(
                y in path
                for y in [
                    "/2016",
                    "/2017",
                    "/2018",
                    "/2019",
                    "/2020",
                    "/2021",
                    "/2022",
                    "/2023",
                    "/2024",
                    "/2025",
                ]
            ):
                return True
            if any(
                k in t for k in ["read more", "download", "report", "audit", "view"]
            ):
                return True
            if any(k in t for k in card_terms):
                return True
            if any(p in path for p in known_paths):
                return True
            return False

        def extract_year(text: str) -> Optional[str]:
            tl = (text or "").lower()
            m = re.search(r"fy\s*([0-9]{4}\s*[-/–]\s*[0-9]{4})", tl)
            if m:
                return m.group(1).replace(" ", "")
            m2 = re.search(r"(20[0-9]{2})", tl)
            return m2.group(1) if m2 else None

        def best_title_for_link(a_tag: Any, fallback_url: str) -> str:
            text = (a_tag.get_text(strip=True) or "").strip()
            if text and text.lower() != "download" and len(text) > 2:
                return text
            containers = list(a_tag.parents)
            for c in containers[:6]:
                head = None
                if hasattr(c, "find"):
                    head = (
                        c.find(
                            class_=re.compile(
                                r"(entry-title|post__title|uael-post__title|elementor-post__title)"
                            )
                        )
                        or c.find(["h1", "h2", "h3", "h4"])
                        or None
                    )
                if head:
                    t = (head.get_text(strip=True) or "").strip()
                    if t:
                        return t
            return (
                Path(urlparse(fallback_url).path).name.replace("-", " ") or "Download"
            )

        while q and pages < max_pages:
            item = q.popleft()
            url = item["url"]
            if url in seen_pages:
                continue
            seen_pages.add(url)
            soup = self._fetch_html(url, "oag")
            if not soup:
                continue
            pages += 1

            # Collect PDFs on page
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not is_http_link(href):
                    continue
                if not re.search(r"\.pdf($|\?)", href, re.I):
                    continue
                resolved = self._resolve_url(href, base)
                if not same_host(resolved):
                    continue
                # Skip obviously broken or non-audit-like files by path heuristics
                path_lower = (urlparse(resolved).path or "").lower()
                if any(x in path_lower for x in ["/wp-json/", "/feed/", "/tag/"]):
                    continue
                title = best_title_for_link(a, resolved)
                collected.append(
                    {
                        "url": resolved,
                        "title": title,
                        "source": source["name"],
                        "source_key": "oag",
                        "doc_type": "audit",
                        "discovered_date": datetime.now().isoformat(),
                        "meta": {
                            "level": item.get("level"),
                            "breadcrumbs": item.get("breadcrumbs", []),
                            "year": extract_year(title),
                        },
                        "referrer": url,
                    }
                )

            # Enqueue deeper pages (cards, categories, read-more)
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not is_http_link(href):
                    continue
                text = a.get_text(strip=True) or ""
                resolved = self._resolve_url(href, base)
                if not same_host(resolved):
                    continue
                if resolved in seen_pages:
                    continue
                if text.lower() in generic_nav:
                    continue
                # Avoid enqueuing direct file links (pdfs) as pages
                if re.search(r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", resolved, re.I):
                    continue
                if should_enqueue(resolved, text):
                    crumbs = item.get("breadcrumbs", [])
                    t = text.strip()
                    if t and len(t) > 2 and t.lower() not in generic_nav:
                        if not crumbs or crumbs[-1].lower() != t.lower():
                            new_crumbs = (crumbs + [t])[-6:]
                        else:
                            new_crumbs = crumbs
                    else:
                        seg = [
                            s for s in (urlparse(resolved).path or "").split("/") if s
                        ]
                        fallback = seg[-1].replace("-", " ") if seg else ""
                        new_crumbs = (crumbs + ([fallback] if fallback else []))[-6:]
                    q.append(
                        {
                            "url": resolved,
                            "level": item.get("level"),
                            "breadcrumbs": new_crumbs,
                        }
                    )

        # Augment with WordPress REST API — OAG document pages now use JS-rendered
        # DataTables so PDF links are invisible to HTML crawling.  The WP REST API
        # /wp-json/wp/v2/media still returns the actual PDF media objects.
        def _collect_from_oag_wp_rest() -> None:
            api_base = f"{base}/wp-json/wp/v2/media"
            per_page = 100
            search_terms = ["audit", "report", "county", "national", "summary"]
            seen_urls: set[str] = {d["url"] for d in collected}
            for term in search_terms:
                page = 1
                while page <= 20:
                    try:
                        resp = self.http.get(
                            api_base,
                            params={
                                "per_page": per_page,
                                "page": page,
                                "mime_type": "application/pdf",
                                "search": term,
                            },
                            timeout=30,
                        )
                        if resp.status_code == 400:
                            # Fallback: some WP versions reject mime_type filter
                            resp = self.http.get(
                                api_base,
                                params={
                                    "per_page": per_page,
                                    "page": page,
                                    "media_type": "file",
                                    "search": term,
                                },
                                timeout=30,
                            )
                        resp.raise_for_status()
                        arr = resp.json()
                    except Exception:
                        break
                    if not isinstance(arr, list) or not arr:
                        break
                    for it in arr:
                        try:
                            src = it.get("source_url") or ""
                            if not src or src in seen_urls:
                                continue
                            if not re.search(r"\.pdf($|\?)", src, re.I):
                                continue
                            title = (
                                (it.get("title") or {}).get("rendered")
                                if isinstance(it.get("title"), dict)
                                else it.get("title")
                            ) or Path(urlparse(src).path).name
                            seen_urls.add(src)
                            collected.append(
                                {
                                    "url": src,
                                    "title": title,
                                    "source": source["name"],
                                    "source_key": "oag",
                                    "doc_type": "audit",
                                    "discovered_date": datetime.now().isoformat(),
                                    "meta": {
                                        "breadcrumbs": ["wp-json", term],
                                        "year": extract_year(title),
                                    },
                                }
                            )
                        except Exception:
                            continue
                    page += 1

        try:
            _collect_from_oag_wp_rest()
        except Exception:
            pass  # Non-fatal: HTML crawl results are still usable

        unique: Dict[str, Dict[str, Any]] = {}
        for d in collected:
            unique.setdefault(d["url"], d)
        return list(unique.values())

    def _discover_cob(self) -> List[Dict[str, Any]]:
        """Discover COB reports/templates from the exact sections; robust to slow/SSL issues."""
        source = self.kenya_sources["cob"]
        base = source["base_url"]
        host = urlparse(base).netloc.replace("www.", "")

        # Focus on exact National and Consolidated County BIRR pages with deep lists
        sections = [
            # County consolidated BIRR (deep history, back to ~2014)
            "https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/",
            # National government BIRR
            "https://cob.go.ke/publications/national-government-budget-implementation-review-reports/",
            # Publications page (main reports index)
            "https://cob.go.ke/publications/",
            # Generic reports index as a safety net
            urljoin(base + "/", "/reports/"),
            source.get("reports_url") or urljoin(base + "/", "/publications/"),
        ]

        q = deque([{"url": u, "breadcrumbs": ["reports"]} for u in sections])
        # Paginate both consolidated county and national government sections more deeply
        for idx in [0, 1]:
            for i in range(2, 21):
                q.append(
                    {
                        "url": sections[idx].rstrip("/") + f"/page/{i}/",
                        "breadcrumbs": ["reports", f"page {i}"],
                    }
                )
        # Paginate the generic /reports/ index as well
        for i in range(2, 21):
            q.append(
                {
                    "url": sections[2].rstrip("/") + f"/page/{i}/",
                    "breadcrumbs": ["reports", f"page {i}"],
                }
            )

        seen: set[str] = set()
        collected: List[Dict[str, Any]] = []
        max_pages = 800
        pages = 0

        def same_host(u: str) -> bool:
            try:
                p = urlparse(u)
            except Exception:
                return False
            return (
                p.scheme in ("http", "https") and p.netloc.replace("www.", "") == host
            )

        def is_http_link(h: str) -> bool:
            if not h:
                return False
            h = h.strip().lower()
            if h.startswith(("#", "mailto:", "tel:", "javascript:")):
                return False
            return True

        def looks_like_download(u: str) -> bool:
            ul = (u or "").lower()
            return bool(
                re.search(r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", ul, re.I)
                or "/download/" in ul
                or "mdocs-file=" in ul  # WP Memorable Docs plugin style
                or "wpdmpro=" in ul  # WP Download Manager
                or "/wp-content/uploads/" in ul
            )

        def looks_like_list(resolved: str, text: str) -> bool:
            path = (urlparse(resolved).path or "").lower()
            t = (text or "").lower()
            if any(
                k in path
                for k in [
                    "/reports/",
                    "/category/",
                    "/news/",
                    "/updates/",
                    "/tag/",
                    "/page/",
                ]
            ):
                return True
            if any(
                k in t
                for k in [
                    "report",
                    "budget",
                    "implementation",
                    "birr",
                    "read more",
                    "view",
                ]
            ):
                return True
            # enqueue year-like slugs
            if re.search(r"20\d{2}", path):
                return True
            return False

        while q and pages < max_pages:
            item = q.popleft()
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            soup = self._fetch_html(url, "cob")
            if not soup:
                continue
            pages += 1

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not is_http_link(href):
                    continue
                resolved = self._resolve_url(href, base)
                if not same_host(resolved):
                    continue
                text = (a.get_text(strip=True) or "").strip()
                # Ignore obvious image/media files
                if re.search(
                    r"\.(png|jpe?g|gif|mp4|webm|avi|svg)($|\?)", resolved, re.I
                ):
                    continue
                if looks_like_download(resolved):
                    collected.append(
                        {
                            "url": resolved,
                            "title": text or Path(urlparse(resolved).path).name,
                            "source": source["name"],
                            "source_key": "cob",
                            "doc_type": "report",
                            "discovered_date": datetime.now().isoformat(),
                            "meta": {"breadcrumbs": item.get("breadcrumbs", [])},
                            "referrer": url,
                        }
                    )
                elif looks_like_list(resolved, text):
                    if resolved not in seen:
                        q.append(
                            {
                                "url": resolved,
                                "breadcrumbs": item.get("breadcrumbs", [])
                                + [text or Path(urlparse(resolved).path).name],
                            }
                        )

        # Attempt to augment via sitemap(s) recursively
        visited_sm: set[str] = set()

        def _collect_from_sitemap(sm_url: str, depth: int = 0) -> None:
            if depth > 3 or not sm_url or sm_url in visited_sm:
                return
            visited_sm.add(sm_url)
            try:
                resp = self.http.get(sm_url, timeout=30)
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
            except Exception:
                return

            tag = (root.tag or "").lower()
            if tag.endswith("sitemapindex"):
                for loc in root.findall(".//{*}sitemap/{*}loc"):
                    nxt = (loc.text or "").strip()
                    if nxt:
                        _collect_from_sitemap(nxt, depth + 1)
                return

            for loc in root.findall(".//{*}url/{*}loc"):
                u = (loc.text or "").strip()
                if not u:
                    continue
                try:
                    pu = urlparse(u)
                except Exception:
                    continue
                if pu.netloc.replace("www.", "") != host:
                    continue
                # If the sitemap links directly to files, take them.
                if (
                    re.search(r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", u, re.I)
                    or "/download/" in u
                ):
                    collected.append(
                        {
                            "url": u,
                            "title": Path(pu.path).name,
                            "source": source["name"],
                            "source_key": "cob",
                            "doc_type": "report",
                            "discovered_date": datetime.now().isoformat(),
                            "meta": {"breadcrumbs": ["sitemap"]},
                            "referrer": sm_url,
                        }
                    )
                    return
                # Otherwise, many WP sitemaps list attachment pages. Fetch page and extract file links
                soup = self._fetch_html(u, "cob")
                if not soup:
                    continue
                for f in self._resolve_pdfs_on_page(soup, base):
                    collected.append(
                        {
                            "url": f,
                            "title": Path(urlparse(f).path).name,
                            "source": source["name"],
                            "source_key": "cob",
                            "doc_type": "report",
                            "discovered_date": datetime.now().isoformat(),
                            "meta": {"breadcrumbs": ["sitemap", u]},
                            "referrer": u,
                        }
                    )

        for sm in [
            urljoin(base + "/", "/sitemap_index.xml"),
            urljoin(base + "/", "/sitemap.xml"),
            urljoin(base + "/", "/wp-sitemap.xml"),  # WP 5.5+ default
        ]:
            _collect_from_sitemap(sm)

        # Attempt to augment via WordPress REST API for media (PDFs/XLS etc.)
        def _collect_from_wp_rest() -> None:
            endpoints = [
                # Core media endpoint
                urljoin(base + "/", "/wp-json/wp/v2/media"),
            ]
            exts = [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel",
                "text/csv",
                "application/zip",
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ]
            per_page = 100
            for ep in endpoints:
                for mime in exts:
                    page = 1
                    while page <= 20:
                        try:
                            resp = self.http.get(
                                ep,
                                params={
                                    "per_page": per_page,
                                    "page": page,
                                    "mime_type": mime,
                                },
                                timeout=30,
                            )
                            if (
                                resp.status_code == 400
                                and "mime_type" in resp.text.lower()
                            ):
                                # Some WP versions use 'media_type=file' and filter via search; try without mime filter
                                alt = self.http.get(
                                    ep,
                                    params={
                                        "per_page": per_page,
                                        "page": page,
                                        "media_type": "file",
                                    },
                                    timeout=30,
                                )
                                resp = alt
                            resp.raise_for_status()
                            arr = resp.json()
                        except Exception:
                            break
                        if not isinstance(arr, list) or not arr:
                            break
                        for it in arr:
                            try:
                                src = it.get("source_url") or ""
                                if not src:
                                    continue
                                pu = urlparse(src)
                                if pu.netloc.replace("www.", "") != host:
                                    continue
                                if not re.search(
                                    r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", src, re.I
                                ):
                                    continue
                                title = (
                                    (it.get("title") or {}).get("rendered")
                                    if isinstance(it.get("title"), dict)
                                    else it.get("title")
                                ) or Path(pu.path).name
                                collected.append(
                                    {
                                        "url": src,
                                        "title": title,
                                        "source": source["name"],
                                        "source_key": "cob",
                                        "doc_type": "report",
                                        "discovered_date": datetime.now().isoformat(),
                                        "meta": {"breadcrumbs": ["wp-json"]},
                                    }
                                )
                            except Exception:
                                continue
                        page += 1

        _collect_from_wp_rest()

        # Dedupe
        uniq: Dict[str, Dict[str, Any]] = {}
        for d in collected:
            uniq.setdefault(d["url"], d)
        return list(uniq.values())

    def _discover_knbs(self) -> List[Dict[str, Any]]:
        """Discover KNBS economic publications using the dedicated extractor."""
        if not self.knbs_extractor:
            logger.warning("⚠️ KNBS extractor not available, skipping KNBS discovery")
            return []

        try:
            logger.info("🔍 Discovering KNBS publications...")

            # Use the KNBSExtractor to discover documents
            documents = self.knbs_extractor.discover_documents()

            logger.info(f"✅ Discovered {len(documents)} KNBS documents")

            # Convert to pipeline format
            pipeline_docs = []
            for doc in documents:
                # Extract document type from various fields
                doc_type = (
                    doc.get("type")
                    or doc.get("publication_type")
                    or doc.get("release_type")
                    or "other"
                )

                pipeline_docs.append(
                    {
                        "url": doc["url"],
                        "title": doc["title"],
                        "source": "Kenya National Bureau of Statistics",
                        "source_key": "knbs",
                        "doc_type": doc_type,
                        "year": doc.get("year"),
                        "quarter": doc.get("quarter"),
                        "county": doc.get("county"),
                        "discovered_date": datetime.now().isoformat(),
                        "metadata": {
                            "publication_type": doc.get("type", "unknown"),
                            "priority": doc.get("priority", "medium"),
                            "report_page": doc.get("report_page"),
                            "period": doc.get("period"),
                        },
                    }
                )

            # Sort by priority and year (most recent first)
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            pipeline_docs.sort(
                key=lambda d: (
                    priority_order.get(d["metadata"].get("priority", "medium"), 2),
                    -(d.get("year") or 0),
                )
            )

            return pipeline_docs

        except Exception as e:
            logger.error(f"❌ Error discovering KNBS documents: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return []

    def _discover_treasury(self) -> List[Dict[str, Any]]:
        source = self.kenya_sources["treasury"]
        base = source["base_url"]

        # Treasury migrated from WordPress to Drupal in 2024/2025.
        # New domain: newsite.treasury.go.ke  (Drupal, PDF path pattern: /sites/default/files/...)
        # Old domain www.treasury.go.ke still redirects / hosts some legacy wp-content PDFs.
        new_base = "https://newsite.treasury.go.ke"
        # Primary document pages on the new Drupal site (verified Feb 2026):
        seeds = [
            f"{new_base}/quarterly-economic-and-budgetary-review-report",  # 32 QEBR PDFs
            f"{new_base}/budget-books",  # 55 budget book PDFs
            f"{new_base}/budget-policy-statement",  # 15 BPS PDFs
            f"{new_base}/budget-review-and-outlook-paper",
            f"{new_base}/general-reports",
            f"{new_base}/sector-budget-proposal-reports",
            f"{new_base}/directorate-public-debt-management",
            f"{new_base}/pdmo-reports-and-documents",
            f"{new_base}/debt-policy-strategy-and-risk-management",
            f"{new_base}/budget",
        ]
        # Legacy WordPress URLs as fallback (some old wp-content/ PDFs still resolve)
        legacy_seeds = [
            "https://www.treasury.go.ke/",
        ]

        q = deque([{"url": u, "breadcrumbs": []} for u in seeds + legacy_seeds])

        seen_pages: set[str] = set()
        collected: List[Dict[str, Any]] = []
        max_pages = 300
        pages = 0

        # Accept both old and new treasury hosts
        accepted_hosts = {"treasury.go.ke", "newsite.treasury.go.ke"}

        def same_host(u: str) -> bool:
            try:
                p = urlparse(u)
            except Exception:
                return False
            return p.netloc.replace("www.", "") in accepted_hosts

        def is_http_link(h: str) -> bool:
            if not h:
                return False
            h = h.strip().lower()
            if h.startswith(("#", "mailto:", "tel:", "javascript:")):
                return False
            return True

        def classify(title: str) -> str:
            t = (title or "").lower()
            if "circular" in t or "circulars" in t:
                return "circular"
            if (
                "borrowing plan" in t
                or "annual borrowing plan" in t
                or "abp" in t
                or "debt" in t
            ):
                return "debt"
            if "qebr" in t or "quarterly economic" in t or "quarterly budgetary" in t:
                return "report"
            if "budget" in t or "bps" in t or "policy statement" in t:
                return "budget"
            return "report"

        def extract_year(text: str) -> Optional[str]:
            tl = (text or "").lower()
            m = re.search(r"fy\s*([0-9]{4}\s*[-/–]\s*[0-9]{4})", tl)
            if m:
                return m.group(1).replace(" ", "")
            m2 = re.search(r"(20[0-9]{2})", tl)
            return m2.group(1) if m2 else None

        def looks_like_list_link(url: str, text: str) -> bool:
            path = (urlparse(url).path or "").lower()
            t = (text or "").lower()
            if any(k in path for k in ["/category/", "/tag/", "/page/"]):
                return True
            # Drupal document section pages on newsite.treasury.go.ke
            if any(
                k in path
                for k in [
                    "/quarterly-economic",
                    "/budget-books",
                    "/budget-policy",
                    "/budget-review",
                    "/general-reports",
                    "/sector-budget",
                    "/directorate-public-debt",
                    "/pdmo-reports",
                    "/debt-policy",
                ]
            ):
                return True
            if any(
                k in t
                for k in [
                    "previous years",
                    "older posts",
                    "qebr",
                    "borrowing",
                    "debt",
                    "budget",
                    "policy statement",
                    "sector report",
                    "annual report",
                ]
            ):
                return True
            # Left side menu links live under the same host and often without file extensions
            return not re.search(r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", path, re.I)

        # Exclusion terms to drop tenders/adverts/press and similar noise
        exclude_terms = {
            "tender",
            "advert",
            "vacancy",
            "recruitment",
            "procurement",
            "eoi",
            "rfq",
            "rfp",
            "press release",
            "media release",
            "speech",
            "obituary",
            "appointment",
        }

        while q and pages < max_pages:
            item = q.popleft()
            url = item["url"]
            if url in seen_pages:
                continue
            seen_pages.add(url)
            soup = self._fetch_html(url, "treasury")
            if not soup:
                continue
            pages += 1

            # Collect file links on page
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not is_http_link(href):
                    continue
                if not re.search(r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", href, re.I):
                    continue
                # Resolve relative URLs against the *current page* URL (not source base)
                # so that /sites/default/files/... on newsite.treasury resolves correctly
                resolved = self._resolve_url(href, url)
                if not same_host(resolved):
                    continue
                title = a.get_text(strip=True) or Path(urlparse(resolved).path).name
                lt = (title or "").lower()
                lp = (resolved or "").lower()
                if any(term in lt or term in lp for term in exclude_terms):
                    continue
                collected.append(
                    {
                        "url": resolved,
                        "title": title,
                        "source": source["name"],
                        "source_key": "treasury",
                        "doc_type": classify(title),
                        "discovered_date": datetime.now().isoformat(),
                        "meta": {
                            "breadcrumbs": item.get("breadcrumbs", []),
                            "year": extract_year(title),
                        },
                        "referrer": url,
                    }
                )

            # Enqueue deeper listing/category/menu links
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not is_http_link(href):
                    continue
                resolved = self._resolve_url(href, url)
                if not same_host(resolved):
                    continue
                text = a.get_text(strip=True) or ""
                if looks_like_list_link(resolved, text):
                    if resolved not in seen_pages:
                        crumbs = item.get("breadcrumbs", [])
                        label = text or Path(urlparse(resolved).path).name
                        q.append(
                            {
                                "url": resolved,
                                "breadcrumbs": (crumbs + [label])[-6:],
                            }
                        )

        # Dedupe
        uniq: Dict[str, Dict[str, Any]] = {}
        for d in collected:
            uniq.setdefault(d["url"], d)
        return list(uniq.values())

    def _s3_key_for(self, source_key: str, md5_hash: str, filename: str) -> str:
        return f"documents/{source_key}/{md5_hash[:2]}/{md5_hash}/{filename}"

    def _maybe_upload_to_s3(
        self, file_path: Path, md5_hash: str, source_key: str, content_type: str
    ) -> Optional[str]:
        if not self.s3 or not self.s3_bucket:
            return None
        key = self._s3_key_for(source_key, md5_hash, file_path.name)
        try:
            # Check existence
            try:
                self.s3.head_object(Bucket=self.s3_bucket, Key=key)
                return key  # already present
            except ClientError:
                pass
            extra_args = {"ContentType": content_type} if content_type else {}
            self.s3.upload_file(
                str(file_path), self.s3_bucket, key, ExtraArgs=extra_args
            )
            return key
        except Exception:
            return None

    def select_treasury_batch(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Select a small batch from Treasury: latest 10 QEBR + 3 ABP + 5 Circulars.
        Uses title heuristics to detect FY and quarter ordering.
        """

        def year_key(title: str) -> int:
            t = (title or "").lower()
            m = re.search(r"(20\d{2})\s*[/–-]\s*(20\d{2})", t)
            if m:
                try:
                    return int(m.group(1)) * 100 + int(m.group(2))
                except Exception:
                    pass
            m2 = re.search(r"(20\d{2})", t)
            return int(m2.group(1)) if m2 else 0

        def quarter_rank(title: str) -> int:
            t = (title or "").lower()
            if "q4" in t or "4th quarter" in t:
                return 4
            if "q3" in t or "3rd quarter" in t:
                return 3
            if (
                "q2" in t
                or "2nd quarter" in t
                or "1st half" in t
                or "first half" in t
                or "half year" in t
            ):
                return 2
            if "q1" in t or "1st quarter" in t:
                return 1
            return 0

        qebr = [
            d
            for d in docs
            if re.search(r"qebr|quarterly\s+economic", (d.get("title") or ""), re.I)
        ]
        abp = [
            d
            for d in docs
            if re.search(
                r"annual\s+borrowing\s+plan|\babp\b", (d.get("title") or ""), re.I
            )
        ]
        circs = [
            d for d in docs if re.search(r"circular", (d.get("title") or ""), re.I)
        ]

        qebr_sorted = sorted(
            qebr,
            key=lambda d: (
                year_key(d.get("title", "")),
                quarter_rank(d.get("title", "")),
            ),
            reverse=True,
        )
        abp_sorted = sorted(
            abp, key=lambda d: year_key(d.get("title", "")), reverse=True
        )
        circ_sorted = sorted(
            circs, key=lambda d: year_key(d.get("title", "")), reverse=True
        )

        return qebr_sorted[:10] + abp_sorted[:3] + circ_sorted[:5]

    def _classify_document_type(self, title: str) -> str:
        """Classify document type based on title"""
        title_lower = title.lower()

        if any(word in title_lower for word in ["audit", "auditor"]):
            return "audit"
        elif any(word in title_lower for word in ["budget", "allocation"]):
            return "budget"
        elif any(
            word in title_lower for word in ["implementation", "review", "expenditure"]
        ):
            return "report"
        elif any(word in title_lower for word in ["debt", "loan", "borrowing"]):
            return "loan"
        else:
            return "other"

    def _resolve_url(self, href: str, base_url: str) -> str:
        """Convert relative URLs to absolute"""
        try:
            return urljoin(base_url if base_url else "", href)
        except Exception:
            # fallback to previous simple rules
            if href.startswith("http"):
                return href
            elif href.startswith("//"):
                return f"https:{href}"
            elif href.startswith("/"):
                return f"{base_url}{href}"
            else:
                return f"{base_url}/{href}"

    def discover_budget_documents(
        self, source_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Public discovery API used by backend: returns discovered docs for a given source or all."""
        keys = [source_key] if source_key else ["treasury", "cob", "oag", "knbs"]
        out: List[Dict[str, Any]] = []
        for k in keys:
            if k == "treasury":
                out.extend(self._discover_treasury())
            elif k == "cob":
                out.extend(self._discover_cob())
            elif k == "oag":
                out.extend(self._discover_oag())
            elif k == "knbs":
                out.extend(self._discover_knbs())
        return out

    async def download_and_process_document(
        self, doc_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Download and process a single document"""
        try:
            # Helper to GET with optional Referer and TLS fallback
            def _get(
                u: str,
                source_key: str,
                ref: Optional[str] = None,
                insecure: bool = False,
            ):
                headers: Dict[str, str] = {}
                if ref:
                    headers["Referer"] = ref
                # Some WordPress download endpoints require a referer even if not given
                if source_key in {"oag", "cob"} and not headers.get("Referer"):
                    headers["Referer"] = self.kenya_sources.get(source_key, {}).get(
                        "base_url", ""
                    )
                verify = self._ssl_verify_for(source_key, insecure)
                try:
                    return self.http.get(u, timeout=60, verify=verify, headers=headers)
                except requests.exceptions.SSLError as ssl_err:
                    if source_key == "knbs" and self.knbs_ca_bundle:
                        logger.error(
                            "KNBS SSL validation failed with pinned bundle %s when fetching %s: %s",
                            self.knbs_ca_bundle,
                            u,
                            ssl_err,
                        )
                    raise

            # Helper to HEAD (or lightweight GET) to evaluate candidate files
            def _head_size(u: str, source_key: str, ref: Optional[str] = None) -> int:
                headers: Dict[str, str] = {"Accept": "*/*"}
                if ref:
                    headers["Referer"] = ref
                if source_key in {"oag", "cob"} and not headers.get("Referer"):
                    headers["Referer"] = self.kenya_sources.get(source_key, {}).get(
                        "base_url", ""
                    )
                try:
                    verify = self._ssl_verify_for(source_key, insecure=False)
                    r = self.http.head(
                        u,
                        timeout=20,
                        allow_redirects=True,
                        headers=headers,
                        verify=verify,
                    )
                    if r.ok:
                        cl = r.headers.get("content-length")
                        return int(cl) if cl and cl.isdigit() else -1
                except Exception:
                    pass
                return -1

            # Rank candidate file URLs: prefer report-like names and bigger files
            def _score_candidate(u: str, title: str = "") -> int:
                score = 0
                ul = (u or "").lower()
                tl = (title or "").lower()
                good_terms = [
                    "report",
                    "budget",
                    "implementation",
                    "birr",
                    "county",
                    "national",
                    "fy",
                    "financial",
                    "annual",
                ]
                bad_terms = ["logo", "branding", "letterhead", "template", "guideline"]
                for g in good_terms:
                    if g in ul or g in tl:
                        score += 10
                for b in bad_terms:
                    if b in ul or b in tl:
                        score -= 15
                # Prefer uploads path
                if "/wp-content/uploads/" in ul:
                    score += 8
                # Prefer PDFs
                if re.search(r"\.pdf($|\?)", ul):
                    score += 5
                return score

            # If URL looks like an HTML landing page (no direct file extension), try to resolve to a file link
            url = doc_info["url"]
            if not re.search(r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", url, re.I):
                soup = self._fetch_html(url, doc_info.get("source_key", ""))
                if soup:
                    candidates = self._resolve_pdfs_on_page(
                        soup,
                        self.kenya_sources.get(doc_info.get("source_key", ""), {}).get(
                            "base_url", ""
                        ),
                    )
                    if candidates:
                        # Choose best candidate by heuristics and HEAD size where available
                        ranked = sorted(
                            candidates,
                            key=lambda u: _score_candidate(
                                u, doc_info.get("title", "")
                            ),
                            reverse=True,
                        )
                        best_url = ranked[0]
                        # Try a small set to find the largest file by content-length when ties
                        referrer = doc_info.get("referrer") or (
                            doc_info.get("meta") or {}
                        ).get("referrer")
                        sizes = []
                        for cand in ranked[:5]:
                            sz = _head_size(
                                cand, doc_info.get("source_key", ""), referrer
                            )
                            sizes.append((sz, cand))
                        sizes = [t for t in sizes if t[0] >= 0]
                        if sizes:
                            sizes.sort(reverse=True)  # largest first
                            # If the largest is substantially bigger (>500KB), prefer it
                            if sizes[0][0] >= 500_000:
                                best_url = sizes[0][1]
                        url = best_url
                        doc_info["url"] = url

            # Download the document (with SSL fallback for OAG/COB and Referer if present)
            source_key = doc_info.get("source_key") or ""
            referrer = doc_info.get("referrer") or (doc_info.get("meta") or {}).get(
                "referrer"
            )
            if source_key in {"oag", "cob"}:
                try:
                    response = _get(url, source_key, referrer, insecure=False)
                    response.raise_for_status()
                except Exception:
                    response = _get(url, source_key, referrer, insecure=True)
                    response.raise_for_status()
            else:
                response = _get(url, source_key, referrer, insecure=False)
            response.raise_for_status()

            content = response.content
            ctype = (response.headers.get("content-type") or "").lower()

            # If server returned HTML for a download URL, try to resolve actual file links from that HTML
            if (
                "text/html" in ctype
                or content[:256].lstrip().lower().startswith(b"<html")
                or content[:256].lstrip().lower().startswith(b"<!doctype html")
            ) and not re.search(r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", url, re.I):
                try:
                    soup = BeautifulSoup(content, "html.parser")
                    candidates = self._resolve_pdfs_on_page(
                        soup,
                        self.kenya_sources.get(source_key, {}).get("base_url", ""),
                    )
                    # Fallback: WordPress Download Manager pages often require hitting ?wpdmdl=<ID>
                    if not candidates:
                        try:
                            html_text = content.decode("utf-8", "ignore")
                        except Exception:
                            html_text = ""
                        wpd_ids = set(re.findall(r"wpdmdl=(\d+)", html_text, re.I))
                        base_root = (
                            self.kenya_sources.get(source_key, {})
                            .get("base_url", "")
                            .rstrip("/")
                        )
                        for wid in wpd_ids:
                            for suffix in [
                                f"/?wpdmdl={wid}",
                                f"/?wpdmdl={wid}&refresh=1",
                            ]:
                                cand_url = base_root + suffix
                                if cand_url not in candidates:
                                    candidates.append(cand_url)
                    # Headless fallback (COB only) if still no direct candidates
                    if source_key == "cob" and not candidates and headless_allowed():
                        try:
                            headless_res = await fetch_cob_download(url)
                            if headless_res:
                                data_bytes, inferred_name = headless_res
                                if data_bytes and (
                                    data_bytes.startswith(b"%PDF")
                                    or len(data_bytes) > 2048
                                ):
                                    content = data_bytes
                                    ctype = (
                                        "application/pdf"
                                        if data_bytes.startswith(b"%PDF")
                                        else ctype
                                    )
                                    # Provide synthetic filename via doc_info
                                    if inferred_name:
                                        doc_info["title"] = (
                                            doc_info.get("title") or inferred_name
                                        )
                                    # Mark URL variant to avoid re-processing loops
                                    doc_info["url"] = url + "#headless"
                                    candidates = (
                                        []
                                    )  # ensure normal candidate loop skipped
                        except Exception:
                            pass
                    if candidates:
                        # Reuse same ranking logic
                        ranked = sorted(
                            candidates,
                            key=lambda u: _score_candidate(
                                u, doc_info.get("title", "")
                            ),
                            reverse=True,
                        )
                        tried = 0
                        for cand in ranked[:5]:
                            tried += 1
                            try:
                                r2 = _get(
                                    cand,
                                    source_key,
                                    referrer,
                                    insecure=(source_key in {"oag", "cob"}),
                                )
                                r2.raise_for_status()
                                data = r2.content
                                ctype2 = (r2.headers.get("content-type") or "").lower()
                                if (b"%PDF" in data[:512]) or re.search(
                                    r"\.(pdf|xlsx?|csv|docx?|zip)($|\?)", cand, re.I
                                ):
                                    # accept likely file
                                    url = cand
                                    doc_info["url"] = url
                                    response = r2
                                    content = data
                                    ctype = ctype2
                                    break
                            except Exception:
                                continue
                        else:
                            # no acceptable candidate
                            pass
                except Exception:
                    pass

            # Final sanity: ensure we didn't fetch HTML masquerading as a file
            if ("text/html" in ctype) or (
                content[:16].lstrip().lower().startswith(b"<!doctype html")
                or content[:8] == b"<html>".lower()
            ):
                raise RuntimeError("Resolved URL returned HTML, not a document file")
            md5_hash = hashlib.md5(content).hexdigest()

            # Skip if already processed (cache manifest)
            cached = self.processed_manifest.get("by_md5", {}).get(md5_hash)
            if cached:
                return {
                    "document_id": cached.get("document_id"),
                    "file_path": cached.get("file_path"),
                    "extraction_result": {},
                    "normalized_data": [],
                    "skipped": True,
                }

            # Save to local storage with a robust filename
            url_path_name = Path(urlparse(url).path).name
            # Try to infer filename from headers when missing
            cd = response.headers.get("content-disposition", "")
            guessed = None
            if "filename=" in cd:
                guessed = cd.split("filename=")[-1].strip("\"' ")
            if not url_path_name and guessed:
                url_path_name = guessed
            if not url_path_name:
                # fallback default
                url_path_name = (
                    "document.pdf"
                    if "pdf" in response.headers.get("content-type", "").lower()
                    else "document.bin"
                )
            filename = f"{doc_info['source_key']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{url_path_name}"
            file_path = self.storage_path / filename

            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(f"Downloaded: {doc_info['title']} -> {file_path}")

            # Optional: upload to S3-compatible storage
            s3_key = self._maybe_upload_to_s3(
                file_path,
                md5_hash,
                doc_info.get("source_key", "unknown"),
                response.headers.get("content-type", "application/octet-stream"),
            )

            # Extract structured data from PDF
            extraction_result = self.extractor.extract_with_fallback(str(file_path))

            # Prepare document record for database
            document_record = {
                "title": doc_info["title"],
                "url": doc_info["url"],
                "file_path": str(file_path),
                "publisher": doc_info["source"],
                "doc_type": doc_info["doc_type"],
                "fetch_date": datetime.now(),
                "md5": md5_hash,
                "country_id": 1,  # Kenya
                "metadata": {
                    "file_size": len(content),
                    "source_key": doc_info["source_key"],
                    "extraction_confidence": extraction_result.get("confidence", 0),
                    "report_meta": doc_info.get("meta"),
                    "storage": {"s3_key": s3_key} if s3_key else {},
                },
            }

            # Route by document type
            if doc_info["doc_type"] == "audit":
                # Parse audit findings
                findings = self.audit_parser.parse(
                    extraction_result,
                    {"title": doc_info["title"], "file_path": str(file_path)},
                )

                # Validate audit findings (Week 1 Task 2: Data Quality)
                validated_findings = []
                validation_stats = {
                    "total": len(findings),
                    "valid": 0,
                    "rejected": 0,
                    "warnings": 0,
                }

                for finding in findings:
                    validation_result = self.data_validator.validate_audit_data(finding)

                    if validation_result.is_valid:
                        # Add confidence score and validation metadata
                        finding["confidence_score"] = validation_result.confidence
                        finding["validation_warnings"] = validation_result.warnings
                        validated_findings.append(finding)
                        validation_stats["valid"] += 1

                        if validation_result.warnings:
                            validation_stats["warnings"] += len(
                                validation_result.warnings
                            )
                    else:
                        validation_stats["rejected"] += 1
                        logger.warning(
                            f"Rejected audit finding with confidence {validation_result.confidence:.2f}: "
                            f"Errors: {validation_result.errors}"
                        )

                logger.info(
                    f"Audit validation complete: {validation_stats['valid']}/{validation_stats['total']} valid, "
                    f"{validation_stats['rejected']} rejected, {validation_stats['warnings']} warnings"
                )

                # Store validation statistics in document metadata
                document_record["metadata"]["validation_stats"] = validation_stats

                # Load validated findings to database
                doc_id = await self.db_loader.load_audit_findings_document(
                    document_record, validated_findings
                )
                # For return payload consistency
                normalized_data = [
                    {"_kind": "audit_finding", **f} for f in validated_findings
                ]
            else:
                # KNBS economic documents: parse with KNBSParser and emit structured items
                knbs_loaded = False
                if doc_info.get("source_key") == "knbs" and self.knbs_parser:
                    try:
                        knbs_meta = {
                            "type": doc_info.get("doc_type") or "unknown",
                            "url": doc_info.get("url"),
                            "title": doc_info.get("title"),
                            "county": doc_info.get("county"),
                            "year": doc_info.get("year"),
                        }
                        knbs_result = self.knbs_parser.parse_document(knbs_meta)

                        # County whitelist to avoid creating bogus entities from sub-counties/regions/"Total"
                        try:
                            county_list = []
                            if getattr(self.knbs_parser, "counties", None):
                                county_list = [
                                    c.strip() for c in self.knbs_parser.counties
                                ]
                            elif getattr(self.knbs_extractor, "counties", None):
                                county_list = [
                                    c.strip() for c in self.knbs_extractor.counties
                                ]
                            valid_counties = {c.lower(): c for c in county_list}
                        except Exception:
                            valid_counties = {}

                        def resolve_county_name(name: Optional[str]) -> Optional[str]:
                            if not name:
                                return None
                            raw = str(name).strip()
                            # Remove trailing "County" if present for matching
                            base = (
                                raw[:-6].strip()
                                if raw.lower().endswith("county")
                                else raw
                            )
                            key = base.lower()
                            return valid_counties.get(key)

                        # Map parser output to normalized items with _kind values
                        knbs_items: list[dict] = []

                        # Population
                        for pd in knbs_result.get("population_data", []) or []:
                            total = pd.get("total_population")
                            if total and float(total) > 0:
                                county = resolve_county_name(
                                    pd.get("county") or doc_info.get("county")
                                )
                                # Only create county entities for known counties; otherwise skip row to avoid sub-county noise
                                if county:
                                    entity = {
                                        "canonical_name": f"{county} County",
                                        "type": "COUNTY",
                                        "raw_name": county,
                                    }
                                else:
                                    # If not a valid county label, treat as national aggregate only if document is not a county abstract
                                    if resolve_county_name(doc_info.get("county")):
                                        # This is a county abstract but row label isn't a county — likely sub-county/Total; skip
                                        continue
                                    entity = {
                                        "canonical_name": "Kenya",
                                        "type": "NATIONAL",
                                    }
                                knbs_items.append(
                                    {
                                        "_kind": "population_data",
                                        "entity": entity,
                                        "year": pd.get("year") or doc_info.get("year"),
                                        "total_population": int(total),
                                        "male_population": pd.get("male_population"),
                                        "female_population": pd.get(
                                            "female_population"
                                        ),
                                        "urban_population": pd.get("urban_population"),
                                        "rural_population": pd.get("rural_population"),
                                        "population_density": pd.get(
                                            "population_density"
                                        ),
                                        "source_page": pd.get("source_page"),
                                        "confidence": pd.get("confidence", 1.0),
                                    }
                                )

                        # GDP / GCP
                        for gd in knbs_result.get("gdp_data", []) or []:
                            gval = gd.get("gdp_value")
                            if gval and float(gval) > 0:
                                county = resolve_county_name(
                                    gd.get("county") or doc_info.get("county")
                                )
                                if county:
                                    entity = {
                                        "canonical_name": f"{county} County",
                                        "type": "COUNTY",
                                        "raw_name": county,
                                    }
                                else:
                                    if resolve_county_name(doc_info.get("county")):
                                        # County doc with non-county label in row; skip
                                        continue
                                    entity = {
                                        "canonical_name": "Kenya",
                                        "type": "NATIONAL",
                                    }
                                knbs_items.append(
                                    {
                                        "_kind": "gdp_data",
                                        "entity": entity,
                                        "year": gd.get("year") or doc_info.get("year"),
                                        "quarter": gd.get("quarter"),
                                        "gdp_value": float(gd.get("gdp_value")),
                                        "gdp_growth_rate": gd.get("growth_rate"),
                                        "currency": "KES",
                                        "source_page": gd.get("source_page"),
                                        "confidence": gd.get("confidence", 1.0),
                                    }
                                )

                        # Indicators
                        for ind in knbs_result.get("economic_indicators", []) or []:
                            val = ind.get("value")
                            if val is not None and float(val) != 0.0:
                                county = resolve_county_name(
                                    ind.get("county") or doc_info.get("county")
                                )
                                if county:
                                    entity = {
                                        "canonical_name": f"{county} County",
                                        "type": "COUNTY",
                                        "raw_name": county,
                                    }
                                else:
                                    if resolve_county_name(doc_info.get("county")):
                                        # County doc with non-county row; skip
                                        continue
                                    entity = {
                                        "canonical_name": "Kenya",
                                        "type": "NATIONAL",
                                    }
                                knbs_items.append(
                                    {
                                        "_kind": "economic_indicator",
                                        "entity": entity,
                                        "indicator_type": ind.get("indicator_type")
                                        or ind.get("type"),
                                        "period": ind.get("period")
                                        or str(knbs_meta.get("year")),
                                        "unit": ind.get("unit"),
                                        "value": float(val),
                                        "source_page": ind.get("source_page"),
                                        "confidence": ind.get("confidence", 1.0),
                                    }
                                )

                        # Load to DB (no budget normalization/validation for KNBS structured payloads)
                        doc_id = await self.db_loader.load_document(
                            document_record, knbs_items
                        )

                        normalized_data = knbs_items
                        knbs_loaded = True
                        # Update manifest and return handled below
                    except Exception as knbs_err:
                        logger.error(f"KNBS parse/load failed: {knbs_err}")
                        # Fall back to generic normalization so we still retain the document record
                        normalized_data = []
                        doc_id = await self.db_loader.load_document(
                            document_record, normalized_data
                        )
                if not knbs_loaded:
                    # Normalize tabular data for budgets/reports
                    normalized_data = self.normalizer.normalize_extracted_data(
                        extraction_result, doc_info["source_key"], doc_info["doc_type"]
                    )

                # Validate budget data (Week 1 Task 2: Data Quality)
                validated_data = []
                validation_stats = {
                    "total": len(normalized_data),
                    "valid": 0,
                    "rejected": 0,
                    "warnings": 0,
                }

                for item in normalized_data:
                    # Skip budget-line validation when KNBS structured items were already handled
                    if doc_info.get("source_key") == "knbs" and self.knbs_parser:
                        continue
                    validation_result = self.data_validator.validate_budget_data(item)

                    if validation_result.is_valid:
                        # Add confidence score and validation metadata
                        item["confidence_score"] = validation_result.confidence
                        item["validation_warnings"] = validation_result.warnings
                        validated_data.append(item)
                        validation_stats["valid"] += 1

                        if validation_result.warnings:
                            validation_stats["warnings"] += len(
                                validation_result.warnings
                            )
                    else:
                        validation_stats["rejected"] += 1
                        logger.warning(
                            f"Rejected budget line with confidence {validation_result.confidence:.2f}: "
                            f"Errors: {validation_result.errors}"
                        )

                logger.info(
                    f"Budget validation complete: {validation_stats['valid']}/{validation_stats['total']} valid, "
                    f"{validation_stats['rejected']} rejected, {validation_stats['warnings']} warnings"
                )

                # Store validation statistics in document metadata
                document_record["metadata"]["validation_stats"] = validation_stats

                # Load validated data to database when not already handled by KNBS branch
                if not (doc_info.get("source_key") == "knbs" and knbs_loaded):
                    doc_id = await self.db_loader.load_document(
                        document_record, validated_data
                    )

                # Update normalized_data reference for return payload
                normalized_data = validated_data

            # Update manifest
            self.processed_manifest.setdefault("by_md5", {})[md5_hash] = {
                "document_id": doc_id,
                "file_path": str(file_path),
                "url": doc_info["url"],
                "title": doc_info["title"],
                "source": doc_info["source"],
                "doc_type": doc_info["doc_type"],
                "fetched": datetime.now().isoformat(),
                "s3_key": s3_key,
            }
            self._save_manifest()

            return {
                "document_id": doc_id,
                "file_path": str(file_path),
                "extraction_result": extraction_result,
                "normalized_data": normalized_data,
            }

        except Exception as e:
            logger.error(f"Error processing document {doc_info['url']}: {e}")
            return None

    async def run_full_pipeline(self) -> Dict[str, Any]:
        """Run the complete data ingestion pipeline for Kenya MVP with smart scheduling"""
        pipeline_results = {
            "start_time": datetime.now().isoformat(),
            "sources_processed": {},
            "total_documents": 0,
            "successful_extractions": 0,
            "errors": [],
            "scheduler_decisions": {},  # Track which sources ran and why
        }

        # Get scheduler recommendations
        logger.info("Checking smart scheduler for sources to run...")
        schedule_summary = self.scheduler.get_schedule_summary()
        logger.info(
            f"Scheduler efficiency: Skipping {schedule_summary['efficiency']['skip_percentage']}% of sources today"
        )

        # Process each major source (with smart scheduling)
        all_sources = ["treasury", "cob", "oag", "knbs"]  # Current active sources

        for source_key in all_sources:
            # Check if source should run today
            should_run, reason = self.scheduler.should_run(source_key)

            pipeline_results["scheduler_decisions"][source_key] = {
                "should_run": should_run,
                "reason": reason,
            }

            if not should_run:
                logger.info(f"⏸️  Skipping {source_key}: {reason}")
                next_run, next_reason = self.scheduler.get_next_run(source_key)
                logger.info(f"   Next run scheduled for: {next_run} - {next_reason}")
                continue

            logger.info(f"✅ Processing source: {source_key} - {reason}")

            try:
                # Discover documents
                discovered_docs = self.discover_budget_documents(source_key)

                source_results = {
                    "discovered": len(discovered_docs),
                    "processed": 0,
                    "successful": 0,
                    "documents": [],
                    "schedule_reason": reason,
                }

                # Process each document (limit to recent ones for MVP)
                recent_docs = discovered_docs[:5]  # Limit to 5 most recent per source

                for doc_info in recent_docs:
                    result = await self.download_and_process_document(doc_info)
                    source_results["processed"] += 1

                    if result:
                        source_results["successful"] += 1
                        source_results["documents"].append(result["document_id"])
                        pipeline_results["successful_extractions"] += 1

                    # Rate limiting - be respectful to government servers
                    await asyncio.sleep(2)

                pipeline_results["sources_processed"][source_key] = source_results
                pipeline_results["total_documents"] += source_results["processed"]

            except Exception as e:
                error_msg = f"Error processing source {source_key}: {e}"
                logger.error(error_msg)
                pipeline_results["errors"].append(error_msg)

        pipeline_results["end_time"] = datetime.now().isoformat()

        # Save pipeline results
        results_file = (
            self.storage_path
            / f"pipeline_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(results_file, "w") as f:
            json.dump(pipeline_results, f, indent=2, default=str)

        logger.info(f"Pipeline completed. Results saved to {results_file}")
        return pipeline_results


if __name__ == "__main__":
    pipeline = KenyaDataPipeline()
    results = asyncio.run(pipeline.run_full_pipeline())
    print(
        f"Pipeline completed: {results['successful_extractions']}/{results['total_documents']} documents processed successfully"
    )
