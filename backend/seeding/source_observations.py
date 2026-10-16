"""Read committed CoB facts for the version-one generated-draft evidence seam.

No parser, source acquisition, event creation or publication runs here. Callers
provide a fresh session factory, never the writer's active transaction. Missing
qualifications are unavailable capabilities, not successful empty observations.
"""
from datetime import date, datetime
from decimal import Decimal
import re
from urllib.parse import urlsplit

from sqlalchemy import func, select, text

from models import BudgetLine, DocumentStatus, Entity, Extraction, IngestionJob, IngestionStatus, SourceDocument
from services.entity_financials import budget_line_is_unreported
from services.figure_qualification import qualify_rows


class SourceObservationUnavailable(ValueError):
    """Fixed diagnostic safe to surface in an authenticated operator response."""


def _positive_id(value):
    if type(value) is not int or not 0 < value <= 2147483647:
        raise SourceObservationUnavailable("Positive bounded record and ingestion IDs required")


def _aware(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (ValueError, TypeError):
        raise SourceObservationUnavailable("Stored evidence timestamps unavailable") from None


def _read_limits(db):
    # pg_settings.setting is milliseconds for both settings. Keep a stricter
    # inherited limit; zero means unbounded and is replaced by our finite cap.
    db.execute(text("""SELECT name, set_config(name,
        CASE WHEN setting::bigint=0 THEN bounds.ms
             ELSE LEAST(setting::bigint,bounds.ms) END::text,true)
        FROM pg_settings CROSS JOIN LATERAL (
            SELECT CASE WHEN name='lock_timeout' THEN 2000 ELSE 5000 END AS ms
        ) bounds WHERE name IN ('statement_timeout','lock_timeout')"""))


def read_county_budget_record_ids(factory, *, ingestion_id):
    """Select exact persisted lineage for a completed job; overflow never truncates."""
    _positive_id(ingestion_id)
    db = factory()
    if db.new or db.dirty or db.deleted or db.identity_map or db.in_transaction():
        raise SourceObservationUnavailable("Fresh committed-reader session required")
    with db:
        if db.get_bind().dialect.name != "postgresql":
            raise SourceObservationUnavailable("PostgreSQL committed snapshot required")
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        _read_limits(db)
        job = db.get(IngestionJob, ingestion_id)
        if (job is None or job.domain != "counties_budget" or job.dry_run is not False
                or job.status != IngestionStatus.COMPLETED or job.finished_at is None
                or type(job.errors) is not list or job.errors
                or not isinstance(job.meta, dict) or job.meta.get("source_mode") != "live"):
            raise SourceObservationUnavailable("Committed successful live CoB ingestion required")
        ids = tuple(db.scalars(select(BudgetLine.id).where(
            BudgetLine.provenance.contains([{"ingestion_job_id": ingestion_id}]))
            .order_by(BudgetLine.id).limit(1001)))
        if len(ids) > 1000:
            raise SourceObservationUnavailable("Bounded exact ingestion lineage required")
        return ids


def read_county_budget_observation(factory, *, record_id, ingestion_id):
    """Return one exact-decimal actual-spending fact, or a specific refusal.

    Version is the durable ingestion ID, not a social event sequence; generation
    owns semantic fingerprinting and the atomic event/version decision. Only
    this explicit record is read. Publication date must be stored evidence, never
    inferred from a fiscal year or retrieval timestamp.
    """
    _positive_id(record_id)
    _positive_id(ingestion_id)
    db = factory()
    # Do not enter/close an existing writer on refusal: Session.__exit__ would
    # roll back its transaction. A cached identity map can also predate commit.
    if db.new or db.dirty or db.deleted or db.identity_map or db.in_transaction():
        raise SourceObservationUnavailable("Fresh committed-reader session required")
    with db:
        if db.get_bind().dialect.name != "postgresql":
            raise SourceObservationUnavailable("PostgreSQL committed snapshot required")
        # All lineage/quantity/qualification reads see one committed snapshot.
        # READ ONLY additionally refuses accidental writes through this seam.
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        _read_limits(db)
        now = db.scalar(select(func.current_timestamp()))
        job = db.execute(select(IngestionJob,
            func.timezone(func.current_setting("TimeZone"), IngestionJob.started_at),
            func.timezone(func.current_setting("TimeZone"), IngestionJob.finished_at))
            .where(IngestionJob.id == ingestion_id)).one_or_none()
        if job is None:
            raise SourceObservationUnavailable("Committed successful live CoB ingestion required")
        job, started, finished = job
        if (job is None or job.domain != "counties_budget" or job.dry_run is not False
                or job.status != IngestionStatus.COMPLETED or job.finished_at is None
                or type(job.errors) is not list or job.errors
                or not isinstance(job.meta, dict) or job.meta.get("source_mode") != "live"):
            raise SourceObservationUnavailable("Committed successful live CoB ingestion required")
        if started is None or finished is None or not started <= finished <= now:
            raise SourceObservationUnavailable("Stored ingestion chronology invalid")
        row = db.get(BudgetLine, record_id)
        if (row is None or row.publishable is not True or row.quarantine_reason or budget_line_is_unreported(row)
                or row.currency != "KES" or not isinstance(row.provenance, list)):
            raise SourceObservationUnavailable("Publishable actual CoB record required")
        entries = [entry for entry in row.provenance if isinstance(entry, dict)
                   and type(entry.get("ingestion_job_id")) is int
                   and entry["ingestion_job_id"] == ingestion_id
                   and entry.get("data_quality") == "official"]
        if len(entries) != 1:
            raise SourceObservationUnavailable("Exact record ingestion lineage unavailable")
        q = qualify_rows(db, "budget_lines", [row])[row.id]["actual_spent"]
        if (q["status"] != "verified" or q["source_kind"] != "pdf"
                or q["document_bytes_checked"] is not True or q["value_checked"] is not True
                or q["identity"]["basis"] != "actual"
                or q["source_document_id"] != row.source_document_id
                or q["digest"] != entries[0].get("artifact_sha256")):
            raise SourceObservationUnavailable("Verified measure-specific PDF evidence required")
        linked = entries[0].get("source_evidence")
        if not isinstance(linked, list) or not any(
                isinstance(e, dict) and isinstance(e.get("receipt"), dict)
                and e["receipt"].get("extraction_id") == q["receipt_id"]
                and e["receipt"].get("digest") == q["digest"]
                and isinstance(e.get("identity"), dict)
                and e["identity"].get("measure") == "actual_spent" for e in linked):
            raise SourceObservationUnavailable("Qualified evidence ingestion lineage unavailable")
        doc = db.get(SourceDocument, row.source_document_id)
        try:
            url = urlsplit(doc.url)
            if (doc.status != DocumentStatus.AVAILABLE or url.scheme != "https"
                    or url.hostname not in ("cob.go.ke", "www.cob.go.ke")
                    or url.username or url.password or url.port not in (None, 443)):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise SourceObservationUnavailable("Official available CoB document required") from None
        meta = doc.meta if isinstance(doc.meta, dict) else {}
        try:
            published = date.fromisoformat(meta["publication_date"])
        except (ValueError, TypeError, KeyError):
            raise SourceObservationUnavailable("Publisher publication date unavailable") from None
        extraction = db.get(Extraction, q["receipt_id"])
        receipt = extraction.extracted_json["response_receipt"]
        if receipt["request_url"] != doc.url:
            raise SourceObservationUnavailable("Exact acquired document URL required")
        retrieved = _aware(receipt["acquired_at"])
        verified = _aware(receipt["byte_check"]["checked_at"])
        if published > retrieved.date() or not retrieved <= verified <= finished <= now:
            raise SourceObservationUnavailable("Stored evidence chronology invalid")
        entity = db.get(Entity, row.entity_id)
        if entity is None or not entity.canonical_name:
            raise SourceObservationUnavailable("Source entity unavailable")
        amount = format(Decimal(row.actual_spent), "f")
        if not re.fullmatch(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,8})?", amount):
            raise SourceObservationUnavailable("Bounded exact monetary value required")
        locator = q["locator"]
        if not isinstance(locator, dict) or type(locator.get("page")) is not int or locator["page"] <= 0:
            raise SourceObservationUnavailable("PDF page locator unavailable")
        fact = {
            "fact_id": f"budget_lines:{row.id}:actual_spent", "entity": entity.canonical_name,
            "metric": f"Actual spending: {row.category}" + (f" / {row.subcategory}" if row.subcategory else ""),
            "period": q["identity"]["period"], "comparison_basis": "actual expenditure, same category and reporting period",
            "value": amount, "unit": "KES", "scale": "units", "classification": "actual",
            "source_document_id": doc.id, "document_url": doc.url,
            "locator": f"PDF page {locator['page']}; table {locator.get('table', 'unspecified')}; cell {locator.get('cell', 'unspecified')}",
            "document_checksum": q["digest"], "publisher": doc.publisher,
            "published_on": published.isoformat(), "retrieved_at": retrieved.isoformat(),
            "verified_at": verified.isoformat(), "canonical_url": f"https://www.auditgava.com/counties/{entity.id}",
        }
        if any(not isinstance(fact[key], str) or not fact[key].strip() or len(fact[key]) > 300
               for key in ("entity", "metric", "period", "locator", "publisher")):
            raise SourceObservationUnavailable("Bounded fact text required")
        return {"schema_version": 1, "source_type": "cob", "source_key": fact["fact_id"],
                "evidence_version": ingestion_id, "ingestion_id": str(ingestion_id),
                "category": "budget_update", "title": f"{entity.canonical_name} expenditure data",
                "committed": True, "fixture": False, "quarantined": False,
                "publishable": True, "correction_pending": False, "facts": [fact]}
