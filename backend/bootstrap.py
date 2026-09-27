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
#: count, so a live source would legitimately agree with it and the match
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

    ``BudgetLine``      via ``_upsert_budget_lines``. This one IS superseded in
        practice — the Controller of Budget and Government of Kenya documents
        own all 2,000 county lines and none traces to this file.
    ``Loan``            via ``_upsert_county_debt`` — county debt and pending
        bills, both modelled as fixed percentages of a modelled budget.
    ``PopulationData``  via ``_upsert_population``.
    ``entity.meta``     ``metrics`` (read by /counties for revenue, transfers,
        development budget and pending bills), plus ``economic_profile``,
        ``governor`` and ``last_updated``, which nothing else writes.

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


# --- Typical Kenya county budget sector split (COB averages) ---
# These percentages approximate how county budgets are distributed
# Source: Controller of Budget county reports 2022-2024
COUNTY_BUDGET_SECTORS = [
    # util_bias: sector-specific offset (percentage points) added to the county's
    # base execution rate so that different sectors show varied utilization.
    # Recurrent-heavy sectors (admin, assembly) tend to absorb budget easily;
    # development-heavy sectors (roads, water) typically underspend.
    {
        "category": "Health",
        "development_pct": 0.08,
        "recurrent_pct": 0.17,
        "util_bias": +2,
    },
    {
        "category": "Education & Training",
        "development_pct": 0.04,
        "recurrent_pct": 0.06,
        "util_bias": +1,
    },
    {
        "category": "Roads & Transport",
        "development_pct": 0.10,
        "recurrent_pct": 0.03,
        "util_bias": -6,
    },
    {
        "category": "Agriculture & Livestock",
        "development_pct": 0.05,
        "recurrent_pct": 0.04,
        "util_bias": -4,
    },
    {
        "category": "Water & Sanitation",
        "development_pct": 0.06,
        "recurrent_pct": 0.02,
        "util_bias": -8,
    },
    {
        "category": "Public Administration",
        "development_pct": 0.02,
        "recurrent_pct": 0.18,
        "util_bias": +5,
    },
    {
        "category": "County Assembly",
        "development_pct": 0.01,
        "recurrent_pct": 0.08,
        "util_bias": +7,
    },
    {
        "category": "Trade & Enterprise",
        "development_pct": 0.02,
        "recurrent_pct": 0.01,
        "util_bias": -3,
    },
    {
        "category": "Lands & Urban Planning",
        "development_pct": 0.02,
        "recurrent_pct": 0.01,
        "util_bias": -5,
    },
]
# Remaining ~6% dev + ~1% recurrent = "Other" catch-all


def _upsert_budget_lines(
    session: Session,
    *,
    entity_id: int,
    entity_name: str,
    period_id: int,
    source_document_id: int,
    total_allocated: Decimal,
    execution_rate: Decimal,
    pending_bills: Decimal,
) -> None:
    """Create multiple BudgetLine rows per county — one per sector."""
    import hashlib

    provenance = [
        {
            "source": "bootstrap",
            "dataset": COUNTY_DATA_PATH.name,
            "period": FISCAL_LABEL,
        }
    ]

    # Development is typically ~40% of county budgets, recurrent ~60%
    dev_total = total_allocated * Decimal("0.40")
    rec_total = total_allocated * Decimal("0.60")

    allocated_so_far = Decimal("0")
    for idx, sector in enumerate(COUNTY_BUDGET_SECTORS):
        cat = sector["category"]
        alloc = (
            dev_total * Decimal(str(sector["development_pct"] / 0.40))
            + rec_total * Decimal(str(sector["recurrent_pct"] / 0.60))
        ).quantize(Decimal("0.01"))
        # Scale alloc so dev_pct + rec_pct share of total makes sense
        alloc = (
            total_allocated
            * Decimal(str(sector["development_pct"] + sector["recurrent_pct"]))
        ).quantize(Decimal("0.01"))

        # --- Per-sector utilization variance ---
        # Deterministic jitter in [-3, +3] based on county name + sector index
        seed_bytes = f"{entity_name}:{idx}".encode()
        jitter = (int(hashlib.md5(seed_bytes).hexdigest()[:8], 16) % 7) - 3  # -3..+3
        bias = sector.get("util_bias", 0)
        sector_rate = execution_rate + Decimal(str(bias + jitter))
        # Clamp to [40, 100] so values stay plausible
        sector_rate = max(Decimal("40"), min(Decimal("100"), sector_rate))
        actual = (alloc * sector_rate / Decimal("100")).quantize(Decimal("0.01"))
        committed = (
            (pending_bills * alloc / total_allocated).quantize(Decimal("0.01"))
            if total_allocated > 0
            else Decimal("0")
        )
        allocated_so_far += alloc

        existing = (
            session.query(BudgetLine)
            .filter(
                BudgetLine.entity_id == entity_id,
                BudgetLine.period_id == period_id,
                BudgetLine.category == cat,
            )
            .first()
        )
        if existing:
            existing.allocated_amount = alloc
            existing.actual_spent = actual
            existing.committed_amount = committed
            existing.currency = "KES"
            existing.source_document_id = source_document_id
            existing.provenance = provenance
            session.add(existing)
        else:
            session.add(
                BudgetLine(
                    entity_id=entity_id,
                    period_id=period_id,
                    category=cat,
                    allocated_amount=alloc,
                    actual_spent=actual,
                    committed_amount=committed,
                    currency="KES",
                    source_document_id=source_document_id,
                    provenance=provenance,
                )
            )

    # "Other" catch-all for the remainder
    remainder = total_allocated - allocated_so_far
    if remainder > 0:
        # Give "Other" a slight negative bias + its own jitter
        seed_bytes = f"{entity_name}:other".encode()
        jitter = (int(hashlib.md5(seed_bytes).hexdigest()[:8], 16) % 7) - 3
        other_rate = execution_rate + Decimal(str(-2 + jitter))
        other_rate = max(Decimal("40"), min(Decimal("100"), other_rate))
        actual_rem = (remainder * other_rate / Decimal("100")).quantize(Decimal("0.01"))
        existing = (
            session.query(BudgetLine)
            .filter(
                BudgetLine.entity_id == entity_id,
                BudgetLine.period_id == period_id,
                BudgetLine.category == "Other",
            )
            .first()
        )
        if existing:
            existing.allocated_amount = remainder
            existing.actual_spent = actual_rem
            existing.committed_amount = Decimal("0")
            existing.currency = "KES"
            existing.source_document_id = source_document_id
            existing.provenance = provenance
            session.add(existing)
        else:
            session.add(
                BudgetLine(
                    entity_id=entity_id,
                    period_id=period_id,
                    category="Other",
                    allocated_amount=remainder,
                    actual_spent=actual_rem,
                    committed_amount=Decimal("0"),
                    currency="KES",
                    source_document_id=source_document_id,
                    provenance=provenance,
                )
            )


def _upsert_population(
    session: Session,
    *,
    entity_id: int,
    population: int,
    source_document_id: int,
) -> None:
    """Create PopulationData row for a county (Census 2019 baseline)."""
    if not population or population <= 0:
        return
    existing = (
        session.query(PopulationData)
        .filter(
            PopulationData.entity_id == entity_id,
            PopulationData.year == 2019,
        )
        .first()
    )
    if existing:
        existing.total_population = population
        existing.source_document_id = source_document_id
        session.add(existing)
        return
    session.add(
        PopulationData(
            entity_id=entity_id,
            year=2019,
            total_population=population,
            source_document_id=source_document_id,
            confidence=Decimal("0.95"),
            meta={"source": "Kenya Census 2019", "bootstrap": True},
        )
    )


def _upsert_county_debt(
    session: Session,
    *,
    entity_id: int,
    county_name: str,
    debt_outstanding: float,
    pending_bills: float,
    source_document_id: int,
) -> None:
    """Create Loan rows for county-level debt (outstanding + pending bills)."""
    provenance = [{"source": "bootstrap", "dataset": COUNTY_DATA_PATH.name}]

    if debt_outstanding and debt_outstanding > 0:
        existing = (
            session.query(Loan)
            .filter(
                Loan.entity_id == entity_id,
                Loan.lender == "County Government Debt",
            )
            .first()
        )
        if existing:
            existing.principal = Decimal(str(debt_outstanding))
            existing.outstanding = Decimal(str(debt_outstanding))
            existing.provenance = provenance
            session.add(existing)
        else:
            session.add(
                Loan(
                    entity_id=entity_id,
                    lender="County Government Debt",
                    debt_category=DebtCategory.OTHER,
                    principal=Decimal(str(debt_outstanding)),
                    outstanding=Decimal(str(debt_outstanding)),
                    interest_rate=Decimal("0"),
                    issue_date=FISCAL_START,
                    maturity_date=None,
                    currency="KES",
                    source_document_id=source_document_id,
                    provenance=provenance,
                )
            )

    # THE MODELLED PENDING-BILLS FIGURE IS NOT PUBLISHED AT ALL.
    #
    # It is not a measurement. Every one of the 47 is exactly 8% of a budget
    # that is itself population x KSh 4,500 — the same ratio for the whole
    # country, which is what a formula looks like, not a set of observations.
    #
    # An earlier version of this deferred only where the Treasury BROP had a
    # real figure, so that "a county the parse has not reached keeps the only
    # figure it has". That reasoning was wrong: the figure it kept was a
    # fabrication, and the one county it applied to — Narok — is precisely
    # the county the BROP reports as having submitted nothing. Publishing 8%
    # of a modelled budget for the one county that told the Treasury nothing
    # is the worst case, not the safe one.
    #
    # So nothing is written. Where the BROP has a figure the API serves it;
    # where it does not, county_pending_bills() returns None and the UI shows
    # absence. See services/publication_gate.py.
    if pending_bills and pending_bills > 0:
        logger.info(
            "%s: not writing the modelled pending-bills figure (%.0f) — it is "
            "8%% of a modelled budget, not a published one",
            county_name,
            pending_bills,
        )
        pending_bills = 0.0

    if pending_bills and pending_bills > 0:
        existing = (
            session.query(Loan)
            .filter(
                Loan.entity_id == entity_id,
                Loan.lender == "Pending Bills",
            )
            .first()
        )
        if existing:
            existing.principal = Decimal(str(pending_bills))
            existing.outstanding = Decimal(str(pending_bills))
            existing.provenance = provenance
            session.add(existing)
        else:
            session.add(
                Loan(
                    entity_id=entity_id,
                    lender="Pending Bills",
                    debt_category=DebtCategory.PENDING_BILLS,
                    principal=Decimal(str(pending_bills)),
                    outstanding=Decimal(str(pending_bills)),
                    interest_rate=Decimal("0"),
                    issue_date=FISCAL_START,
                    maturity_date=None,
                    currency="KES",
                    source_document_id=source_document_id,
                    provenance=provenance,
                )
            )


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

NATIONAL_POPULATION = 47_564_296  # Census 2019 (KNBS)


def _seed_economic_indicators(
    session: Session,
    *,
    source_document_id: int,
) -> None:
    """Seed key economic indicators that the /economic/summary endpoint needs."""
    # Source: KNBS Economic Survey 2025 + CBK Monthly Economic Indicators
    indicators = [
        # Inflation rates (KNBS CPI releases)
        {
            "type": "inflation_rate",
            "date": datetime(2024, 12, 31),
            "value": Decimal("6.6"),
            "unit": "percent",
            "source": "KNBS CPI December 2024",
        },
        {
            "type": "inflation_rate",
            "date": datetime(2024, 6, 30),
            "value": Decimal("4.6"),
            "unit": "percent",
            "source": "KNBS CPI June 2024",
        },
        {
            "type": "inflation_rate",
            "date": datetime(2023, 12, 31),
            "value": Decimal("6.6"),
            "unit": "percent",
            "source": "KNBS CPI December 2023",
        },
        {
            "type": "inflation_rate",
            "date": datetime(2023, 6, 30),
            "value": Decimal("7.9"),
            "unit": "percent",
            "source": "KNBS CPI June 2023",
        },
        {
            "type": "inflation_rate",
            "date": datetime(2025, 1, 31),
            "value": Decimal("3.3"),
            "unit": "percent",
            "source": "KNBS CPI January 2025",
        },
        # Unemployment rates (KNBS Labour Force Survey)
        {
            "type": "unemployment_rate",
            "date": datetime(2024, 12, 31),
            "value": Decimal("5.4"),
            "unit": "percent",
            "source": "KNBS QLFS Q4 2024",
        },
        {
            "type": "unemployment_rate",
            "date": datetime(2023, 12, 31),
            "value": Decimal("5.6"),
            "unit": "percent",
            "source": "KNBS QLFS Q4 2023",
        },
        {
            "type": "unemployment_rate",
            "date": datetime(2022, 12, 31),
            "value": Decimal("5.7"),
            "unit": "percent",
            "source": "KNBS QLFS Q4 2022",
        },
        # CPI index values
        {
            "type": "CPI",
            "date": datetime(2025, 1, 31),
            "value": Decimal("143.08"),
            "unit": "index",
            "source": "KNBS Consumer Price Index January 2025",
        },
        {
            "type": "CPI",
            "date": datetime(2024, 12, 31),
            "value": Decimal("142.47"),
            "unit": "index",
            "source": "KNBS Consumer Price Index December 2024",
        },
    ]

    for ind in indicators:
        existing = (
            session.query(EconomicIndicator)
            .filter(
                EconomicIndicator.indicator_type == ind["type"],
                EconomicIndicator.indicator_date == ind["date"],
                EconomicIndicator.entity_id.is_(None),
            )
            .first()
        )
        if existing:
            existing.value = ind["value"]
            existing.unit = ind["unit"]
            existing.source_document_id = source_document_id
            session.add(existing)
        else:
            session.add(
                EconomicIndicator(
                    indicator_type=ind["type"],
                    indicator_date=ind["date"],
                    value=ind["value"],
                    entity_id=None,
                    unit=ind["unit"],
                    source_document_id=source_document_id,
                    confidence=Decimal("0.90"),
                    meta={"source": ind["source"], "bootstrap": True},
                )
            )

    logger.info("Seeded %d economic indicator records", len(indicators))


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
    """Seed Kenya national GDP, population, and sovereign debt into normalised tables."""
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

    # National population
    _upsert_population(
        session,
        entity_id=national_entity.id,
        population=NATIONAL_POPULATION,
        source_document_id=national_doc.id,
    )

    # Also seed a national population record with entity_id=None
    # This is what the /economic/population/latest and /economic/summary endpoints query for
    existing_null_pop = (
        session.query(PopulationData)
        .filter(PopulationData.entity_id.is_(None), PopulationData.year == 2019)
        .first()
    )
    if not existing_null_pop:
        session.add(
            PopulationData(
                entity_id=None,
                year=2019,
                total_population=NATIONAL_POPULATION,
                source_document_id=national_doc.id,
                confidence=Decimal("0.95"),
                meta={
                    "source": "Kenya Census 2019",
                    "bootstrap": True,
                    "scope": "national",
                },
            )
        )
    elif existing_null_pop.total_population != NATIONAL_POPULATION:
        existing_null_pop.total_population = NATIONAL_POPULATION
        existing_null_pop.source_document_id = national_doc.id
        session.add(existing_null_pop)

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

    # Seed economic indicators and poverty indices
    _seed_economic_indicators(session, source_document_id=national_doc.id)
    _seed_poverty_indices(session, source_document_id=national_doc.id)

    logger.info(
        "National-level data seeded (GDP, population, economic indicators, poverty indices). "
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
    national-level seeders (GDP, population, federal audits) are cheap
    and idempotent, so they always run — that way a new data file
    (e.g. federal audit findings) is picked up on restart without
    needing `--force`.
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
            county_code = None
            if code_lookup:
                county_code = code_lookup.get(county_name)
            if not county_code:
                county_code = info.get("county_code")
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
            meta["economic_profile"] = {
                "county_type": info.get("county_type"),
                "economic_base": info.get("economic_base"),
                "infrastructure_level": info.get("infrastructure_level"),
                "revenue_potential": info.get("revenue_potential"),
                "major_issues": info.get("major_issues", []),
            }
            if info.get("governor"):
                meta["governor"] = info["governor"]
            meta["last_updated"] = info.get("last_updated")
            entity.meta = meta
            session.add(entity)
            session.flush()

            last_updated = info.get("last_updated")
            fetch_dt = (
                datetime.fromisoformat(last_updated)
                if isinstance(last_updated, str)
                else datetime.now(timezone.utc)
            )

            budget_doc = _ensure_source_document(
                session,
                country_id=country.id,
                title=f"{county_name} County Budget {FISCAL_LABEL}",
                publisher="County Treasury",
                doc_type=DocumentType.BUDGET,
                fetch_date=fetch_dt,
                metadata={
                    "source": COUNTY_DATA_PATH.name,
                    "county": county_name,
                },
            )

            allocated = _parse_decimal(info.get("budget_2025"))
            execution_rate = _parse_decimal(info.get("budget_execution_rate"))
            committed = _parse_decimal(info.get("pending_bills"))
            _upsert_budget_lines(
                session,
                entity_id=entity.id,
                entity_name=county_name,
                period_id=period.id,
                source_document_id=budget_doc.id,
                total_allocated=allocated,
                execution_rate=execution_rate,
                pending_bills=committed,
            )

            # Seed PopulationData table (Census 2019)
            _upsert_population(
                session,
                entity_id=entity.id,
                population=int(info.get("population", 0)),
                source_document_id=budget_doc.id,
            )

            # Seed Loan table (county debt + pending bills)
            _upsert_county_debt(
                session,
                entity_id=entity.id,
                county_name=county_name,
                debt_outstanding=float(info.get("debt_outstanding", 0)),
                pending_bills=float(info.get("pending_bills", 0)),
                source_document_id=budget_doc.id,
            )

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
                "National-level data refreshed (GDP, population, "
                "federal audits, national budget)"
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
