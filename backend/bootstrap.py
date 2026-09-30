"""Database bootstrap utilities for seeding canonical county data."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from database import SessionLocal
from models import (
    BudgetLine,
    Country,
    DebtCategory,
    DocumentType,
    EconomicIndicator,
    Entity,
    EntityType,
    FiscalPeriod,
    GDPData,
    IngestionJob,
    IngestionStatus,
    Loan,
    PopulationData,
    PovertyIndex,
    SourceDocument,
)
from county_metrics_purge import (  # noqa: F401 - re-exported
    PURGED_META_KEYS,
    PURGED_METRIC_FIELDS,
    purge_modelled_county_metrics,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

FISCAL_LABEL = "FY2025/26"
FISCAL_START = datetime(2025, 7, 1)
FISCAL_END = datetime(2026, 6, 30)
#: A deployment that mounts the reference data somewhere else says so here.
DATA_DIR_ENV_VAR = "BOOTSTRAP_DATA_DIR"

#: Inside the backend package, because that is the only place that ships.
#:
#: This used to be ``Path(__file__).resolve().parent.parent / "apis"`` — true
#: of a git checkout, false of the container. The backend image is built with
#: ``context: ./backend`` and ``COPY . .`` into ``/app``
#: (docker-build-deploy.yml), so ``bootstrap.py`` lands at
#: ``/app/bootstrap.py`` and the old expression resolved to ``/apis``, which
#: nothing has ever written. Anything above this directory is outside the
#: build context and CANNOT be copied in, so the files have to live here.
#:
#: The visible symptom was a false line in the freshness record: every restart
#: of the production web process wrote ``fixture_missing`` / "absent from the
#: repo", of three files that are in the repo. Because that run also stamped
#: the domain's IngestionJob, a no-op overwrote the reason recorded by the
#: weekly job that does have the data.
PACKAGED_DATA_DIR = Path(__file__).resolve().parent / "data" / "reference"


def resolve_data_dir() -> Path:
    """Where the reference fixtures are, honouring the env override."""
    override = os.environ.get(DATA_DIR_ENV_VAR, "").strip()
    return Path(override) if override else PACKAGED_DATA_DIR


DATA_DIR = resolve_data_dir()
COUNTY_DATA_PATH = DATA_DIR / "enhanced_county_data.json"
# `oag_audit_data.json` and `oag_national_audit_data.json` were retired in
# issue #233. Both were hand-written audit fixtures whose findings the Blue Book
# extractor now delivers from the published reports, each with a page. The
# supersession checks that proved it — every county the first named had
# extraction-backed findings, and every row and figure the second could write
# was withheld by the publication gate — passed on a production clone on
# 2026-09-26 before either file was deleted. The API derives what they used to
# supply (services/audit_derived.py).


# ── Provenance for the weekly bootstrap (issue #137 P3) ─────────────
#
# seed.yml runs initialize_reference_data() directly (seed.yml:283-284),
# outside the seeding CLI, so before this it recorded no IngestionJob and
# emitted no freshness mark — check_ingestion_freshness could not see the job
# at all. It re-seeds from three git-tracked files every Sunday, one of them
# nearly a year old.
#
# Age is taken from the DATE THE DATA DECLARES, not the file's mtime. In CI
# `actions/checkout` sets mtime to checkout time, so an mtime-based age would
# report a year-old fixture as fresh — an observability bug inside the
# observability fix.
BOOTSTRAP_DOMAIN = "bootstrap_reference_data"
STALE_AFTER_DAYS = 180

# Where each file states its own date, and what supersedes it if anything.
# `live_source` names the seeding domain that fetches the same facts from the
# publisher; "no_live_source" is a deliberate declaration, not a gap left
# unfilled.
_FIXTURE_DECLARATIONS: Dict[str, Dict[str, Any]] = {
    "enhanced_county_data.json": {
        # This file's own metadata describes its figures as
        # "Official government sources + realistic estimates" with a
        # "Population-based" budget_methodology — i.e. modelled, not
        # published. The UI already discloses that (messages.ts:450).
        "date_field": ("metadata", "extraction_date"),
        "declared_date": "2025-08-24",
        "live_source": "counties_budget",
        "superseded_check": "county_reference_data",
    },
}


# --------------------------------------------------------------------------
# supersession: has the live domain actually delivered?
# --------------------------------------------------------------------------
#
# A fixture's AGE only matters if a reader can still see what is in it. Once
# the live domain named in `live_source` is genuinely producing the same
# facts, the file is vestigial: bootstrap still reads it, but nothing it
# contains reaches an API response, so counting its age as staleness points
# the gate at the wrong file and hides the ones that do still matter.
#
# Two rules keep this from becoming the excuse that stale data hides behind:
#
# 1. Supersession is MEASURED, in the database, at the moment the census
#    runs — never declared in this file. A declaration is exactly the kind of
#    claim that rots silently, which is the failure this whole census exists
#    to catch.
# 2. It has to hold for EVERY published thing the file feeds, not just the
#    obvious one. Partial supersession is not supersession: if any path can
#    still put the file's content in front of a reader, its age still counts.
#
# Every failure path returns False. A check that cannot run — no session, a
# broken query, an unreadable file — leaves the fixture stale, so a fixture
# is never excused by the absence of evidence.


#: The fields ``enhanced_county_data.json`` MODELS rather than reports. Its
#: own metadata calls them "realistic estimates" on a "Population-based"
#: methodology — budget is population x KES 4,500 x an economic factor, debt
#: is a flat 15% of that budget and pending bills a flat 8% (identical ratios
#: for all 47 counties), and every record carries
#: ``"data_source": "realistic_estimate", "needs_verification": true``.
#:
#: A figure derived from a Controller of Budget report would not match one of
#: these to the shilling, so an exact match means the stored figure IS this
#: file's. ``population`` is deliberately excluded: it is a real Census 2019
#: count for most counties, so a live source could agree and the match
#: would prove nothing.
_MODELLED_COUNTY_METRICS = (
    "budget_2025",
    "revenue_2024",
    "debt_outstanding",
    "pending_bills",
    "missing_funds",
)


#: The purge and the field list it works from live in ``services`` so the
#: Alembic revision that clears production can import them without dragging in
#: ``database`` — see that module's docstring. Aliased here under their old
#: private names because this module is where the writer and the census read
#: them, and one definition is the point.
_PURGED_METRIC_FIELDS = PURGED_METRIC_FIELDS
_PURGED_META_KEYS = PURGED_META_KEYS


def _fixture_document_ids(session: Session, filename: str) -> List[int]:
    """Documents ``_ensure_source_document`` minted for ``filename``.

    Scanned in Python rather than with a JSON path operator so the check
    behaves the same on SQLite as on Postgres, and so it cannot silently
    under-count if a publisher or title ever changes — under-counting here
    would push toward calling a fixture superseded, which is the one direction
    that must never happen by accident.
    """
    return [
        doc_id
        for doc_id, meta in session.query(SourceDocument.id, SourceDocument.meta).all()
        if isinstance(meta, dict) and meta.get("source") == filename
    ]


def _county_reference_data_superseded(session: Session) -> Tuple[bool, str]:
    """Is every published claim in ``enhanced_county_data.json`` now derived?

    The `counties_budget` domain named as this file's live source writes
    ``BudgetLine`` rows and nothing else. The file writes four surfaces, so
    three of them have no live path at all today:

    ``BudgetLine``      formerly written here (modelled sector split); no
        longer written — the counties_budget domain owns county budget lines.
    ``Loan``            formerly written here (modelled county debt and
        pending bills); no longer written — pending bills are the pending_bills
        domain's (national: Treasury BROP; counties: CoB year-end CBIRR).
    ``PopulationData``  formerly written here; the population domain owns it.
    ``entity.meta``     ``metrics`` (read by /counties for revenue, transfers,
        development budget and pending bills) from the historical writer.
        Bootstrap now writes only county identifiers and reference timestamps;
        county_officials owns governors, and economic profiles are retired.

    So this returns False until each of those has a live source. The evidence
    names what is still outstanding, which is the actionable form of "377 days
    old".
    """
    try:
        payload = json.loads(COUNTY_DATA_PATH.read_text())
    except Exception as exc:  # noqa: BLE001 - unreadable means unproven
        return False, f"could not read {COUNTY_DATA_PATH.name}: {exc}"

    records = payload.get("county_data") or {}
    if not isinstance(records, dict) or not records:
        return False, f"{COUNTY_DATA_PATH.name} carries no county_data to check"

    outstanding: List[str] = []

    # --- rows still hanging off documents this file minted ---
    doc_ids = _fixture_document_ids(session, COUNTY_DATA_PATH.name)
    if doc_ids:
        for model, label in (
            (BudgetLine, "budget-line"),
            (Loan, "loan"),
            (PopulationData, "population"),
        ):
            rows = (
                session.query(model)
                .filter(model.source_document_id.in_(doc_ids))
                .count()
            )
            if rows:
                counties = (
                    session.query(model.entity_id)
                    .filter(model.source_document_id.in_(doc_ids))
                    .distinct()
                    .count()
                )
                outstanding.append(
                    f"{rows} {label} row(s) across {counties} counties"
                )

    # --- the modelled figures still stored on the entity ---
    still_modelled: List[str] = []
    for name, info in records.items():
        if not isinstance(info, dict):
            continue
        entity = (
            session.query(Entity)
            .filter(Entity.canonical_name == f"{name} County")
            .first()
        )
        if entity is None:
            continue
        stored: Dict[str, Any] = {}
        for by_year in ((entity.meta or {}).get("metrics") or {}).values():
            if isinstance(by_year, dict):
                stored.update(by_year)
        for field in _MODELLED_COUNTY_METRICS:
            if field not in stored or info.get(field) is None:
                continue
            try:
                if Decimal(str(stored[field])) == Decimal(str(info[field])):
                    still_modelled.append(name)
                    break
            except Exception:  # noqa: BLE001 - unparseable is not a match
                continue
    if still_modelled:
        outstanding.append(
            f"entity.meta metrics on {len(still_modelled)} of {len(records)} "
            f"counties still hold this file's modelled figures exactly "
            f"({', '.join(sorted(still_modelled)[:3])}"
            f"{', ...' if len(still_modelled) > 3 else ''})"
        )

    if outstanding:
        # The closing clause names what is left, not a fixed list: county
        # population moved to the 2019 census volume on 2026-09-05 and the
        # sentence that still said otherwise would have been wrong the moment
        # it did.
        return False, (
            f"still served from {COUNTY_DATA_PATH.name}: "
            + "; ".join(outstanding)
        )

    return True, (
        f"no budget-line, loan or population row traces to "
        f"{COUNTY_DATA_PATH.name}, and none of the {len(records)} counties "
        f"still holds its modelled figures"
    )


#: Named so the declaration table stays plain data.
_SUPERSESSION_CHECKS: Dict[str, Callable[[Session], Tuple[bool, str]]] = {
    "county_reference_data": _county_reference_data_superseded,
}


def _supersession(
    spec: Dict[str, Any], session: Optional[Session]
) -> Tuple[bool, Optional[str]]:
    """Whether this fixture is superseded, and the evidence either way."""
    name = spec.get("superseded_check")
    if not name:
        return False, None
    check = _SUPERSESSION_CHECKS.get(name)
    if check is None:  # a declaration naming a check that does not exist
        logger.warning("bootstrap: no supersession check named %r", name)
        return False, f"no check named {name!r} is registered"
    if session is None:
        # The census is also read without a database (tests, tooling). No
        # session means no evidence, and no evidence means still stale.
        return False, "not verified: the census ran without a database session"
    try:
        return check(session)
    except Exception as exc:  # noqa: BLE001 - unproven, so still stale
        logger.warning("bootstrap: supersession check %r failed: %s", name, exc)
        return False, f"check {name!r} could not be completed: {exc}"


def _declared_date(path: Path, spec: Dict[str, Any]) -> str:
    """The date the DATA claims, preferring the file's own metadata."""
    field = spec.get("date_field")
    if field:
        try:
            payload = json.loads(path.read_text())
            for key in field:
                payload = payload[key]
            return str(payload)[:10]
        except Exception:  # noqa: BLE001 - fall back to the declaration
            logger.warning(
                "bootstrap: %s declares no %s; using the recorded date",
                path.name,
                ".".join(field),
            )
    return spec["declared_date"]


def bootstrap_provenance(session: Optional[Session] = None) -> Dict[str, Any]:
    """What the weekly bootstrap read, how old it was, and what still uses it.

    Written into ``IngestionJob.meta`` so the run is visible to the same
    checks that watch the nightly. Returns plain JSON-serialisable types.

    ``session`` lets a fixture be shown SUPERSEDED — its facts now derived by
    the live domain, so nothing in it reaches a reader and its age is no
    longer a staleness signal. Without a session nothing can be verified and
    every fixture stays stale, which is the safe direction.
    """
    files: List[Dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()

    for name, spec in _FIXTURE_DECLARATIONS.items():
        path = DATA_DIR / name
        if not path.exists():
            files.append(
                {
                    "file": name,
                    "present": False,
                    "sha256": None,
                    "bytes": 0,
                    "data_date": None,
                    "age_days": None,
                    "live_source": spec["live_source"],
                    "superseded": False,
                    "supersession_evidence": "the file is absent",
                }
            )
            continue
        raw = path.read_bytes()
        date_str = _declared_date(path, spec)
        try:
            age = (today - datetime.fromisoformat(date_str).date()).days
        except ValueError:
            age = None
        superseded, evidence = _supersession(spec, session)
        files.append(
            {
                "file": name,
                "present": True,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "data_date": date_str,
                "age_days": age,
                "live_source": spec["live_source"],
                # Age still reported for a superseded file — it is read, and
                # a reader of this record should see how old it is — but it no
                # longer counts as staleness.
                "superseded": superseded,
                "supersession_evidence": evidence,
            }
        )

    stale = [
        f["file"]
        for f in files
        if f["age_days"] is not None
        and f["age_days"] > STALE_AFTER_DAYS
        and not f["superseded"]
    ]
    superseded = [f["file"] for f in files if f["superseded"]]
    missing = [f["file"] for f in files if not f["present"]]

    # WHY this run served a fixture, in the key the staleness gate reads
    # (`ingestion_jobs.meta.source_fallback_reason`). Without it the gate
    # reported "reasons: unrecorded" for 26 consecutive runs — it could see
    # that bootstrap had never reached a publisher but not why, which is the
    # one thing needed to act on it.
    #
    # Not "no_live_source": every file here DECLARES a live domain that is
    # supposed to supersede it, so this is a live path that is not working,
    # and it must keep failing the gate rather than being excused as a
    # by-design gap.
    if missing:
        # NOT "absent from the repo": these files are tracked, and saying they
        # were deleted sends the next reader to look for a deletion that never
        # happened. The fault this actually catches is a deployment that did
        # not ship them, so the message names the directory that was searched.
        where = (
            str(DATA_DIR)
            if DATA_DIR.is_dir()
            else f"{DATA_DIR} (no such directory in this deployment)"
        )
        reason = "fixture_missing"
        detail = (
            f"{len(missing)} of {len(files)} fixture(s) not found under "
            f"{where}: {', '.join(missing)}"
        )
    elif stale:
        oldest = max(
            (f for f in files if f["file"] in stale),
            key=lambda f: f["age_days"] or 0,
        )
        reason = "fixture_stale"
        detail = (
            f"{len(stale)} of {len(files)} fixture(s) older than "
            f"{STALE_AFTER_DAYS}d; oldest {oldest['file']} at "
            f"{oldest['age_days']}d, which the '{oldest['live_source']}' "
            f"domain is meant to supersede"
        )
        if superseded:
            # Name what is already done, so the count going down is visible
            # and the remaining files are the ones the message points at.
            detail += (
                f" (not counted: {', '.join(superseded)} — already superseded "
                f"by live data)"
            )
    elif superseded and len(superseded) == len(files):
        # Every fixture read is now vestigial: verified, this run, against the
        # database. bootstrap still reads these files, but nothing in them can
        # reach a reader, so their age is not a staleness signal.
        reason = "fixture_superseded"
        detail = (
            f"all {len(files)} fixture(s) superseded by live data: "
            + "; ".join(
                f"{f['file']} ({f['live_source']}) — {f['supersession_evidence']}"
                for f in files
                if f["superseded"]
            )
        )
    else:
        reason = "fixture_current"
        detail = (
            f"all {len(files)} fixture(s) within {STALE_AFTER_DAYS}d, but "
            f"still read from the repo rather than a publisher"
        )

    return {
        # Declared, not inferred: a run that reads git-tracked JSON must never
        # be indistinguishable from one that fetched from a publisher.
        "source_mode": "fixture",
        "source_fallback_reason": reason,
        "source_fallback_detail": detail,
        "stale_after_days": STALE_AFTER_DAYS,
        # Which directory answered, so a run that found nothing can be told
        # apart from one that read a different copy.
        "data_dir": str(DATA_DIR),
        "files": files,
        "stale_files": stale,
        "superseded_files": superseded,
        "is_stale": bool(stale),
    }


def _parse_decimal(value: Any) -> Decimal:
    """Convert value to Decimal safely."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _ensure_country(session: Session) -> Country:
    """Ensure Kenya country record exists."""
    country = session.query(Country).filter(Country.iso_code == "KEN").first()
    if country:
        return country
    country = Country(
        iso_code="KEN",
        name="Kenya",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en_KE",
        meta={"fiscal_year_start": "07-01"},
    )
    session.add(country)
    session.commit()
    session.refresh(country)
    logger.info("Created base country record for Kenya")
    return country


def _ensure_fiscal_period(session: Session, country_id: int) -> FiscalPeriod:
    """Ensure current fiscal period exists for Kenya."""
    from seeding.utils import normalize_fiscal_label

    canonical = normalize_fiscal_label(FISCAL_LABEL)
    period = (
        session.query(FiscalPeriod)
        .filter(FiscalPeriod.country_id == country_id, FiscalPeriod.label == canonical)
        .first()
    )
    if period:
        return period
    period = FiscalPeriod(
        country_id=country_id,
        label=canonical,
        start_date=FISCAL_START,
        end_date=FISCAL_END,
    )
    session.add(period)
    session.commit()
    session.refresh(period)
    logger.info("Created fiscal period %s", FISCAL_LABEL)
    return period


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        logger.warning("Seed file missing: %s", path)
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return {}


def _ensure_source_document(
    session: Session,
    *,
    country_id: int,
    title: str,
    publisher: str,
    doc_type: DocumentType,
    fetch_date: datetime,
    metadata: Dict[str, Any],
) -> SourceDocument:
    document = (
        session.query(SourceDocument)
        .filter(SourceDocument.country_id == country_id, SourceDocument.title == title)
        .first()
    )
    if document:
        # Refresh metadata if it changed
        document.meta = {**(document.meta or {}), **metadata}
        document.fetch_date = fetch_date
        session.add(document)
        session.flush()
        return document

    document = SourceDocument(
        country_id=country_id,
        publisher=publisher,
        title=title,
        url=metadata.get("url"),
        file_path=metadata.get("file_path"),
        fetch_date=fetch_date,
        md5=metadata.get("md5"),
        doc_type=doc_type,
        meta=metadata,
    )
    session.add(document)
    session.flush()
    return document


# ── National-level (Kenya) GDP ─────────────────────────────────────────
# GDP is loaded from the World Bank-sourced fixture (seeding/real_data/
# national_gdp.json), NOT a hardcoded series. A wrong constant here
# (2025 = 15.4T vs the real ~16-18T) is exactly what previously inflated
# the headline debt-to-GDP ratio to 82%. The live `national_gdp` seeding
# domain overlays current World Bank values nightly. (Sovereign debt
# likewise comes from the seeding pipeline; see national_debt.json.)
def _load_national_gdp_series() -> "list[tuple[int, int]]":
    """Return [(year, nominal_gdp_kes)] from the World Bank-sourced fixture."""
    fixture = (
        Path(__file__).resolve().parent / "seeding" / "real_data" / "national_gdp.json"
    )
    try:
        data = json.loads(fixture.read_text(encoding="utf-8"))
        return [
            (int(r["year"]), int(r["gdp_kes"]))
            for r in data.get("gdp", [])
            if r.get("gdp_kes") is not None
        ]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not load national_gdp.json fixture: %s", exc)
        return []

# NATIONAL_DEBT_BREAKDOWN removed — debt data now comes from the seeding
# pipeline via `python -m seeding.cli seed --domain national_debt`.
# Real data in: backend/seeding/real_data/national_debt.json
# Source: CBK Public Debt Statistical Bulletin, April 2025.


_LEGACY_BOOTSTRAP_INDICATORS = ("inflation_rate", "unemployment_rate", "CPI")


def _seed_economic_indicators(
    session: Session,
    *,
    source_document_id: int,
) -> None:
    """Preserve legacy bootstrap indicators until the source owner replaces them.

    ``inflation_rate`` and ``unemployment_rate`` used to be literals here,
    written on every backend start and every Sunday. The economic_indicators
    domain's World Bank pull writes the same keys at the same ``YYYY-12-31``
    dates, so each writer overwrote the other — and this one was wrong:
    ``inflation_rate`` 2024-12-31 = 6.6 is December **2023**'s figure (CBK
    gives Dec 2024 as 12-month 2.99, annual average 4.50). The update path
    also changed ``value`` without ``meta``, leaving a bootstrap number under
    World Bank provenance (issue #232). A live domain owns those keys now;
    bootstrap writes none of them. Legacy rows must remain until the live
    writer can replace a matching year-end row or retire an off-cycle row
    with source coverage and an identity receipt. Startup has neither.

    The dedicated economic_indicators domain also owns CPI. The former CPI
    literals used a combined national debt/GDP source document, which could
    not establish the CPI release or measurement basis. Bootstrap therefore
    neither creates nor updates any economic indicator, including CPI. Its
    existing rows remain for source-backed reconciliation. The domain
    normalizes indicator names, so legacy uppercase ``CPI`` rows require an
    explicit identity and measure review before retirement.
    """
    legacy = [
        row.id
        for row in session.query(EconomicIndicator)
        .filter(
            EconomicIndicator.indicator_type.in_(_LEGACY_BOOTSTRAP_INDICATORS),
            EconomicIndicator.entity_id.is_(None),
        )
        .all()
        if isinstance(row.meta, dict) and row.meta.get("bootstrap") is True
    ]
    if legacy:
        logger.warning(
            "Preserved %d legacy bootstrap economic-indicator rows pending "
            "source reconciliation; row IDs: %s",
            len(legacy),
            sorted(legacy)[:10],
        )

    logger.info("Economic indicator writes delegated to economic_indicators domain")


def _seed_poverty_indices(
    session: Session,
    *,
    source_document_id: int,
) -> None:
    """Placeholder — NULL entity_id poverty rows are now handled by the seeding
    pipeline's ``national_gdp`` domain.  This function is kept as a no-op so
    callers don't need to be updated."""
    # NOTE: The actual poverty index data (World Bank, KNBS KIHBS) is seeded by
    # seeding.domains.national_gdp which uses raw SQL inserts that reliably
    # persist NULL entity_id rows in Supabase.
    logger.info("Poverty index seeding delegated to national_gdp seeding domain")


def _seed_national_data(
    session: Session,
    *,
    country: Country,
    period: FiscalPeriod,
) -> None:
    """Seed national reference data while preserving legacy economic indicators."""
    # Ensure a national-level Entity exists
    national_entity = (
        session.query(Entity)
        .filter(
            Entity.country_id == country.id,
            Entity.type == EntityType.NATIONAL,
        )
        .first()
    )
    if not national_entity:
        national_entity = Entity(
            country_id=country.id,
            type=EntityType.NATIONAL,
            canonical_name="Republic of Kenya",
            slug="republic-of-kenya",
            alt_names=["Kenya", "GOK"],
            meta={},
        )
        session.add(national_entity)
        session.flush()  # get ID

    # Source document for national data
    national_doc = _ensure_source_document(
        session,
        country_id=country.id,
        title="CBK Public Debt Report & KNBS Economic Survey 2025",
        publisher="Central Bank of Kenya / National Treasury",
        doc_type=DocumentType.LOAN,
        fetch_date=datetime(2025, 4, 30),
        metadata={
            "source": "bootstrap",
            "scope": "national",
            "cbk_csv_latest": "Apr 2025",
        },
    )

    # GDP series — clean up orphan rows from other entities (but NOT NULL rows,
    # which are intentional national-level records for /economic/summary)
    orphan_gdp = (
        session.query(GDPData)
        .filter(
            GDPData.entity_id != national_entity.id,
            GDPData.entity_id.isnot(None),
        )
        .all()
    )
    for orphan in orphan_gdp:
        session.delete(orphan)
    if orphan_gdp:
        logger.info(f"Deleted {len(orphan_gdp)} orphan GDP rows")

    gdp_series = _load_national_gdp_series()
    for year, gdp_val in gdp_series:
        existing = (
            session.query(GDPData)
            .filter(GDPData.entity_id == national_entity.id, GDPData.year == year)
            .first()
        )
        if existing:
            existing.gdp_value = Decimal(str(gdp_val))
            session.add(existing)
        else:
            session.add(
                GDPData(
                    entity_id=national_entity.id,
                    year=year,
                    gdp_value=Decimal(str(gdp_val)),
                    source_document_id=national_doc.id,
                    confidence=Decimal("0.95"),
                    meta={
                        "source": "World Bank NY.GDP.MKTP.CN (fixture)",
                        "bootstrap": True,
                    },
                )
            )

    # Reconcile to the authoritative series: prune national-entity GDP rows for
    # any year BEYOND the latest fixture year. Without this, a stale/fabricated
    # FUTURE year left by an earlier seed (e.g. 2025 = 15.4T from the old
    # hardcoded NATIONAL_GDP_SERIES) survives forever and — being the newest
    # year — out-ranks the real latest World Bank value in every
    # `order_by(year.desc())` lookup, re-inflating the debt-to-GDP/GDP headline
    # the fix was meant to correct. We prune ``year > max`` (not "not in set")
    # so a shorter fixture can never delete legitimate earlier history. Guarded
    # by a non-empty series.
    fixture_years = [year for year, _ in gdp_series]
    if fixture_years:
        latest_fixture_year = max(fixture_years)
        stale_gdp = (
            session.query(GDPData)
            .filter(
                GDPData.entity_id == national_entity.id,
                GDPData.year > latest_fixture_year,
            )
            .all()
        )
        for row in stale_gdp:
            session.delete(row)
        if stale_gdp:
            logger.info(
                "Pruned %d stale national GDP year(s) beyond latest fixture "
                "year %d: %s",
                len(stale_gdp),
                latest_fixture_year,
                sorted(r.year for r in stale_gdp),
            )

    # NOTE: NULL entity_id GDP rows (for /economic/summary) are handled by the
    # seeding pipeline's "national_gdp" domain, not here.  Bootstrap only manages
    # the entity-linked rows above.
    session.flush()

    # National and county population are owned by the population domain.

    # National debt breakdown is now handled by the seeding pipeline:
    #   python -m seeding.cli seed --domain national_debt
    # Bootstrap no longer writes loan records to avoid conflicts.
    # Clean up any stale bootstrap category-summary rows that may linger
    # from earlier versions of this code.
    stale_bootstrap_loans = [
        loan
        for loan in session.query(Loan)
        .filter(Loan.entity_id == national_entity.id)
        .all()
        if any(
            isinstance(p, dict) and p.get("source") == "bootstrap"
            for p in (loan.provenance or [])
        )
    ]
    if stale_bootstrap_loans:
        for loan in stale_bootstrap_loans:
            session.delete(loan)
        logger.info(
            f"Deleted {len(stale_bootstrap_loans)} stale bootstrap loan rows "
            f"(debt data now comes from seeding pipeline)"
        )

    # Preserve legacy economic indicators; the dedicated domain owns new writes.
    _seed_economic_indicators(session, source_document_id=national_doc.id)
    _seed_poverty_indices(session, source_document_id=national_doc.id)

    logger.info(
        "National-level data seeded (GDP); economic indicators use the dedicated domain. "
        "Run 'python -m seeding.cli seed --domain national_debt' for debt records."
    )


def _seed_national_budget(session: Session) -> None:
    """Seed national-government BudgetLine rows from the CoB NG-BIRR fixture.

    Delegates to the national_budget seeding domain so bootstrap stays
    aligned with the canonical pipeline. Uses the local fixture
    (live_pdf_fetch_enabled=False) to keep restart time bounded; the
    CLI entrypoint (`python -m seeding.cli seed --domain national_budget`)
    is still the right tool when a fresh live fetch is wanted.

    Idempotent — the domain writer matches on
    (entity_id, period_id, category, subcategory), so repeat calls are no-ops
    when the fixture hasn't changed.
    """
    try:
        from seeding.config import SeedingSettings
        from seeding.domains.national_budget import run as _run
        from seeding.types import DomainRunContext
    except ImportError as exc:  # seeding package missing — safe to skip
        logger.warning("national_budget seed skipped (import failed): %s", exc)
        return

    try:
        settings = SeedingSettings(live_pdf_fetch_enabled=False)
        context = DomainRunContext(since=None, dry_run=False, job_id=None)
        result = _run(session=session, settings=settings, context=context)
        if result.errors:
            logger.warning(
                "national_budget seed completed with errors: %s", result.errors
            )
        logger.info(
            "National budget execution seeded (processed=%d, created=%d, updated=%d)",
            result.items_processed,
            result.items_created,
            result.items_updated,
        )
    except Exception as exc:  # don't crash startup on seeder hiccups
        logger.warning("national_budget seed skipped: %s", exc)


#: How long a RUNNING ingestion row is taken at its word. The seeding CLI's own
#: ceiling is SEED_TOTAL_TIMEOUT_SECONDS (1320s = 22 min in seed.yml), so an
#: hour is comfortably past any healthy run. Beyond it the row is assumed to be
#: the debris of a crashed run: a process that died mid-domain leaves RUNNING
#: behind forever, and honouring that would wedge every future boot into a
#: no-op — trading a timeout for a silent, permanent one.
DEFER_TO_SEED_WITHIN_MINUTES = 60


def _seed_run_in_flight(session: Session) -> Optional[str]:
    """The domain of a seeding run currently writing, if there is one.

    Bootstrap and the nightly both write ``audits``. When they overlap, one
    blocks on the other's row locks until the database's statement timeout
    fires — see ``test_bootstrap_defers_to_a_live_seed`` for the run this comes
    from. Bootstrap is the side that yields: its input is a git-tracked file
    that will still be there in twenty minutes, while the seed run is fetching
    from publishers on a clock it cannot restart.

    ``BOOTSTRAP_DOMAIN`` is excluded deliberately. Two web processes starting
    together would otherwise each see the other's RUNNING row and both defer,
    turning a race into a guaranteed no-op.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=DEFER_TO_SEED_WITHIN_MINUTES
    )
    row = (
        session.query(IngestionJob)
        .filter(
            IngestionJob.status == IngestionStatus.RUNNING,
            IngestionJob.domain != BOOTSTRAP_DOMAIN,
            IngestionJob.started_at >= cutoff.replace(tzinfo=None),
        )
        .order_by(IngestionJob.started_at.desc())
        .first()
    )
    return row.domain if row else None


def initialize_reference_data(
    code_lookup: Optional[Dict[str, str]] = None, *, force: bool = False
) -> None:
    """Seed canonical county + audit data into the database if missing.

    The per-county loop is the expensive part (~3 min on a cold DB); once
    47 county entities exist it's skipped on subsequent boots. The
    national-level reference seeders are cheap
    and idempotent, so they always run without needing `--force`.
    """
    # Yield to a seed run that is already writing. Nothing here is urgent —
    # these are git-tracked files — and the alternative is a row-lock wait that
    # ends in the database's statement timeout, which costs three things at
    # once: a FAILED ingestion row that the nightly's 30-minute results window
    # counts as its own domain failure, a web process that never reaches
    # `_app_ready`, and no bootstrap either way.
    #
    # No IngestionJob is recorded: this run did not happen, and a fixture-mode
    # row saying otherwise would be read by check_ingestion_freshness as a
    # bootstrap that served a fixture.
    if not force:
        probe = SessionLocal()
        try:
            busy = _seed_run_in_flight(probe)
        except Exception:  # noqa: BLE001 - a probe must never be the failure
            busy = None
        finally:
            probe.close()
        if busy:
            logger.warning(
                "bootstrap: deferring — the '%s' seeding domain is writing "
                "now, and both write `audits`. The weekly bootstrap job owns "
                "this refresh; nothing here is time-critical.",
                busy,
            )
            return

    # Fast-path check — skip the expensive county loop only. National
    # seeders further down still run so newly added data files get picked
    # up even when the county entities are already in place.
    skip_county_loop = False
    if not force:
        quick_session = SessionLocal()
        try:
            county_count = (
                quick_session.query(Entity)
                .filter(Entity.type == EntityType.COUNTY)
                .count()
            )
            if county_count >= 47:
                logger.info(
                    "County data present (%d counties) — skipping county loop; "
                    "still refreshing national-level data",
                    county_count,
                )
                skip_county_loop = True
        except Exception:
            pass  # table might not exist yet; fall through to full seed
        finally:
            quick_session.close()

    county_records: Dict[str, Any] = {}

    if not skip_county_loop:
        county_payload = _load_json(COUNTY_DATA_PATH)
        county_records = county_payload.get("county_data", {})
        if not county_records:
            logger.warning("No county data available for seeding")


    started_at = datetime.now(timezone.utc)
    session = SessionLocal()
    try:
        country = _ensure_country(session)
        period = _ensure_fiscal_period(session, country.id)

        for county_name, info in county_records.items():
            from services.county_identity import official_county_code

            county_code = official_county_code(county_name)
            if county_code is None:
                raise ValueError(f"Unrecognized county identity: {county_name!r}")
            canonical_name = f"{county_name} County"
            entity = (
                session.query(Entity)
                .filter(
                    Entity.country_id == country.id,
                    Entity.canonical_name == canonical_name,
                )
                .first()
            )
            if not entity:
                slug_base = county_name.lower().replace(" ", "-").replace("'", "")
                slug_suffix = (county_code or "").lower()
                slug = f"{slug_base}-{slug_suffix}".strip("-")
                entity = Entity(
                    country_id=country.id,
                    type=EntityType.COUNTY,
                    canonical_name=canonical_name,
                    slug=slug,
                    alt_names=[county_name],
                    meta={},
                )

            meta = dict(entity.meta or {})
            from seeding.utils import normalize_fiscal_label as _nlbl

            _fy_key = _nlbl(FISCAL_LABEL)
            # One key: the county's code. This used to store thirteen more —
            # budget_2025, revenue_2024, debt_outstanding, pending_bills,
            # missing_funds, population, four ratios, a health score, an audit
            # letter grade — and a second copy of seven of them under
            # `financial_metrics`. Every one was modelled here (budget is
            # population x KSh 4,500; debt is 15% of that; pending bills 8%;
            # the "rates" are the same constant for 40 counties), and every
            # one now has a publisher behind it or is withheld for having
            # none. See _PURGED_METRIC_FIELDS for the field-by-field map, and
            # purge_modelled_county_metrics for the databases that still hold
            # what this loop wrote before today.
            #
            # `county_code` stays because it is an identifier rather than a
            # claim, and /search and the entity listing read it from here.
            metrics = dict((meta.get("metrics") or {}).get(_fy_key, {}))
            metrics = {
                k: v for k, v in metrics.items() if k not in _PURGED_METRIC_FIELDS
            }
            metrics["county_code"] = county_code

            meta.setdefault("metrics", {})[_fy_key] = metrics
            for _stale in _PURGED_META_KEYS:
                meta.pop(_stale, None)
            # Officials belong to county_officials; retired economic profiles
            # are removed only by the separately reviewed cleanup.
            meta["last_updated"] = info.get("last_updated")
            entity.meta = meta
            session.add(entity)
            session.flush()

            # Population and county money are ingested by their sourced domains.

        # --- National-level data (GDP + sovereign debt) ---
        _seed_national_data(session, country=country, period=period)

        # --- National-government budget execution (CoB NG-BIRR) ---
        _seed_national_budget(session)

        # Record the run so the freshness checks can see it (issue #137 P3).
        # Before this the weekly job was invisible: no IngestionJob, no
        # freshness mark, so a fixture could freeze for a year — and one had —
        # while every gate stayed green because none of them was looking.
        provenance = bootstrap_provenance(session)
        session.add(
            IngestionJob(
                domain=BOOTSTRAP_DOMAIN,
                status=IngestionStatus.COMPLETED,
                dry_run=False,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                meta=provenance,
            )
        )
        session.commit()

        if provenance["is_stale"]:
            logger.warning(
                "bootstrap: re-seeded from fixture(s) older than %d days: %s",
                STALE_AFTER_DAYS,
                ", ".join(
                    f"{f['file']} ({f['age_days']}d)"
                    for f in provenance["files"]
                    if f["file"] in provenance["stale_files"]
                ),
            )

        if skip_county_loop:
            logger.info(
                "National-level data refreshed (GDP, "
                "economic indicators, national budget)"
            )
        else:
            logger.info(
                "Reference county data initialized (%d counties)",
                len(county_records),
            )
    except Exception as exc:
        session.rollback()
        logger.error("Failed to initialize reference data: %s", exc)
        # The failure must be visible too — a job row that only appears on
        # success makes an outage look like a run that never happened.
        try:
            session.add(
                IngestionJob(
                    domain=BOOTSTRAP_DOMAIN,
                    status=IngestionStatus.FAILED,
                    dry_run=False,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    errors=[str(exc)[:2000]],
                    meta={
                        "source_mode": "fixture",
                        "source_fallback_reason": "bootstrap_failed",
                        "source_fallback_detail": (
                            f"{type(exc).__name__}: {str(exc)[:300]}"
                        ),
                    },
                )
            )
            session.commit()
        except Exception:  # noqa: BLE001 - never mask the original failure
            session.rollback()
            logger.exception("bootstrap: could not record the failed job row")
        raise
    finally:
        session.close()
