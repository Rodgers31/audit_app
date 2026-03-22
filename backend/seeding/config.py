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
            "(https://cob.go.ke/reports/pending-bills/)."
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
    cob_birr_page_url: str = Field(
        default="https://cob.go.ke/reports/national-government-budget-implementation-review-reports/",
        description=(
            "COB National Government BIRR reports page. Scraped to discover "
            "the latest quarterly budget implementation review PDF."
        ),
    )
    treasury_bps_page_url: str = Field(
        default="https://www.treasury.go.ke/budget-policy-statement/",
        description=(
            "National Treasury Budget Policy Statement page. "
            "Scraped to discover the latest BPS PDF."
        ),
    )
    live_pdf_fetch_enabled: bool = Field(
        default=True,
        description=(
            "Whether to attempt live PDF fetching from government websites. "
            "When False, only fixture/configured URLs are used."
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
