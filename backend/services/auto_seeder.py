"""Lightweight web-worker refreshes and county reference creation.

Debt, economics, population, officials and heavy document ingestion belong to
the dedicated seeding runner. Its source-owning writers must not compete with
web startup or periodic refreshes.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from database import SessionLocal
from models import (
    Country,
    Entity,
    EntityType,
)

# Import the live data fetcher
from services.live_data_fetcher import LiveDataAggregator

logger = logging.getLogger("auto_seeder")

# Request-serving workers own only these lightweight refreshes. PDF registry
# jobs (population, audits, counties_budget, pending_bills, stalled_projects)
# belong to the dedicated seed.yml runner with its bounded CLI budgets.
# A thread or coroutine timeout cannot bound a parser's memory in this process.
# Refresh schedule configuration (hours between refreshes)
REFRESH_SCHEDULE = {
    "counties": 168,  # Weekly - County reference refresh
}

# Kenya's 47 counties - Official codes (ISO 3166-2:KE)
# This is reference data, not fetched data - counties don't change
KENYA_COUNTY_CODES = {
    "001": "Mombasa",
    "002": "Kwale",
    "003": "Kilifi",
    "004": "Tana River",
    "005": "Lamu",
    "006": "Taita Taveta",
    "007": "Garissa",
    "008": "Wajir",
    "009": "Mandera",
    "010": "Marsabit",
    "011": "Isiolo",
    "012": "Meru",
    "013": "Tharaka Nithi",
    "014": "Embu",
    "015": "Kitui",
    "016": "Machakos",
    "017": "Makueni",
    "018": "Nyandarua",
    "019": "Nyeri",
    "020": "Kirinyaga",
    "021": "Murang'a",
    "022": "Kiambu",
    "023": "Turkana",
    "024": "West Pokot",
    "025": "Samburu",
    "026": "Trans Nzoia",
    "027": "Uasin Gishu",
    "028": "Elgeyo Marakwet",
    "029": "Nandi",
    "030": "Baringo",
    "031": "Laikipia",
    "032": "Nakuru",
    "033": "Narok",
    "034": "Kajiado",
    "035": "Kericho",
    "036": "Bomet",
    "037": "Kakamega",
    "038": "Vihiga",
    "039": "Bungoma",
    "040": "Busia",
    "041": "Siaya",
    "042": "Kisumu",
    "043": "Homa Bay",
    "044": "Migori",
    "045": "Kisii",
    "046": "Nyamira",
    "047": "Nairobi",
}


class AutoSeeder:
    """Schedule the web worker's lightweight reference refreshes."""

    # Reference domains attempted at boot; a failed scheduled domain remains
    # due for retry on the next periodic tick.
    _BOOT_DOMAINS: tuple = (
        "counties",
        "national_entity",
    )

    def __init__(self):
        self.last_refresh: Dict[str, datetime] = {}
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.aggregator = LiveDataAggregator()
        self._fetch_stats = {
            "total_fetches": 0,
            "successful_fetches": 0,
            "failed_fetches": 0,
            "last_full_refresh": None,
        }
        # Consecutive failures per domain — a domain that keeps failing
        # means its data is silently going stale (this is exactly how the
        # county audit-status gap went unnoticed), so we alert loudly
        # after _ALERT_AFTER_FAILURES in a row.
        self._consecutive_failures: Dict[str, int] = {}

    async def start(self):
        """Start the auto-seeder background task."""
        if self.is_running:
            logger.warning("Auto-seeder already running")
            return

        self.is_running = True
        logger.info("[AUTO-SEEDER] Starting web reference refresh scheduler")

        # Run initial seed in background so it doesn't block uvicorn startup.
        # The server can start serving requests immediately using bootstrap data.
        self._task = asyncio.create_task(self._initial_seed_and_loop())
        logger.info("[AUTO-SEEDER] Background seed + refresh loop started")

    async def _initial_seed_and_loop(self):
        """Run initial seed then start the periodic refresh loop."""
        try:
            await self.seed_all_domains()
        except Exception as exc:
            logger.warning(f"[AUTO-SEEDER] Initial seed failed (non-critical): {exc}")

        await self._refresh_loop()

    # Alert after this many consecutive failures of one domain — transient
    # scrape hiccups are normal; silent multi-day gaps are not.
    _ALERT_AFTER_FAILURES = 3

    def _record_domain_success(self, domain: str) -> None:
        self._consecutive_failures.pop(domain, None)
        self._fetch_stats["successful_fetches"] += 1

    def _record_domain_failure(self, domain: str, exc: Exception) -> None:
        count = self._consecutive_failures.get(domain, 0) + 1
        self._consecutive_failures[domain] = count
        logger.error(f"Failed to refresh {domain} ({count} consecutive): {exc}")
        self._fetch_stats["failed_fetches"] += 1
        if count == self._ALERT_AFTER_FAILURES:
            # One loud alert per failure streak (== not >=, so it doesn't
            # re-fire every tick). CRITICAL log always lands; Sentry is
            # best-effort (no-op when the SDK/DSN isn't configured).
            logger.critical(
                f"[AUTO-SEEDER] Domain '{domain}' has failed {count} refreshes in a row — "
                f"its data is going stale silently. Last error: {exc}"
            )
            try:
                import sentry_sdk

                sentry_sdk.capture_message(
                    f"[AUTO-SEEDER] '{domain}' failed {count} consecutive refreshes: {exc}",
                    level="error",
                )
            except Exception:
                pass

    async def stop(self):
        """Stop the auto-seeder background task."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[AUTO-SEEDER] Service stopped")

    async def _refresh_loop(self):
        """Background loop that checks and refreshes stale data."""
        while self.is_running:
            try:
                # Check every hour
                await asyncio.sleep(3600)
                await self._check_and_refresh()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in refresh loop: {e}")
                # Wait before retrying on error
                await asyncio.sleep(60)

    async def _check_and_refresh(self):
        """Check which domains need refresh and update them."""
        now = datetime.now(timezone.utc)
        logger.info("[AUTO-SEEDER] Checking for stale data...")
        refreshed = False
        failed = False

        for domain, refresh_hours in REFRESH_SCHEDULE.items():
            last = self.last_refresh.get(domain)

            if last is None or (now - last).total_seconds() > refresh_hours * 3600:
                logger.info(
                    f"[AUTO-SEEDER] Refreshing {domain} (stale or never fetched)..."
                )

                try:
                    await self._seed_domain(domain)
                    self.last_refresh[domain] = now
                    self._record_domain_success(domain)
                    refreshed = True
                except Exception as e:
                    self._record_domain_failure(domain, e)
                    failed = True

                self._fetch_stats["total_fetches"] += 1

                # Rate limiting between domain refreshes
                await asyncio.sleep(5)

        # An idle check or failed refresh cannot certify completed work.
        if refreshed and not failed:
            self._fetch_stats["last_full_refresh"] = now.isoformat()

    async def seed_all_domains(self):
        """Run the web worker's registered reference refreshes."""
        logger.info("[AUTO-SEEDER] === WEB REFERENCE REFRESH ===")

        # Order matters: entities first, then data that references them.
        # Sourced from the class attribute so _initial_seed_and_loop and
        # this method stay in sync — drift between the two is what
        # caused the hourly OOM cycle in the first place.
        for domain in self._BOOT_DOMAINS:
            try:
                logger.info(f"[AUTO-SEEDER] Processing domain: {domain}")
                await self._seed_domain(domain)
                self.last_refresh[domain] = datetime.now(timezone.utc)
                self._record_domain_success(domain)
            except Exception as e:
                self._record_domain_failure(domain, e)

            self._fetch_stats["total_fetches"] += 1
            await asyncio.sleep(2)  # Rate limiting

        logger.info("[AUTO-SEEDER] === WEB REFERENCE REFRESH COMPLETE ===")
        logger.info(f"[AUTO-SEEDER] Stats: {self._fetch_stats}")

    async def _seed_domain(self, domain: str):
        """Dispatch a web-owned reference domain or refuse an external one."""
        if domain == "counties":
            await self._seed_counties_live()
        elif domain == "national_entity":
            await self._ensure_national_entity()
        elif domain == "debt":
            await self._seed_debt_live()
        else:
            raise ValueError(f"{domain} is owned by the dedicated seeding runner")

    async def _seed_registry_domain(self, domain_name: str):
        """Refuse even direct calls: heavy jobs must never share the web worker."""
        raise ValueError(f"{domain_name} is owned by the dedicated seeding runner")

    async def _seed_counties_live(self):
        """
        Seed county entities with live data from KNBS/COB.

        County codes are static (they don't change), but population
        and budget data comes from live sources.
        """
        logger.info("[AUTO-SEEDER] Seeding counties...")

        # Try to fetch live county data, but don't block if it fails
        try:
            # Set a timeout for the fetch to avoid blocking startup
            knbs_counties, cob_budgets = await asyncio.wait_for(
                self.aggregator.fetch_all_county_data(),
                timeout=30.0,  # 30 second timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[AUTO-SEEDER] County data fetch timed out, using empty data"
            )
            knbs_counties, cob_budgets = [], []
        except Exception as e:
            logger.warning(
                f"[AUTO-SEEDER] County data fetch failed: {e}, using empty data"
            )
            knbs_counties, cob_budgets = [], []  # Create lookup for live data
        live_population = {}
        live_budgets = {}

        for county in knbs_counties:
            name = county.get("name", "").lower()
            live_population[name] = county.get("population")

        for budget in cob_budgets:
            name = budget.get("county", "").lower()
            live_budgets[name] = budget.get("budget")

        with SessionLocal() as db:
            # Required even when references already exist: a foreign namesake
            # cannot certify that Kenyan reference work completed.
            kenya = db.query(Country).filter(Country.iso_code == "KEN").first()
            if kenya is None:
                raise ValueError("Kenya country (KEN) is required for county references")

            counties_created = 0
            counties_updated = 0

            for code, name in KENYA_COUNTY_CODES.items():
                name_lower = name.lower()

                # Get live data if available
                population = live_population.get(name_lower)
                budget = live_budgets.get(name_lower)

                # Check if county entity exists
                canonical = f"{name} County"
                existing = (
                    db.query(Entity)
                    .filter(
                        Entity.country_id == kenya.id,
                        Entity.type == EntityType.COUNTY,
                        Entity.canonical_name == canonical,
                    )
                    .first()
                )

                # Build metadata with whatever live data we have
                county_meta = {
                    "code": code,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "data_source": (
                        "live_fetch" if population or budget else "pending_live_data"
                    ),
                }

                if population:
                    county_meta["population"] = population
                if budget:
                    county_meta["budget"] = budget

                if existing:
                    # Update existing entity
                    if existing.meta:
                        existing.meta.update(county_meta)
                    else:
                        existing.meta = county_meta
                    existing.canonical_name = canonical
                    counties_updated += 1
                else:
                    slug = name.lower().replace(" ", "-").replace("'", "") + "-" + code
                    county_entity = Entity(
                        country_id=kenya.id,
                        canonical_name=canonical,
                        type=EntityType.COUNTY,
                        slug=slug,
                        alt_names=[name, canonical],
                        meta=county_meta,
                    )
                    db.add(county_entity)
                    counties_created += 1

            db.commit()
            logger.info(
                f"[AUTO-SEEDER] Counties: {counties_created} created, {counties_updated} updated"
            )

    async def _ensure_national_entity(self):
        """Ensure national government entity exists."""
        with SessionLocal() as db:
            kenya = db.query(Country).filter(Country.iso_code == "KEN").first()
            if kenya is None:
                raise ValueError("Kenya country (KEN) is required for national reference")

            existing = (
                db.query(Entity)
                .filter(
                    Entity.country_id == kenya.id,
                    Entity.type == EntityType.NATIONAL,
                )
                .first()
            )

            if not existing:
                national = Entity(
                    country_id=kenya.id,
                    canonical_name="Republic of Kenya",
                    type=EntityType.NATIONAL,
                    slug="republic-of-kenya",
                    alt_names=["Kenya", "Republic of Kenya", "Government of Kenya"],
                    meta={"created_at": datetime.now(timezone.utc).isoformat()},
                )
                db.add(national)
                db.commit()
                logger.info("[AUTO-SEEDER] Created National Government entity")
            else:
                logger.info("[AUTO-SEEDER] National Government entity exists")

    async def _seed_debt_live(self):
        """Refuse legacy callers; dedicated debt domains own sourced writes."""
        raise ValueError(
            "national_debt and debt_timeline are owned by the dedicated seeding runner"
        )

    async def _seed_population_live(self):
        """Refuse legacy direct callers before fetching or touching the database."""
        raise ValueError("population is owned by the dedicated seeding runner")

    async def _seed_economic_live(self):
        """Refuse legacy direct calls before fetch or database access."""
        raise ValueError("economic indicators are owned by the dedicated seeding runner")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the auto-seeder."""
        return {
            "is_running": self.is_running,
            "last_refresh": {k: v.isoformat() for k, v in self.last_refresh.items()},
            "fetch_stats": self._fetch_stats,
            # Domains currently in a failure streak (cleared on success) —
            # non-empty means data is going stale; ≥3 has already alerted.
            "consecutive_failures": dict(self._consecutive_failures),
            "next_refresh": self._get_next_refresh_times(),
            "external_job_owner": {
                "domains": [
                    "audits",
                    "counties_budget",
                    "debt_timeline",
                    "economic_indicators",
                    "national_debt",
                    "pending_bills",
                    "stalled_projects",
                ],
                "runner": ".github/workflows/seed.yml (seeding.cli)",
                "job_health": "not_checked_here",
            },
        }

    def _get_next_refresh_times(self) -> Dict[str, str]:
        """Calculate when each domain will next refresh."""
        now = datetime.now(timezone.utc)
        next_times = {}

        for domain, hours in REFRESH_SCHEDULE.items():
            last = self.last_refresh.get(domain)
            if last:
                next_refresh = last.replace(tzinfo=timezone.utc) + timedelta(
                    hours=hours
                )
                if next_refresh > now:
                    next_times[domain] = next_refresh.isoformat()
                else:
                    next_times[domain] = "Due now"
            else:
                next_times[domain] = "Never run"

        return next_times


# Global instance
auto_seeder = AutoSeeder()


async def start_auto_seeder():
    """Start the auto-seeder service."""
    await auto_seeder.start()


async def stop_auto_seeder():
    """Stop the auto-seeder service."""
    await auto_seeder.stop()


def get_seeder_status() -> Dict[str, Any]:
    """Get the current status of the auto-seeder."""
    return auto_seeder.get_status()
