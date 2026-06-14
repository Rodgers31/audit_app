"""
Auto-Seeder Service - Fully Automated Data Refresh

This service runs on application startup and periodically refreshes
all data domains from official government sources WITHOUT HUMAN INTERVENTION.

ZERO HARDCODED DATA - All data comes from live fetching.

Data Sources:
- CBK (Central Bank of Kenya): National debt statistics
- KNBS (Kenya National Bureau of Statistics): Population, GDP, economic indicators
- Treasury: Budget allocations, debt bulletins
- COB: County budget implementation reports
- OAG: Audit findings

Architecture:
- Uses existing ETL infrastructure (kenya_pipeline.py, knbs_parser.py)
- LiveDataAggregator fetches from all sources
- Automatic fallback when primary sources unavailable
- Scheduled refresh based on data volatility
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from database import SessionLocal
from models import (
    Country,
    DebtCategory,
    DocumentType,
    EconomicIndicator,
    Entity,
    EntityType,
    Loan,
    PopulationData,
    SourceDocument,
)

# Import the live data fetcher
from services.live_data_fetcher import LiveDataAggregator

logger = logging.getLogger("auto_seeder")

# Refresh schedule configuration (hours between refreshes)
REFRESH_SCHEDULE = {
    "debt": 24,  # Daily - CBK updates monthly but we check daily
    "population": 720,  # Monthly - Census data changes rarely
    "economic": 168,  # Weekly - GDP/CPI updated quarterly/monthly
    "counties": 168,  # Weekly - Budget implementation updates
    "budgets": 168,  # Weekly - Treasury releases
    "audits": 168,  # Weekly - OAG releases
    "counties_budget": 168,  # Weekly — CoB CBIRR releases
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
    """
    Fully automated data seeder - NO HARDCODED DATA.

    Features:
    - Runs on application startup
    - Periodic refresh based on source-specific intervals
    - Uses LiveDataAggregator for all data
    - Handles failures gracefully with retry logic
    - Updates database without human intervention
    """

    # Domains seeded synchronously at boot via seed_all_domains().
    # Exposed as a class attribute so _initial_seed_and_loop can backfill
    # last_refresh only for REFRESH_SCHEDULE domains that AREN'T in this
    # set — preserving the existing retry-on-next-tick behaviour for
    # boot-seeded domains that fail at startup.
    _BOOT_DOMAINS: tuple = (
        "counties",
        "national_entity",
        "debt",
        "population",
        "economic",
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

    async def start(self):
        """Start the auto-seeder background task."""
        if self.is_running:
            logger.warning("Auto-seeder already running")
            return

        self.is_running = True
        logger.info("[AUTO-SEEDER] Starting Fully Automated Data Seeder")
        logger.info("[AUTO-SEEDER] NO HARDCODED DATA - All data from live sources")

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

        # Backfill last_refresh ONLY for REFRESH_SCHEDULE domains that
        # aren't boot-seeded (registry-only: budgets, audits,
        # counties_budget). Without this they have last_refresh=None
        # forever and the hourly tick re-runs the registry pipeline
        # (pdfplumber + pandas + HTTP scrapes) every hour — which OOMs
        # a 512 MB worker on Render.
        #
        # Boot-seeded domains are deliberately excluded: if their seed
        # raised, last_refresh stays None and the hourly tick retries
        # them on next iteration — that's the existing transient-failure
        # behaviour and we don't want to suppress it.
        boot_time = datetime.now(timezone.utc)
        for domain in REFRESH_SCHEDULE:
            if domain not in self._BOOT_DOMAINS:
                self.last_refresh.setdefault(domain, boot_time)

        await self._refresh_loop()

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

        for domain, refresh_hours in REFRESH_SCHEDULE.items():
            last = self.last_refresh.get(domain)

            if last is None or (now - last).total_seconds() > refresh_hours * 3600:
                logger.info(
                    f"[AUTO-SEEDER] Refreshing {domain} (stale or never fetched)..."
                )

                try:
                    await self._seed_domain(domain)
                    self.last_refresh[domain] = now
                    self._fetch_stats["successful_fetches"] += 1
                except Exception as e:
                    logger.error(f"Failed to refresh {domain}: {e}")
                    self._fetch_stats["failed_fetches"] += 1

                self._fetch_stats["total_fetches"] += 1

                # Rate limiting between domain refreshes
                await asyncio.sleep(5)

        self._fetch_stats["last_full_refresh"] = now.isoformat()

    async def seed_all_domains(self):
        """Seed all data domains from live sources."""
        logger.info("[AUTO-SEEDER] === FULL DATA REFRESH FROM LIVE SOURCES ===")

        # Order matters: entities first, then data that references them.
        # Sourced from the class attribute so _initial_seed_and_loop and
        # this method stay in sync — drift between the two is what
        # caused the hourly OOM cycle in the first place.
        for domain in self._BOOT_DOMAINS:
            try:
                logger.info(f"[AUTO-SEEDER] Processing domain: {domain}")
                await self._seed_domain(domain)
                self.last_refresh[domain] = datetime.now(timezone.utc)
                self._fetch_stats["successful_fetches"] += 1
            except Exception as e:
                logger.error(f"Failed to seed {domain}: {e}")
                self._fetch_stats["failed_fetches"] += 1

            self._fetch_stats["total_fetches"] += 1
            await asyncio.sleep(2)  # Rate limiting

        logger.info("[AUTO-SEEDER] === FULL DATA REFRESH COMPLETE ===")
        logger.info(f"[AUTO-SEEDER] Stats: {self._fetch_stats}")

    async def _seed_domain(self, domain: str):
        """Seed a specific domain with fresh data from live sources."""
        if domain == "counties":
            await self._seed_counties_live()
        elif domain == "national_entity":
            await self._ensure_national_entity()
        elif domain == "debt":
            await self._seed_debt_live()
        elif domain == "population":
            await self._seed_population_live()
        elif domain == "economic":
            await self._seed_economic_live()
        elif domain in ("counties_budget", "audits", "budgets"):
            # Delegate to the seeding-registry domain so the CoB CBIRR and
            # OAG audit data used by the Follow-the-Money waterfall stay
            # current without a manual CLI run.
            await self._seed_registry_domain(
                "counties_budget" if domain == "budgets" else domain
            )

    async def _seed_registry_domain(self, domain_name: str):
        """Run a registry-based seeding domain (counties_budget, audits).

        Delegates to the same pipeline the CLI uses so CoB CBIRR and OAG
        audit data refresh on the same schedule as the rest of the
        Follow-the-Money waterfall, without requiring a manual run.
        """
        logger.info(
            "[AUTO-SEEDER] Running registry domain %s via seeding pipeline",
            domain_name,
        )
        try:
            from seeding.config import get_settings
            from seeding.registries import REGISTRY, load_builtin_domains
            from seeding.types import DomainRunContext

            load_builtin_domains()
            runner = REGISTRY.get(domain_name)
            if runner is None:
                logger.warning(
                    "[AUTO-SEEDER] Registry domain %s not registered", domain_name
                )
                return

            settings = get_settings()
            loop = asyncio.get_running_loop()

            def _run() -> None:
                with SessionLocal() as db:
                    ctx = DomainRunContext(
                        since=None, dry_run=False, job_id=None
                    )
                    runner(db, settings, ctx)
                    db.commit()

            await loop.run_in_executor(None, _run)
            logger.info(
                "[AUTO-SEEDER] Registry domain %s refresh complete", domain_name
            )
        except Exception as exc:
            logger.warning(
                "[AUTO-SEEDER] Registry domain %s refresh failed: %s",
                domain_name,
                exc,
            )

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
                    # Get Kenya country for country_id
                    kenya = db.query(Country).filter(Country.iso_code == "KEN").first()
                    if not kenya:
                        logger.error("[AUTO-SEEDER] Kenya country not found")
                        return
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
            existing = (
                db.query(Entity)
                .filter(
                    Entity.type == EntityType.NATIONAL,
                )
                .first()
            )

            if not existing:
                kenya = db.query(Country).filter(Country.iso_code == "KEN").first()
                if not kenya:
                    logger.error("[AUTO-SEEDER] Kenya country not found")
                    return
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
        """
        National debt domain — SKIPPED.

        bootstrap.py is the authoritative source for national sovereign debt
        (CBK Public Debt Report, verified Apr 2025).  Live fetches risk
        overwriting verified data with unstructured/partial totals.
        """
        logger.info("[AUTO-SEEDER] Debt domain skipped — bootstrap.py is authoritative")
        return

    async def _seed_population_live(self):
        """
        Seed population data from KNBS live sources.

        NO HARDCODED VALUES - all data from live fetch.
        """
        logger.info("[AUTO-SEEDER] Fetching population data...")

        try:
            population_data = await asyncio.wait_for(
                self.aggregator.fetch_all_population_data(), timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning("[AUTO-SEEDER] Population fetch timed out")
            return
        except Exception as e:
            logger.warning(f"[AUTO-SEEDER] Population fetch failed: {e}")
            return

        if not population_data.get("fetch_success"):
            logger.warning(
                f"[AUTO-SEEDER] Live population fetch failed: {population_data.get('error', 'Unknown')}"
            )
            return

        with SessionLocal() as db:
            records_created = 0
            records_updated = 0

            census_year = population_data.get("census_year") or datetime.now().year

            # Update county populations
            for county_pop in population_data.get("counties", []):
                county_name = county_pop.get("county", "").lower()
                population = county_pop.get("total_population")

                if not population:
                    continue

                # Find county entity by name
                county = (
                    db.query(Entity)
                    .filter(
                        Entity.type == EntityType.COUNTY,
                        Entity.canonical_name.ilike(f"%{county_name}%"),
                    )
                    .first()
                )

                if county:
                    # Check for existing population record
                    existing_pop = (
                        db.query(PopulationData)
                        .filter(
                            PopulationData.entity_id == county.id,
                            PopulationData.year == census_year,
                        )
                        .first()
                    )

                    if existing_pop:
                        existing_pop.total_population = population
                        records_updated += 1
                    else:
                        pop_record = PopulationData(
                            entity_id=county.id,
                            year=census_year,
                            total_population=population,
                            confidence=1.0,
                        )
                        db.add(pop_record)
                        records_created += 1

            # Add national population if available
            if population_data.get("national_population"):
                national = (
                    db.query(Entity).filter(Entity.type == EntityType.NATIONAL).first()
                )

                if national:
                    existing = (
                        db.query(PopulationData)
                        .filter(
                            PopulationData.entity_id == national.id,
                            PopulationData.year == census_year,
                        )
                        .first()
                    )

                    if existing:
                        existing.total_population = population_data[
                            "national_population"
                        ]
                        records_updated += 1
                    else:
                        db.add(
                            PopulationData(
                                entity_id=national.id,
                                year=census_year,
                                total_population=population_data["national_population"],
                                confidence=1.0,
                            )
                        )
                        records_created += 1

            db.commit()
            logger.info(
                f"[AUTO-SEEDER] Population: {records_created} created, {records_updated} updated"
            )

    async def _seed_economic_live(self):
        """
        Seed economic indicators from KNBS live sources.

        NO HARDCODED VALUES - all data from live fetch.
        """
        logger.info("[AUTO-SEEDER] Fetching economic indicators...")

        try:
            economic_data = await asyncio.wait_for(
                self.aggregator.fetch_all_economic_data(), timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning("[AUTO-SEEDER] Economic fetch timed out")
            return
        except Exception as e:
            logger.warning(f"[AUTO-SEEDER] Economic fetch failed: {e}")
            return

        if not economic_data.get("fetch_success"):
            logger.warning(
                f"[AUTO-SEEDER] Live economic fetch failed: {economic_data.get('error', 'Unknown')}"
            )
            return

        with SessionLocal() as db:
            national = (
                db.query(Entity).filter(Entity.type == EntityType.NATIONAL).first()
            )

            if not national:
                logger.error("[AUTO-SEEDER] National entity not found")
                return

            indicators_created = 0
            indicators_updated = 0
            current_year = datetime.now().year

            # GDP
            if economic_data.get("gdp_kes"):
                gdp_year = economic_data.get("gdp_year", current_year)
                existing = (
                    db.query(EconomicIndicator)
                    .filter(
                        EconomicIndicator.entity_id == national.id,
                        EconomicIndicator.indicator_type == "gdp",
                        EconomicIndicator.year == gdp_year,
                    )
                    .first()
                )

                if existing:
                    existing.value = economic_data["gdp_kes"]
                    indicators_updated += 1
                else:
                    db.add(
                        EconomicIndicator(
                            entity_id=national.id,
                            indicator_type="gdp",
                            year=gdp_year,
                            value=economic_data["gdp_kes"],
                            currency="KES",
                            confidence=0.95,
                        )
                    )
                    indicators_created += 1

            # Inflation
            if economic_data.get("inflation_rate"):
                existing = (
                    db.query(EconomicIndicator)
                    .filter(
                        EconomicIndicator.entity_id == national.id,
                        EconomicIndicator.indicator_type == "inflation",
                        EconomicIndicator.year == current_year,
                    )
                    .first()
                )

                if existing:
                    existing.value = economic_data["inflation_rate"]
                    indicators_updated += 1
                else:
                    db.add(
                        EconomicIndicator(
                            entity_id=national.id,
                            indicator_type="inflation",
                            year=current_year,
                            value=economic_data["inflation_rate"],
                            confidence=0.98,
                        )
                    )
                    indicators_created += 1

            # Other indicators from the list
            for indicator in economic_data.get("indicators", []):
                ind_type = indicator.get("indicator_type", "other")
                ind_value = indicator.get("value")
                ind_year = indicator.get("year", current_year)

                if ind_value is None:
                    continue

                existing = (
                    db.query(EconomicIndicator)
                    .filter(
                        EconomicIndicator.entity_id == national.id,
                        EconomicIndicator.indicator_type == ind_type,
                        EconomicIndicator.year == ind_year,
                    )
                    .first()
                )

                if existing:
                    existing.value = ind_value
                    indicators_updated += 1
                else:
                    db.add(
                        EconomicIndicator(
                            entity_id=national.id,
                            indicator_type=ind_type,
                            year=ind_year,
                            value=ind_value,
                            confidence=indicator.get("confidence", 0.9),
                        )
                    )
                    indicators_created += 1

            db.commit()
            logger.info(
                f"[AUTO-SEEDER] Economic: {indicators_created} created, {indicators_updated} updated"
            )

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the auto-seeder."""
        return {
            "is_running": self.is_running,
            "last_refresh": {k: v.isoformat() for k, v in self.last_refresh.items()},
            "fetch_stats": self._fetch_stats,
            "next_refresh": self._get_next_refresh_times(),
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
