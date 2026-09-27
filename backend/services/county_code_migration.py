"""Reviewable metadata-only county-code correction; no database connection or writes."""
from copy import deepcopy

from services.county_identity import official_county_code, legacy_county_route_id


def propose_county_code_changes(entities):
    """Require exactly 47 distinct known identities and reject unexpected codes.

    The input is an Entity snapshot, including its PK, slug and raw metadata.
    Output contains exact before/after JSON suitable for guarded migration and
    reversal. IDs, slugs, names and all foreign keys remain untouched.
    """
    changes, seen, ids, slugs = [], set(), set(), set()
    for entity in entities:
        if type(entity.id) is not int or entity.id <= 0 or entity.id in ids:
            raise ValueError("Invalid or duplicate entity ID")
        if (
            not isinstance(entity.slug, str)
            or not entity.slug.strip()
            or entity.slug in slugs
        ):
            raise ValueError("Invalid or duplicate entity slug")
        ids.add(entity.id)
        slugs.add(entity.slug)
        kind = getattr(entity.type, "value", entity.type)
        if kind != "county":
            raise ValueError("Snapshot contains a non-county entity")
        code = official_county_code(entity.canonical_name)
        if code is None or code in seen:
            raise ValueError("Unknown or duplicate county identity")
        seen.add(code)
        before = entity.meta
        if not isinstance(before, dict):
            raise ValueError("County metadata must be an object")
        after = deepcopy(before)
        edits = []

        def update(obj, path, key):
            if key not in obj:
                return
            old = obj[key]
            if old not in (code, legacy_county_route_id(entity.canonical_name)):
                raise ValueError(
                    f"Unexpected code at {entity.id}/{path}/{key}: {old!r}"
                )
            if old != code:
                obj[key] = code
                edits.append({"path": [*path, key], "before": old, "after": code})

        for key in ("code", "county_code"):
            update(after, [], key)
        metrics = after.get("metrics", {})
        if not isinstance(metrics, dict):
            raise ValueError("County metrics must be an object")
        for year, values in metrics.items():
            if not isinstance(values, dict):
                raise ValueError("County period metrics must be an object")
            update(values, ["metrics", year], "county_code")
        if edits:
            changes.append(
                {
                    "entity_id": entity.id,
                    "canonical_name": entity.canonical_name,
                    "slug": entity.slug,
                    "edits": edits,
                    "before": deepcopy(before),
                    "after": after,
                }
            )
    if len(seen) != 47:
        raise ValueError("A complete 47-county snapshot is required")
    return changes
