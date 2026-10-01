"""National GDP and Poverty Index seeding domain.

Seeds national-level (entity_id=NULL) GDP and poverty index records that the
/economic/summary endpoint relies on.  These complement the entity-linked GDP
rows created by bootstrap (entity_id = national entity ID).

Data sources:
  GDP — Kenya National Bureau of Statistics (KNBS) Economic Survey 2025
  Poverty — World Bank Kenya Economic Update 2024 & KNBS KIHBS
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from models import (
    Country,
    DocumentType,
    GDPData,
    PovertyIndex,
    SourceDocument,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...http_client import create_http_client
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import fetcher

logger = logging.getLogger("seeding.national_gdp")

# GDP is fetched live from the World Bank (NY.GDP.MKTP.CN), with an in-repo
# World Bank-sourced fixture as the last-known-good fallback. There is
# intentionally NO hardcoded GDP series here: a wrong/low GDP constant
# (previously 2025 = 15.4T vs the real ~16-18T) is exactly what inflated
# the headline debt-to-GDP ratio to 82%. See national_gdp/fetcher.py and
# seeding/real_data/national_gdp.json.

# POVERTY_SERIES was removed here (issue #137 P7). It held nine figures as a
# Python constant, inserted at confidence 0.85. The 2019 row was the World
# Bank's 2015 observation exactly (36.1 / 0.408) relabelled; the 2021 row
# republished that same 36.1 under a label naming "KNBS KIHBS 2021", whose
# actual observation is 38.6; and the World Bank reports nothing at all for
# 2019 or 2024. Poverty now comes from fetcher.fetch_kenya_poverty(), which
# writes only years the World Bank actually observes.

def _kenya_country(session: Session) -> Country:
    """Refuse absent or conflicting Kenya identity; never borrow another row.

    KEN is the bootstrap identity. KE is the ISO alpha-2 spelling used by
    older callers. Both are explicit Kenya identities, but two such rows are
    ambiguous. A Kenya name with another code is a conflict, not a fallback.
    """
    countries = session.scalars(
        select(Country).where(
            or_(
                func.upper(func.trim(Country.iso_code)).in_(("KEN", "KE")),
                func.lower(func.trim(Country.name)) == "kenya",
            )
        )
    ).all()
    if len(countries) != 1:
        raise ValueError("Kenya source identity requires exactly one Kenya country")
    country = countries[0]
    if (
        country.iso_code not in ("KEN", "KE")
        or country.name.strip().casefold() != "kenya"
        or country.currency != "KES"
    ):
        raise ValueError("Kenya source identity has conflicting country code, name or currency")
    return country


def _matching_source_document(
    session: Session, *, url: str, publisher: str, title: str, metadata: dict,
    measures: tuple[str, ...], units: tuple[str, ...], datasets: tuple[str, ...],
) -> tuple[Country, SourceDocument | None]:
    """Validate the writer's source contract without repairing shared rows.

    Extra metadata (including publication vintage) is preserved. Missing or
    contradictory required identity is a refusal, even at the same URL.
    This checks stored identity, not the authenticity of publisher bytes.
    """
    country = _kenya_country(session)
    docs = session.scalars(select(SourceDocument).where(SourceDocument.url == url)).all()
    if len(docs) > 1:
        raise ValueError(f"Kenya source identity is ambiguous for {url}")
    doc = docs[0] if docs else None
    if doc is not None:
        # Optional declarations are evidence too: a matching URL/indicator
        # cannot override a country, publisher or measure conflict. Absent
        # optional fields stay absent; no metadata is filled in during reuse.
        declarations = {
            "country": ("Kenya", "KEN", "KE"),
            "country_code": ("KEN", "KE"),
            "iso_code": ("KEN", "KE"),
            "country_id": (country.id,),
            "currency": ("KES",),
            "publisher": (publisher,),
            "source": (publisher, title),
            "scope": ("national",),
            "entity_id": (None,),
            "measure": measures,
            "units": units,
            "dataset_id": datasets,
        }
        if (
            doc.country_id != country.id
            or doc.publisher != publisher
            or doc.title != title
            or doc.doc_type != DocumentType.REPORT
            or not isinstance(doc.meta, dict)
            or any(doc.meta.get(key) != value for key, value in metadata.items())
            or ("indicator" in doc.meta and doc.meta["indicator"] != metadata.get("indicator"))
            or ("indicators" in doc.meta and doc.meta["indicators"] != metadata.get("indicators"))
            or any(
                key in doc.meta
                and (
                    isinstance(doc.meta[key], bool)
                    or (key == "country_id" and not isinstance(doc.meta[key], int))
                    or doc.meta[key] not in allowed
                )
                for key, allowed in declarations.items()
            )
        ):
            raise ValueError(f"Kenya source identity conflicts with existing document {doc.id} at {url}")
    return country, doc


def _ensure_gdp_source_document(session: Session) -> SourceDocument:
    """Get or create the World Bank source document for national GDP."""
    url = "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN"
    title = "World Bank — Kenya GDP, current LCU (NY.GDP.MKTP.CN)"
    metadata = {"seeding_domain": "national_gdp", "indicator": "NY.GDP.MKTP.CN"}
    country, doc = _matching_source_document(
        session, url=url, publisher="World Bank", title=title, metadata=metadata,
        measures=("GDP, current KES", "GDP, current LCU"),
        units=("KES", "LCU"), datasets=("NY.GDP.MKTP.CN",),
    )
    if doc is None:
        doc = SourceDocument(
            country_id=country.id,
            publisher="World Bank",
            title=title,
            url=url,
            file_path=None,
            fetch_date=datetime.now(timezone.utc),
            doc_type=DocumentType.REPORT,
            md5=None,
            meta=metadata,
        )
        session.add(doc)
        session.flush()
    return doc


def _ensure_poverty_source_document(session: Session) -> SourceDocument:
    """The document poverty rows cite.

    Previously every row cited one generic document —
    ``https://www.knbs.or.ke/economic-survey-2025/``, titled "KNBS Economic
    Survey 2025 & World Bank Poverty Data" — while the rows' own metadata
    named three DIFFERENT publications: "KNBS KIHBS 2021", "KNBS KIHBS
    2015/16 (adjusted for 2019 Census)" and "World Bank Kenya Economic Update
    2024". A citation that resolves to a document the figure did not come from
    is worse than a missing one: it looks checkable.

    This document names the two indicators the figures are actually read from,
    so following the citation reaches the numbers.
    """
    url = "https://api.worldbank.org/v2/country/KEN/indicator/SI.POV.NAHC"
    title = (
        "World Bank — Kenya poverty headcount at national poverty "
        "lines (SI.POV.NAHC) and Gini index (SI.POV.GINI)"
    )
    metadata = {
        "seeding_domain": "national_gdp", "indicators": ["SI.POV.NAHC", "SI.POV.GINI"]
    }
    country, doc = _matching_source_document(
        session, url=url, publisher="World Bank", title=title, metadata=metadata,
        measures=("Poverty headcount at national poverty lines and Gini index",),
        units=("percent and Gini 0-1",), datasets=("SI.POV.NAHC", "SI.POV.GINI"),
    )
    if doc is None:
        doc = SourceDocument(
            country_id=country.id,
            publisher="World Bank",
            title=title,
            url=url,
            file_path=None,
            fetch_date=datetime.now(timezone.utc),
            doc_type=DocumentType.REPORT,
            md5=None,
            meta=metadata,
        )
        session.add(doc)
        session.flush()
    return doc


def _ensure_source_document(session: Session) -> SourceDocument:
    """Get or create the source document for national poverty data."""
    url = "https://www.knbs.or.ke/economic-survey-2025/"
    title = "KNBS Economic Survey 2025 & World Bank Poverty Data"
    metadata = {"seeding_domain": "national_gdp"}
    country, doc = _matching_source_document(
        session, url=url, publisher="KNBS / World Bank", title=title, metadata=metadata,
        measures=("Poverty headcount at national poverty lines and Gini index",),
        units=("percent and Gini 0-1",), datasets=(),
    )
    if doc is None:
        doc = SourceDocument(
            country_id=country.id,
            publisher="KNBS / World Bank",
            title=title,
            url=url,
            file_path=None,
            fetch_date=datetime.now(timezone.utc),
            doc_type=DocumentType.REPORT,
            md5=None,
            meta=metadata,
        )
        session.add(doc)
        session.flush()
    return doc


@register_domain("national_gdp")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    created = 0
    updated = 0
    errors: list[str] = []

    gdp_years = 0
    poverty_by_year: dict = {}
    savepoint = None
    try:
        # The caller owns the outer transaction (including its ingestion job).
        # A later poverty source refusal must also undo this run's GDP writes.
        savepoint = session.begin_nested()
        gdp_doc = _ensure_gdp_source_document(session)

        # ── GDP records (entity_id=NULL) — fetched from the World Bank ─
        # Live World Bank NY.GDP.MKTP.CN, with the World Bank-sourced
        # fixture as the last-known-good fallback. On total fetch failure
        # we keep whatever GDP rows already exist — never overwrite real
        # data with a guess, never inject a hardcoded estimate.
        try:
            with create_http_client(settings) as client:
                gdp_by_year = fetcher.fetch_national_gdp_kes(client, settings)
        except Exception as exc:
            logger.warning(
                "national_gdp: GDP fetch failed (%s); keeping existing rows", exc
            )
            gdp_by_year = {}
            errors.append(f"GDP fetch failed: {exc}")

        gdp_years = len(gdp_by_year)
        # Record the data vintage (latest covered year) on the source doc so
        # downstream endpoints can report an honest "as of", not the request
        # time. See backend/provenance.py.
        if gdp_by_year and isinstance(gdp_doc.meta, dict):
            latest_gdp_year = max(gdp_by_year)
            gdp_doc.meta = {
                **gdp_doc.meta,
                "publication_date": f"{latest_gdp_year}-12-31",
                "covers_through_year": latest_gdp_year,
            }
            session.add(gdp_doc)
        for year, gdp_kes in sorted(gdp_by_year.items()):
            value = Decimal(str(gdp_kes))
            existing = (
                session.query(GDPData)
                .filter(GDPData.entity_id.is_(None), GDPData.year == year)
                .first()
            )
            if existing is None:
                session.execute(
                    GDPData.__table__.insert().values(
                        entity_id=None,
                        year=year,
                        gdp_value=value,
                        source_document_id=gdp_doc.id,
                        confidence=Decimal("0.95"),
                        currency="KES",
                        metadata={
                            "source": "World Bank NY.GDP.MKTP.CN",
                            "seeding_domain": "national_gdp",
                            "scope": "national",
                            "data_quality": "official",
                        },
                    )
                )
                created += 1
                logger.info("Created NULL-entity GDP row for %d", year)
            elif existing.gdp_value != value:
                existing.gdp_value = value
                existing.source_document_id = gdp_doc.id
                session.add(existing)
                updated += 1

        # Reconcile to the World Bank series: prune NULL-entity GDP rows for
        # any year BEYOND the latest authoritative actual. This removes a
        # stale/fabricated FUTURE row — e.g. a leftover 2025 = 15.4T from the
        # old hardcoded series — that would otherwise be the newest year and
        # out-rank the real latest GDP in `order_by(year.desc())` lookups
        # (/economic/summary, /learn/civic-figures), re-introducing the very
        # debt-to-GDP overstatement the GDP fix removed.
        #
        # We prune by ``year > latest_source_year`` rather than "not in the
        # fetched set" on purpose: the live World Bank series spans 1960-2024,
        # but a degraded fetch may fall back to the smaller in-repo fixture
        # (2018-2024). A "not in set" rule would then delete decades of
        # legitimate WB history on a transient outage; "beyond latest actual"
        # only ever removes fabricated future projections. In-range years are
        # corrected by the upsert above. Guarded by a non-empty fetch.
        if gdp_by_year:
            latest_source_year = max(gdp_by_year)
            stale_gdp = (
                session.query(GDPData)
                .filter(
                    GDPData.entity_id.is_(None),
                    GDPData.year > latest_source_year,
                )
                .all()
            )
            for row in stale_gdp:
                session.delete(row)
            if stale_gdp:
                logger.info(
                    "Pruned %d stale NULL-entity GDP year(s) beyond latest "
                    "actual %d: %s",
                    len(stale_gdp),
                    latest_source_year,
                    sorted(r.year for r in stale_gdp),
                )

        # ── Poverty index records with entity_id=NULL ────────────────
        # Live World Bank, replacing the POVERTY_SERIES constant. A failed
        # fetch keeps existing rows and prunes nothing — the same
        # last-known-good rule the GDP path above follows.
        try:
            with create_http_client(settings) as client:
                poverty_by_year = fetcher.fetch_kenya_poverty(client, settings)
        except Exception as exc:
            logger.warning(
                "national_gdp: poverty fetch failed (%s); keeping existing rows",
                exc,
            )
            poverty_by_year = {}

        poverty_doc = _ensure_poverty_source_document(session) if poverty_by_year else None

        for year, values in poverty_by_year.items():
            existing = (
                session.query(PovertyIndex)
                .filter(
                    PovertyIndex.entity_id.is_(None),
                    PovertyIndex.year == year,
                )
                .first()
            )
            # extreme_poverty_rate is deliberately NULL — see
            # fetcher.EXTREME_POVERTY_OMITTED_REASON.
            meta = {
                "source": "World Bank (SI.POV.NAHC, SI.POV.GINI)",
                "seeding_domain": "national_gdp",
                "extreme_poverty_rate_absent_reason": (
                    fetcher.EXTREME_POVERTY_OMITTED_REASON
                ),
                "gini_scale": "0-1 (World Bank reports 0-100; divided by 100)",
            }
            if existing is None:
                session.execute(
                    PovertyIndex.__table__.insert().values(
                        entity_id=None,
                        year=year,
                        poverty_headcount_rate=values.get("headcount"),
                        extreme_poverty_rate=None,
                        gini_coefficient=values.get("gini"),
                        source_document_id=poverty_doc.id,
                        confidence=Decimal("0.95"),
                        metadata=meta,
                    )
                )
                created += 1
                logger.info("Created poverty index row for %d", year)
            else:
                changed = False
                if existing.poverty_headcount_rate != values.get("headcount"):
                    existing.poverty_headcount_rate = values.get("headcount")
                    changed = True
                if existing.extreme_poverty_rate is not None:
                    existing.extreme_poverty_rate = None
                    changed = True
                if existing.gini_coefficient != values.get("gini"):
                    existing.gini_coefficient = values.get("gini")
                    changed = True
                if changed:
                    existing.source_document_id = poverty_doc.id
                    existing.confidence = Decimal("0.95")
                    existing.meta = meta
                    session.add(existing)
                    updated += 1

        # Prune NULL-entity poverty years the source does not report. This is
        # the half that matters: 2019 and 2024 exist in production with no
        # World Bank observation behind them, and an upsert alone would leave
        # them there forever. Guarded by a non-empty fetch so a failed request
        # never deletes real rows — the exact guard the GDP prune above uses.
        if poverty_by_year:
            unsourced = (
                session.query(PovertyIndex)
                .filter(
                    PovertyIndex.entity_id.is_(None),
                    PovertyIndex.year.notin_(list(poverty_by_year)),
                )
                .all()
            )
            for row in unsourced:
                session.delete(row)
            if unsourced:
                logger.info(
                    "Pruned %d poverty year(s) with no World Bank observation: %s",
                    len(unsourced),
                    sorted(r.year for r in unsourced),
                )

        savepoint.commit()

    except Exception as exc:
        if savepoint is not None:
            savepoint.rollback()
        created = updated = 0
        logger.exception("national_gdp seeding failed: %s", exc)
        errors.append(str(exc))

    processed = gdp_years + len(poverty_by_year)
    logger.info(
        "national_gdp complete: %d created, %d updated, %d processed",
        created,
        updated,
        processed,
    )

    return DomainRunResult(
        domain="national_gdp",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        items_processed=processed,
        items_created=created,
        items_updated=updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata={},
    )


__all__ = ["run"]
