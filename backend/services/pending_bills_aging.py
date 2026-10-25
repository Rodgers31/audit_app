"""Read source-bound aging cohorts without substituting populations or editions.

The unscoped legacy buckets remain absent. Executive and assembly evidence
remain separate; neither establishes national or combined ages. Reads never
download source bytes.
"""
from __future__ import annotations

import re

from models import DebtCategory, Entity, EntityType, Extraction, Loan, SourceDocument
from sqlalchemy import and_, or_, select

SCOPES = ("county_executive", "county_assembly", "national", "combined")
EXTRACTOR = "pending-bills-aging-v1"
ASSEMBLY_EXTRACTOR = "pending-bills-assembly-aging-v2"
COHORTS = {
    "county_executive": ("pending_bills_aging_v1", EXTRACTOR),
    "county_assembly": ("pending_bills_assembly_aging_v2", ASSEMBLY_EXTRACTOR),
}


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
    active_batch = SourceDocument.meta["pending_bills_publication_batch"].astext

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
            or_(*[SourceDocument.meta[key]["as_at"].astext == as_at
                   for key, _ in COHORTS.values()]),
            same_binding,
            ~other_binding,
        )
        .limit(2)
        .all()
    )
    from seeding.domains.pending_bills.aging import public_observation

    for scope, (key, extractor) in COHORTS.items():
        candidates = []
        for doc in docs:
            meta = doc.meta if isinstance(doc.meta, dict) else {}
            ref = meta.get(key)
            if not isinstance(ref, dict) or ref.get("as_at") != as_at:
                continue
            batch = ref.get("publication_batch")
            if (
                not isinstance(batch, str)
                or re.fullmatch(r"[0-9a-f]{64}", batch) is None
                or batch != meta.get("pending_bills_publication_batch")
                or (stock_context is not None and stock_context != {(doc.id, batch)})
                or ref.get("source_url") != doc.url
                or type(ref.get("extraction_id")) is not int
            ):
                continue
            extraction = (
                db.query(Extraction)
                .populate_existing()
                .filter(
                    Extraction.id == ref["extraction_id"],
                    Extraction.source_document_id == doc.id,
                    Extraction.extractor == extractor,
                )
                .one_or_none()
            )
            if extraction is not None:
                candidates.append((doc, extraction, ref))
        if len(docs) > 1 or len(candidates) > 1:
            result[scope] = absent_observation(scope, "conflicting_source_editions")
        elif candidates:
            doc, extraction, ref = candidates[0]
            result[scope] = public_observation(db, doc, extraction, ref, county=county, scope=scope)
    return result
