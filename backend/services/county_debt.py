"""Explicit county borrowing identities and dated source observations.

No parser guesses an identity from lender/date or arbitrary provenance prose.
The caller owns commit; validation and a savepoint protect unrelated work.
"""
from datetime import date, datetime, timezone
import json
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from sqlalchemy import func, inspect, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import joinedload

from models import (
    CountyDebtInstrument,
    CountyDebtObservation,
    DebtCategory,
    Entity,
    EntityType,
    FigureBasis,
    Loan,
    SourceDocument,
    DocumentStatus,
)


def _identifier(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} requires an explicit nonempty identifier")
    if value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} must be canonical, without control characters")
    return value


def _money(value, precision="0.01"):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Invalid monetary observation")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid monetary observation") from exc
    if not number.is_finite() or number < 0 or number >= Decimal("1e18"):
        raise ValueError("Invalid monetary observation")
    if number != number.quantize(Decimal(precision)):
        raise ValueError("Amounts must be raw currency with at most two decimals")
    return number


def _source_valid(document, entity):
    if document is None or entity is None or document.country_id != entity.country_id:
        return False
    from services.audit_citations import safe_source_url

    return bool(
        safe_source_url(document.url)
        and document.status == DocumentStatus.AVAILABLE
        and isinstance(document.meta, dict)
    )


def _observation_failure(instrument, observation):
    try:
        _identifier(instrument.identity_namespace, "identity_namespace", 120)
        _identifier(instrument.instrument_reference, "instrument_reference", 200)
    except ValueError:
        return "ambiguous_instrument_identity"
    if instrument.entity is None or instrument.entity.type != EntityType.COUNTY:
        return "incompatible_entities"
    if observation is None:
        return "no_observation"
    if not _source_valid(observation.source_document, instrument.entity):
        return "invalid_source_document"
    from services.publication_gate import _has_page_locator

    if not isinstance(observation.page_ref, str) or not _has_page_locator(
        observation.page_ref, allow_descriptive=True
    ):
        return "no_page_reference"
    if not isinstance(observation.provenance, dict):
        return "invalid_metadata"
    if any(
        k in observation.provenance
        for k in (
            "instrument_id",
            "source_instrument_id",
            "loan_reference",
            "as_at",
            "as_of",
        )
    ):
        return "conflicting_observation_metadata"
    if observation.as_at < instrument.issue_date.date():
        return "reporting_date_before_issue"
    return None


def record_county_debt_observation(
    db,
    *,
    entity_id,
    identity_namespace,
    instrument_reference,
    lender,
    issue_date,
    currency,
    as_at,
    source_document_id,
    page_ref,
    basis,
    principal=None,
    outstanding=None,
    interest_rate=None,
    debt_category=DebtCategory.COUNTY_GUARANTEED,
    provenance=None,
    correct=False,
):
    """Idempotent per instrument/date/document; changed same-key facts need correction.

    A different source account is retained as a competing observation. It does
    not silently replace the first account. A later stock date is a new snapshot,
    never another instrument. Changing immutable terms requires reconciliation.
    """
    namespace = _identifier(identity_namespace, "identity_namespace", 120)
    reference = _identifier(instrument_reference, "instrument_reference", 200)
    lender = _identifier(lender, "lender", 200)
    if not isinstance(issue_date, datetime):
        raise ValueError("issue_date must be a datetime")
    # DateTime without timezone has always stored UTC-naive issue dates here.
    # Normalize aware input before comparison so commit/reopen preserves identity.
    if issue_date.tzinfo is not None:
        issue_date = issue_date.astimezone(timezone.utc).replace(tzinfo=None)
    if not isinstance(as_at, date) or isinstance(as_at, datetime):
        raise ValueError("as_at must be a date")
    if as_at < issue_date.date():
        raise ValueError("Reporting date cannot precede issue date")
    if (
        not isinstance(currency, str)
        or len(currency) != 3
        or not currency.isascii()
        or not currency.isalpha()
        or currency != currency.upper()
    ):
        raise ValueError("currency must be an explicit three-letter code")
    if not isinstance(basis, FigureBasis):
        raise ValueError("basis must be explicit")
    if (
        not isinstance(debt_category, DebtCategory)
        or debt_category == DebtCategory.PENDING_BILLS
    ):
        raise ValueError("Pending bills are not borrowing instruments")
    principal, outstanding = _money(principal), _money(outstanding)
    rate = _money(interest_rate, "0.001")
    if rate is not None and (rate >= 1000 or rate != rate.quantize(Decimal("0.001"))):
        raise ValueError("Invalid interest rate")
    page_ref = _identifier(page_ref, "page_ref", 50)
    from services.publication_gate import _has_page_locator

    if not _has_page_locator(page_ref, allow_descriptive=True):
        raise ValueError("A source page locator is required")
    if provenance is not None and not isinstance(provenance, dict):
        raise ValueError("provenance must be a JSON object")
    provenance = dict(provenance or {})
    try:
        json.dumps(provenance, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("provenance must contain finite JSON values") from exc
    if any(
        k in provenance
        for k in (
            "instrument_id",
            "source_instrument_id",
            "loan_reference",
            "as_at",
            "as_of",
        )
    ):
        raise ValueError("Identity and stock date belong in explicit fields")
    if any(
        isinstance(v, bool) or not isinstance(v, int) or v <= 0
        for v in (entity_id, source_document_id)
    ):
        raise ValueError("Entity and document IDs must be positive integer keys")
    entity = db.get(Entity, entity_id)
    document = db.get(SourceDocument, source_document_id)
    if entity is None or entity.type != EntityType.COUNTY:
        raise ValueError("A county entity is required")
    if not _source_valid(document, entity):
        raise ValueError("A compatible source document with a URL is required")
    terms = dict(
        lender=lender,
        issue_date=issue_date,
        currency=currency,
        debt_category=debt_category,
    )
    facts = dict(
        principal=principal,
        outstanding=outstanding,
        interest_rate=rate,
        page_ref=page_ref,
        basis=basis,
        provenance=provenance,
    )
    with db.begin_nested():
        # Unique-key arbitration followed by a row lock serializes repeats and
        # corrections, including two writers racing to create the instrument.
        db.execute(
            insert(CountyDebtInstrument)
            .values(
                entity_id=entity_id,
                identity_namespace=namespace,
                instrument_reference=reference,
                **terms,
            )
            .on_conflict_do_nothing(constraint="uq_county_debt_identity")
        )
        instrument = (
            db.query(CountyDebtInstrument)
            .filter_by(
                entity_id=entity_id,
                identity_namespace=namespace,
                instrument_reference=reference,
            )
            .populate_existing()
            .with_for_update()
            .one()
        )
        if any(getattr(instrument, k) != v for k, v in terms.items()):
            raise ValueError(
                "Conflicting instrument terms; reconcile identity explicitly"
            )
        observation = (
            db.query(CountyDebtObservation)
            .filter_by(
                instrument_id=instrument.id,
                as_at=as_at,
                source_document_id=source_document_id,
            )
            .populate_existing()
            .one_or_none()
        )
        if observation is None:
            observation = CountyDebtObservation(
                instrument_id=instrument.id,
                as_at=as_at,
                source_document_id=source_document_id,
                **facts,
            )
            db.add(observation)
        elif any(getattr(observation, k) != v for k, v in facts.items()):
            if correct is not True:
                raise ValueError("Changed observation requires an explicit correction")
            for k, v in facts.items():
                setattr(observation, k, v)
            observation.revision += 1
        db.flush()
        return observation.id


def _county_instrument_schema_available(db):
    """Resolve both relations on the same search path as the reader.

    Both absent is the supported pre-adoption schema. A partial adoption is
    an error, as are failed catalog queries. One PostgreSQL catalog lookup per
    adapter call avoids table scans and never caches absence across adoption.
    Other SQLAlchemy dialects use their native relation inspection.
    """
    if db.get_bind().dialect.name == "postgresql":
        instruments, observations = db.execute(
            text(
                "SELECT to_regclass('county_debt_instruments') IS NOT NULL, "
                "to_regclass('county_debt_observations') IS NOT NULL"
            )
        ).one()
    else:
        schema = inspect(db.connection())
        instruments = schema.has_table("county_debt_instruments")
        observations = schema.has_table("county_debt_observations")
    if instruments != observations:
        raise RuntimeError(
            "Incomplete county debt schema: both instrument and observation "
            "tables are required; complete the authorized migration"
        )
    return instruments


def county_debt_rows(db, entity_ids):
    """Legacy arrears/loans plus each explicit instrument's latest stock account.

    Latest means latest recorded date, before any publication test: a withheld
    new observation must never resurrect an older publishable balance. All
    competing documents on that date remain visible to the duplicate guard.
    """
    if not entity_ids:
        return []
    instruments_available = _county_instrument_schema_available(db)
    rows = (
        db.query(Loan)
        .options(joinedload(Loan.source_document))
        .filter(Loan.entity_id.in_(entity_ids))
        .all()
    )
    if not instruments_available:
        return rows
    latest = (
        db.query(
            CountyDebtObservation.instrument_id,
            func.max(CountyDebtObservation.as_at).label("as_at"),
        )
        .join(
            CountyDebtInstrument,
            CountyDebtInstrument.id == CountyDebtObservation.instrument_id,
        )
        .filter(CountyDebtInstrument.entity_id.in_(entity_ids))
        .group_by(CountyDebtObservation.instrument_id)
        .subquery()
    )
    pairs = (
        db.query(CountyDebtInstrument, CountyDebtObservation)
        .outerjoin(latest, latest.c.instrument_id == CountyDebtInstrument.id)
        .outerjoin(
            CountyDebtObservation,
            (CountyDebtObservation.instrument_id == CountyDebtInstrument.id)
            & (CountyDebtObservation.as_at == latest.c.as_at),
        )
        .options(
            joinedload(CountyDebtObservation.source_document),
            joinedload(CountyDebtInstrument.entity),
        )
        .filter(CountyDebtInstrument.entity_id.in_(entity_ids))
        .all()
    )
    for instrument, observation in pairs:
        failure = _observation_failure(instrument, observation)
        evidence = (
            dict(observation.provenance)
            if observation and isinstance(observation.provenance, dict)
            else {}
        )
        evidence["as_at"] = observation.as_at.isoformat() if observation else None
        rows.append(
            SimpleNamespace(
                county_instrument=True,
                observation_failure=failure,
                entity_id=instrument.entity_id,
                observation_id=observation.id if observation else None,
                observation_revision=observation.revision if observation else None,
                identity_namespace=instrument.identity_namespace,
                instrument_reference=instrument.instrument_reference,
                lender=instrument.lender,
                issue_date=instrument.issue_date,
                debt_category=instrument.debt_category,
                currency=instrument.currency,
                principal=observation.principal if observation else None,
                outstanding=observation.outstanding if observation else None,
                interest_rate=observation.interest_rate if observation else None,
                basis=observation.basis if observation else None,
                source_document_id=observation.source_document_id
                if observation
                else None,
                source_document=observation.source_document if observation else None,
                page_ref=observation.page_ref if observation else None,
                quarantine_reason=observation.quarantine_reason
                if observation
                else "no_observation",
                provenance=evidence,
            )
        )
    return rows
