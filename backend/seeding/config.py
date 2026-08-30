"""Runtime configuration for the seeding orchestration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils import parse_rate_limit


class SeedingSettings(BaseSettings):
    """Configuration options controlling seeding behaviour."""

    rate_limit: str = Field(
        default="60/min",
        description="Requests per time window e.g. '60/min' or '5/sec'.",
    )
    timeout_seconds: float = Field(
        default=30.0,
        description="HTTP request timeout in seconds for upstream fetches.",
    )
    # Hard cap on how long a single domain handler may run before the CLI
    # aborts it and moves to the next domain. Protects `seed --all` from
    # a single stuck domain (e.g. counties_budget blocking on a slow PDF
    # parse) eating the whole nightly window. 10 min is generous — the
    # slowest healthy domain runs in ~5 min.
    domain_timeout_seconds: int = Field(
        default=600,
        ge=1,
        description="Per-domain hard timeout; aborts one domain without killing the run.",
    )
    # Global wall-clock budget for an entire `seed --all` run. The CLI stops
    # *starting* new domains once this elapses and caps the in-flight domain's
    # alarm at the time remaining, so the process always exits cleanly before
    # the CI step timeout (25 min) rather than being SIGKILLed mid-run — a hard
    # kill marks the step failed and skips the downstream validation job.
    # 22 min leaves ~3 min of headroom under the 25 min step cap. Set to 0 to
    # disable the global budget (rely on per-domain timeouts only).
    total_timeout_seconds: int = Field(
        default=1320,
        ge=0,
        description="Global wall-clock budget for `seed --all`; 0 disables it.",
    )
    max_retries: int = Field(
        default=3, description="Maximum retry attempts for transient HTTP failures."
    )
    retry_backoff: float = Field(
        default=2.0, description="Exponential backoff factor between retries."
    )
    user_agent: str = Field(
        default="KenyaAuditAppSeeder/1.0 (+https://github.com/Rodgers31/audit_app-)",
        description="User agent sent with outbound HTTP requests.",
    )
    contact_email: Optional[str] = Field(
        default=None, description="Contact email advertised to data providers."
    )
    storage_path: Path = Field(
        default=Path("data/seeding"),
        description="Base directory for caching downloads and generated assets.",
    )
    cache_path: Path = Field(
        default=Path("data/seeding/cache"),
        description="Directory dedicated to HTTP/download caches.",
    )
    cache_ttl_seconds: int = Field(
        default=86_400,
        description="How long cached HTTP responses remain valid (in seconds).",
    )
    log_level: str = Field(
        default="INFO", description="Logging level for seeding runs."
    )
    log_path: Optional[Path] = Field(
        default=None,
        description="Optional file path for JSON logs (stdout only when unset).",
    )
    http_cache_enabled: bool = Field(
        default=True,
        description="Toggle lightweight caching of HTTP responses where safe.",
    )
    http_follow_redirects: bool = Field(
        default=True,
        description="Whether HTTP client should automatically follow redirects.",
    )
    # ── Large-PDF streaming download + cross-run PDF cache ─────────────
    # Government BIRR/audit PDFs are 12-50MB and the COB CDN's throughput
    # swings wildly night to night (the same 48MB county file measured
    # ~50s one night and ~556s the next). The two guards below stop a
    # slow-CDN night from consuming the whole per-domain SIGALRM budget
    # and aborting the run mid-parse (issue #119).
    pdf_download_timeout_seconds: float = Field(
        default=300.0,
        ge=1.0,
        description=(
            "TOTAL wall-clock cap for a single streamed large-PDF download. "
            "Unlike timeout_seconds (a per-operation httpx timeout — the max "
            "gap between chunks), this bounds the whole transfer, so a "
            "slow-but-steady trickle cannot run unbounded. On breach the "
            "downloader raises a plain Exception and the domain falls back to "
            "its fixture instead of the per-domain budget aborting mid-parse. "
            "Since downloads became RESUMABLE (a timeout now keeps its bytes "
            "and the next attempt continues via HTTP Range), this cap no "
            "longer decides whether a document is EVER fetched — only how "
            "much progress one run makes. Raised 180s->300s so the common "
            "case finishes in a single run while still leaving room inside "
            "domain_timeout_seconds (600s) for the ~254s a county-PDF parse "
            "needs."
        ),
    )
    pdf_download_max_bytes: int = Field(
        default=120 * 1024 * 1024,
        ge=1,
        description=(
            "Defensive size ceiling for a streamed PDF download. COB county "
            "BIRR PDFs are ~48MB; 120MB leaves headroom while still catching "
            "a runaway or wrong-content-type body before it fills the disk."
        ),
    )
    pdf_cache_ttl_seconds: int = Field(
        default=30 * 86_400,
        ge=0,
        description=(
            "How long a downloaded source PDF stays reusable in the on-disk "
            "PDF cache. A published BIRR report is immutable for a quarter, so "
            "30 days lets a slow-CDN night reuse the last good download instead "
            "of re-pulling ~48MB; when COB publishes the next report its URL "
            "changes and the stale entry is simply never requested again. "
            "Persist the cache dir across CI runs (actions/cache) for this to "
            "help the nightly job. 0 disables the PDF cache."
        ),
    )
    population_dataset_url: str = Field(
        default="file://seeding/real_data/population.json",
        description=(
            "Endpoint providing population statistics payloads. "
            "Use file:// for local fixtures or https:// for production APIs "
            "(e.g., https://www.knbs.or.ke/data/population.json)."
        ),
    )
    budgets_dataset_url: str = Field(
        default="file://seeding/real_data/budgets.json",
        description=(
            "Endpoint containing county budget summaries. "
            "Use file:// for local fixtures or https:// for production APIs "
            "(e.g., https://cob.go.ke/api/budgets or OpenData portal)."
        ),
    )
    audits_dataset_url: str = Field(
        default="file://seeding/real_data/audits.json",
        description=(
            "Endpoint containing audit findings dataset. "
            "Use file:// for local fixtures or https:// for production APIs "
            "(e.g., https://oagkenya.go.ke/reports/data.json)."
        ),
    )
    economic_indicators_dataset_url: str = Field(
        default="file://seeding/real_data/economic_indicators.json",
        description=(
            "Endpoint containing economic indicator time series. "
            "Use file:// for local fixtures or https:// for production APIs "
            "(e.g., https://www.knbs.or.ke/data/economic-indicators.json)."
        ),
    )
    national_debt_dataset_url: str = Field(
        default="file://seeding/real_data/national_debt.json",
        description=(
            "Endpoint containing national debt and loan data (CBK Public Debt Bulletin). "
            "Use file:// for local data or https:// for production APIs "
            "(e.g., https://www.centralbank.go.ke/public-debt/)."
        ),
    )
    pending_bills_dataset_url: Optional[str] = Field(
        default="file://seeding/fixtures/pending_bills.json",
        description=(
            "Endpoint containing pending bills data. "
            "If None, the live COB ETL extractor runs instead. "
            "Use file:// for local fixtures or https:// for production APIs "
            "(e.g., https://cob.go.ke/api/pending-bills). "
            "Source: Office of the Controller of Budget "
            "(https://cob.go.ke/publications/pending-bills/)."
        ),
    )
    debt_timeline_dataset_url: str = Field(
        default="file://seeding/real_data/debt_timeline.json",
        description=(
            "Endpoint containing historical public debt timeline by year. "
            "Use file:// for local fixtures or https:// for production APIs. "
            "Source: CBK Annual Reports & National Treasury BPS."
        ),
    )
    fiscal_summary_dataset_url: str = Field(
        default="file://seeding/real_data/fiscal_summary.json",
        description=(
            "Endpoint containing national fiscal summary (budget, revenue, debt service). "
            "Use file:// for local fixtures or https:// for production APIs. "
            "Source: National Treasury BPS & Controller of Budget Reports."
        ),
    )
    revenue_by_source_dataset_url: str = Field(
        default="file://seeding/real_data/revenue_by_source.json",
        description=(
            "Endpoint containing revenue breakdown by tax type per fiscal year. "
            "Use file:// for local fixtures or https:// for production APIs. "
            "Source: KRA Annual Revenue Performance Reports."
        ),
    )
    learning_hub_dataset_url: str = Field(
        default="file://seeding/fixtures/learning_hub.json",
        description=(
            "Endpoint containing educational questions for the learning hub. "
            "Use file:// for local fixtures or curated content APIs."
        ),
    )
    national_budget_execution_dataset_url: str = Field(
        default="file://seeding/real_data/national_budget_execution.json",
        description=(
            "Endpoint containing national government budget execution by sector. "
            "Use file:// for local fixtures or https:// for production APIs. "
            "Source: Controller of Budget Annual NG-BIRR Reports."
        ),
    )
    # ── Live PDF source URLs ────────────────────────────────────
    cbk_public_debt_page_url: str = Field(
        default="https://www.centralbank.go.ke/public-debt/",
        description=(
            "CBK public debt page URL. Scraped to discover the latest "
            "Monthly Statistical Bulletin PDF link."
        ),
    )
    cbk_statistical_bulletin_url: Optional[str] = Field(
        default=None,
        description=(
            "Direct URL to the latest CBK Statistical Bulletin PDF. "
            "When set, the national_debt domain extracts Table 4.1.4 "
            "('Composition of Government Gross Domestic Debt by "
            "Instrument') and overlays per-instrument domestic debt "
            "values onto the fixture. When unset (the default) or the "
            "URL 404s, domestic debt stays on fixture values. "
            "Example: https://www.centralbank.go.ke/uploads/cbk_"
            "statistical_bulletins/<hash>/sbull_jun25.pdf — the path "
            "changes each release, so this is opt-in via env var. "
            "Auto-discovery from the CBK statistics page is a planned "
            "follow-up."
        ),
    )
    cbk_statistical_bulletin_page_url: str = Field(
        default="https://www.centralbank.go.ke/releases/statistical-bulletin/",
        description=(
            "CBK Statistical Bulletin listing page. Scraped each run to "
            "discover the CURRENT bulletin PDF, because the direct path "
            "carries a per-release upload hash "
            "(/uploads/statistical_bulletin/<hash>_December 2025.pdf) that "
            "cannot be predicted. Discovery replaces the hardcoded "
            "cbk_statistical_bulletin_url, which was never set — so the "
            "domestic-debt-by-instrument overlay had simply never run."
        ),
    )
    treasury_brop_page_url: str = Field(
        default="https://www.treasury.go.ke/budget-review-and-outlook-paper/",
        description=(
            "National Treasury BROP listing page. Scraped to discover the "
            "current Budget Review and Outlook Paper, so a new edition is "
            "picked up automatically instead of the pipeline silently "
            "re-reading last year's hardcoded PDF path."
        ),
    )
    cob_birr_page_url: str = Field(
        default="https://cob.go.ke/publications/national-government-budget-implementation-review-reports/",
        description=(
            "COB National Government BIRR reports page. Scraped to discover "
            "the latest quarterly budget implementation review PDF."
        ),
    )
    kra_revenue_url: Optional[str] = Field(
        default=None,
        description=(
            "KRA revenue-performance page or PDF URL (FY revenue results). "
            "When set, the revenue_by_source domain extracts the per-tax-type "
            "breakdown (PAYE, VAT, Corporation, Excise, Customs) and overlays "
            "it onto the fixture for the matched fiscal year — ONLY if the "
            "parse passes the plausibility/reconciliation gate. When unset "
            "(the default) or unreachable, the breakdown stays on fixture "
            "values. Opt-in because KRA's publication URL/format changes each "
            "release and must be confirmed before trusting the parse. Example: "
            "https://www.kra.go.ke/news-center/press-release/<slug>"
        ),
    )
    treasury_budget_books_page_url: str = Field(
        default="https://www.treasury.go.ke/budget-books/",
        description=(
            "National Treasury Budget Books listing page. Scraped each run "
            "to discover the CURRENT fiscal year's approved Budget "
            "Estimates (the Programme Based Budget book), which is where "
            "the ENACTED budget for a new fiscal year first appears. COB "
            "cannot supply it: COB publishes at quarter-end + 45 days, so "
            "an FY that started on 1 July has no COB report until mid "
            "November. Without this source the site could only ever show "
            "last year's budget between July and November."
        ),
    )
    treasury_bps_page_url: str = Field(
        default="https://www.treasury.go.ke/budget-policy-statement/",
        description=(
            "National Treasury Budget Policy Statement page. "
            "Scraped to discover the latest BPS PDF."
        ),
    )
    treasury_brop_url: Optional[str] = Field(
        default=(
            "https://www.treasury.go.ke/sites/default/files/"
            "2025-Budget-Review-and-Outlook-Paper-1.pdf"
        ),
        description=(
            "Direct URL to the latest National Treasury Budget Review "
            "and Outlook Paper (BROP) PDF. The pending_bills domain "
            "extracts paragraph 18 (national aggregate) and Table 10 "
            "(per-county breakdown) from this document. The path "
            "changes each year — set ``SEED_TREASURY_BROP_URL`` to the "
            "new release URL when the next BROP drops, or set to None "
            "to skip live fetch and use the fixture. Auto-discovery "
            "from the Treasury landing page is a planned follow-up."
        ),
    )
    live_pdf_fetch_enabled: bool = Field(
        default=True,
        description=(
            "Whether to attempt live PDF fetching from government websites. "
            "When False, only fixture/configured URLs are used."
        ),
    )
    audits_ocr_enabled: bool = Field(
        default=False,
        description=(
            "OCR scanned OAG audit report PDFs (pytesseract + pdf2image). "
            "OAG publishes county audit reports as scanned images with no "
            "embedded text, so without OCR the live audit path yields "
            "nothing. Requires system tesseract-ocr + poppler-utils "
            "(installed in the seed workflow). Off by default so local "
            "runs without the binaries stay fast and warning-free."
        ),
    )
    audits_ocr_max_pages: int = Field(
        default=30,
        description=(
            "Page cap per PDF for the OCR path. OCR costs ~2-5s/page; "
            "the audit-opinion sections OAG reports lead with fit inside "
            "the first ~30 pages."
        ),
    )
    counties_budget_prefer_live_source: bool = Field(
        default=True,
        description=(
            "When True (default), the counties_budget fetcher tries the "
            "Controller of Budget County BIRR PDFs before falling back to "
            "the local CRA-formula fixture at seeding/real_data/"
            "budgets.json. When False, the fixture is used unconditionally "
            "— useful for offline development or reproducing a known state. "
            "Independent of live_pdf_fetch_enabled: set both True for "
            "production, both False for a fully-deterministic local run."
        ),
    )
    counties_budget_cob_reports_url: str = Field(
        default="https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/",
        description=(
            "Controller of Budget Consolidated County BIRR landing page, "
            "scraped to discover the latest quarterly and annual county "
            "execution PDFs. Secondary candidate (tried when the primary "
            "404s): https://cob.go.ke/publications/county-reports/."
        ),
    )
    counties_budget_cob_wp_api_url: str = Field(
        default=(
            "https://cob.go.ke/wp-json/wp/v2/media"
            "?per_page=100&mime_type=application/pdf&orderby=date&order=desc"
        ),
        description=(
            "Controller of Budget WordPress REST API endpoint for PDF "
            "media. Preferred over HTML scraping because the landing "
            "pages frequently return 415/5xx behind the CDN while the "
            "WP JSON endpoint stays 200 and returns structured "
            "{title, date, source_url, mime_type} records we can sort "
            "and filter deterministically. See "
            "counties_budget.fetcher._discover_latest_county_birr_via_wp_api."
        ),
    )

    # ── World Bank API (free, unauthenticated) ───────────────────
    worldbank_api_base_url: str = Field(
        default="https://api.worldbank.org/v2",
        description=(
            "Base URL for World Bank Indicators API. "
            "Used to enrich GDP data in debt_timeline and economic_indicators. "
            "Free, no API key needed. Rate limit ~30 req/s."
        ),
    )
    worldbank_cache_ttl_seconds: int = Field(
        default=86_400,
        description=(
            "TTL for cached World Bank API responses (seconds). "
            "Default 24 hours — this data rarely changes."
        ),
    )
    enrich_with_worldbank: bool = Field(
        default=True,
        description=(
            "Whether to attempt World Bank API enrichment during seeding. "
            "When False, only fixture/configured URLs are used."
        ),
    )

    budget_default_currency: str = Field(
        default="KES",
        description="Fallback currency code for budget records when missing.",
    )
    dry_run_default: bool = Field(
        default=False,
        description="Whether runs should avoid DB writes unless explicitly overridden.",
    )

    model_config = SettingsConfigDict(env_prefix="SEED_", extra="ignore")

    def ensure_directories(self) -> None:
        """Create storage-related directories if they do not already exist."""

        self.storage_path.expanduser().mkdir(parents=True, exist_ok=True)
        self.cache_path.expanduser().mkdir(parents=True, exist_ok=True)
        if self.log_path:
            self.log_path.expanduser().parent.mkdir(parents=True, exist_ok=True)

    @property
    def rate_limit_window(self) -> Tuple[int, float]:
        """Return rate limiter configuration (tokens, period seconds)."""

        return parse_rate_limit(self.rate_limit)

    @property
    def default_headers(self) -> Dict[str, str]:
        """Return default headers to include with outbound HTTP requests."""

        headers: Dict[str, str] = {"User-Agent": self.user_agent}
        if self.contact_email:
            headers["From"] = self.contact_email
        return headers

    def dataset_title(self, domain: str) -> str:
        """Return a human readable title for a dataset domain."""

        mapping = {
            "population": "Kenya Population Statistics",
            "budgets": "County Budget Execution Summary",
            "audits": "County Audit Findings",
            "economic_indicators": "Economic Indicators Time Series",
        }
        return mapping.get(domain, f"{domain.title()} Dataset")


@lru_cache(maxsize=1)
def get_settings() -> SeedingSettings:
    """Return cached settings instance."""

    settings = SeedingSettings()
    settings.ensure_directories()
    return settings
