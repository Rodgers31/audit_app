"""What ``enhanced_county_data.json`` modelled into ``entity.meta``, and its removal.

This lives outside ``bootstrap`` for one reason: the Alembic revision that
clears production has to import it, and the ``run-migrations`` CI job installs
only ``alembic sqlalchemy psycopg2-binary``. ``bootstrap`` imports
``database``, which imports ``dotenv`` unguarded, so a migration that reached
the rule through ``bootstrap`` died at import with ``ModuleNotFoundError`` —
and that job is skipped on pull requests, so no PR check would ever have shown
it. It sits at the top level rather than under ``services`` for the same reason:
``services/__init__.py`` imports ``auto_seeder``, which imports ``database``,
so importing anything from that package pulls the whole runtime in behind it.

The rule stays in ONE place: ``bootstrap`` imports these names rather than
restating them, so the writer, the migration and the tests cannot drift.
"""

from __future__ import annotations

from typing import Dict

from models import Entity, EntityType
from sqlalchemy.orm import Session


#: Every metric key the county loop ever wrote from that file, so the purge
#: below removes what is STORED rather than whatever is absent from a
#: keep-list — a keep-list would quietly delete a key some later writer adds.
#:
#: ``county_code`` is deliberately not here. It is an identifier, not a claim
#: about money or people, and it has live readers: ``/search`` and the entity
#: listing serve it out of this dict. ``source_note`` is not written by the county
#: loop at all; it is an earlier seeder's marker ("placeholder-seed") that
#: production still carries beside the rest, and it describes the same figures.
PURGED_METRIC_FIELDS = frozenset(
    {
        "population",
        "budget_2025",
        "revenue_2024",
        "local_revenue",
        "debt_outstanding",
        "pending_bills",
        "missing_funds",
        "budget_execution_rate",
        "audit_rating",
        "financial_health_score",
        "debt_to_budget_ratio",
        "pending_bills_ratio",
        "per_capita_budget",
        "source_note",
    }
)

#: The second copy: seven of the same figures again, under their own key.
#: Nothing reads it — ``main.py`` bound it to a local it never used, and that
#: local is gone too — but clearing ``metrics`` and leaving this would take the
#: census green while the identical numbers sat one key away.
PURGED_META_KEYS = frozenset({"financial_metrics"})


def purge_modelled_county_metrics(session: Session) -> Dict[str, int]:
    """Delete the figures this file modelled from ``entity.meta``.

    Each of them now has a live source or is deliberately withheld:

        budget_2025, per_capita_budget      Controller of Budget, CBIRR
        revenue_2024, local_revenue         CBIRR own-source revenue table
        pending_bills, pending_bills_ratio  Treasury BROP Table 10
        population                          KNBS 2019 Census, Table 2.2
        debt_outstanding, debt_to_budget…   withheld: no publisher
        missing_funds                       withheld: no source document
        budget_execution_rate               computed from budget lines
        financial_health_score              computed, components disclosed
        audit_rating                        derived from OAG finding severity

    None of them reaches a response any more, which is exactly why they had to
    go: a figure that is stored but unserved is one endpoint away from served,
    and it keeps the fixture census red for a reader who cannot see it.

    Idempotent, and safe on a database that never held them.
    """
    changed = 0
    fields_removed = 0
    keys_removed = 0

    for entity in session.query(Entity).filter(Entity.type == EntityType.COUNTY):
        meta = dict(entity.meta or {})
        touched = False

        metrics = meta.get("metrics")
        if isinstance(metrics, dict):
            rebuilt = {}
            for fy, by_year in metrics.items():
                if not isinstance(by_year, dict):
                    rebuilt[fy] = by_year
                    continue
                kept = {
                    k: v
                    for k, v in by_year.items()
                    if k not in PURGED_METRIC_FIELDS
                }
                fields_removed += len(by_year) - len(kept)
                if len(kept) != len(by_year):
                    touched = True
                rebuilt[fy] = kept
            meta["metrics"] = rebuilt

        for key in PURGED_META_KEYS:
            if key in meta:
                del meta[key]
                keys_removed += 1
                touched = True

        if touched:
            # JSONB is not mutation-tracked, so the column only travels on a
            # fresh object.
            entity.meta = meta
            session.add(entity)
            changed += 1

    return {
        "entities_changed": changed,
        "metric_fields_removed": fields_removed,
        "meta_keys_removed": keys_removed,
    }
