"""Read source-bound aging cohorts without substituting populations or editions.

The unscoped legacy buckets remain absent: an executive aging table cannot
describe national bills or county assemblies. Reads never download source bytes.
"""
from __future__ import annotations

import re

from models import DebtCategory, Entity, EntityType, Extraction, Loan, SourceDocument
from sqlalchemy import and_, or_, select

SCOPES = ("county_executive", "county_assembly", "national", "combined")
EXTRACTOR = "pending-bills-aging-v1"


def absent_observation(scope, reason="no_source_bound_aging_observation"):
    return {
        "version": 1,
        "scope": scope,
        "status": "unavailable",
        "absent_reason": reason,
        "buckets": None,
        "complete_total": None,
    }


def aging_observations(db, *, as_at=None, county=None, stock_context=None):
    result = {scope: absent_observation(scope) for scope in SCOPES}
    if as_at is None or (stock_context is not None and not stock_context):
        return result
    from services.publication_gate import COUNTY_PENDING_BILLS_PUBLICATION

    # The document's retained pointer is history, not current publication
    # authority. Every presently published stock row on this date must agree
    # with the cohort's source AND batch. This also refuses mixed partial
    # replacements without deleting the older extraction/pointer history.
    current_stock = and_(
        Entity.type == EntityType.COUNTY,
        Loan.debt_category == DebtCategory.PENDING_BILLS,
        Loan.provenance["publication"].astext == COUNTY_PENDING_BILLS_PUBLICATION,
        Loan.provenance["category"].astext == "county",
        Loan.provenance["as_at"].astext == as_at,
    )
    active_batch = SourceDocument.meta["pending_bills_aging_v1"][
        "publication_batch"
    ].astext

    def active_stock_where(binding):
        return (
            select(1)
            .select_from(Loan)
            .join(Entity, Entity.id == Loan.entity_id)
            .where(current_stock, binding)
            .correlate(SourceDocument)
            .exists()
        )

    same_binding = active_stock_where(
        and_(
            Loan.source_document_id == SourceDocument.id,
            Loan.provenance["publication_batch"].astext == active_batch,
        )
    )
    other_binding = active_stock_where(
        or_(
            Loan.source_document_id.is_(None),
            Loan.source_document_id != SourceDocument.id,
            Loan.provenance["publication_batch"].astext.is_(None),
            Loan.provenance["publication_batch"].astext != active_batch,
        )
    )
    # Metadata points at one immutable extraction. A title or latest source
    # document cannot establish a prior observation's artifact identity.
    docs = (
        db.query(SourceDocument)
        .populate_existing()
        .filter(
            SourceDocument.publisher == "Office of the Controller of Budget (OCOB)",
            SourceDocument.meta["pending_bills_aging_v1"]["as_at"].astext == as_at,
            same_binding,
            ~other_binding,
        )
        .limit(2)
        .all()
    )
    if len(docs) > 1:
        result["county_executive"] = absent_observation(
            "county_executive", "conflicting_source_editions"
        )
        return result
    candidates = []
    for doc in docs:
        meta = doc.meta if isinstance(doc.meta, dict) else {}
        ref = meta.get("pending_bills_aging_v1")
        if not isinstance(ref, dict) or ref.get("as_at") != as_at:
            continue
        batch = ref.get("publication_batch")
        if (
            not isinstance(batch, str)
            or re.fullmatch(r"[0-9a-f]{64}", batch) is None
            or batch != meta.get("pending_bills_publication_batch")
        ):
            continue
        # The caller may have read stock before a concurrent publication
        # committed. Its immutable bindings must agree with this read too.
        if stock_context is not None and stock_context != {(doc.id, batch)}:
            continue
        if ref.get("source_url") != doc.url:
            continue
        if type(ref.get("extraction_id")) is not int:
            continue
        extraction = (
            db.query(Extraction)
            .populate_existing()
            .filter(
                Extraction.id == ref["extraction_id"],
                Extraction.source_document_id == doc.id,
                Extraction.extractor == EXTRACTOR,
            )
            .one_or_none()
        )
        if extraction is not None:
            candidates.append((doc, extraction, ref))
    if len(candidates) != 1:
        if candidates:
            result["county_executive"] = absent_observation(
                "county_executive", "conflicting_source_editions"
            )
        return result
    doc, extraction, ref = candidates[0]
    from seeding.domains.pending_bills.aging import public_observation

    result["county_executive"] = public_observation(
        db, doc, extraction, ref, county=county
    )
    return result
