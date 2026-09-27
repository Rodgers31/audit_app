"""Every field on the Layer-1 source registry is read by code, or says it is not.

Issue #137 P4. ``SourceDataset.discovery_urls`` was declared on all six
registry entries, and the module docstring promised that the fetchers "decide
*where* from this table; nothing downstream hardcodes a URL". Nothing read the
field. The fetchers took their URLs from ``seeding/config.py`` (``SEED_*``
settings) or from literals of their own, and the audits fetcher queried search
terms that were not the two ``search=`` URLs the registry listed for it. A reader trusting the registry
would have edited a URL that no request ever used.

The rule enforced here is narrow on purpose: a field on ``SourceDataset`` must
either be READ somewhere in the backend (an attribute load, ``x.<field>``), or
be named in :data:`DOCUMENTATION_ONLY` with the reason it exists for humans.
A field that claims to steer the pipeline and is read by nothing fails.

Limit, stated rather than hidden: the reader search matches the attribute
NAME, not its receiver's type. A distinctive name (``discovery_urls``) is
decided exactly; a common one (``description``, ``dataset_id``) can be
satisfied by an unrelated object's attribute of the same name. This test is
therefore a necessary check on distinctive fields, not a proof for common ones.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

from seeding import source_registry
from seeding.source_registry import SOURCE_REGISTRY, SourceDataset

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

# Fields kept for the people reading the registry, with nothing in code
# consuming them. Each entry needs a reason; an entry without one is how a
# decorative field passes for an operational one.
DOCUMENTATION_ONLY = {
    "publisher_url": "the publisher's home page, for a human locating the source",
    "description": "what the dataset is, for a human reading the registry",
}


def _attribute_loads() -> set:
    """Every ``x.<name>`` read anywhere in the backend's own Python."""
    names: set = set()
    for path in _BACKEND.rglob("*.py"):
        rel = path.relative_to(_BACKEND).parts
        if rel[0] in {"tests", "venv", ".venv", ".venv313", "alembic"}:
            continue
        if "site-packages" in rel:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                names.add(node.attr)
    return names


def test_every_registry_field_is_read_or_declared_documentation():
    loads = _attribute_loads()
    unread = [
        f.name
        for f in dataclasses.fields(SourceDataset)
        if f.name not in loads and f.name not in DOCUMENTATION_ONLY
    ]
    assert unread == [], (
        f"SourceDataset field(s) {unread} are read by nothing in the backend. "
        "Either wire a reader, delete the field, or — if it exists only for "
        "humans — list it in DOCUMENTATION_ONLY with the reason."
    )


def test_documentation_only_names_real_fields():
    """A stale allowlist entry would exempt a field that no longer exists."""
    field_names = {f.name for f in dataclasses.fields(SourceDataset)}
    assert set(DOCUMENTATION_ONLY) <= field_names


def test_the_reader_search_can_see_a_real_reader():
    """Positive control: fields with known readers must be found.

    ``match_keywords`` is read at ``fiscal_summary/fetcher.py`` and
    ``audits/__init__.py``; ``parser_id`` at ``audits/__init__.py``. If the
    walk stopped finding them, the main test would pass for having looked at
    nothing.
    """
    loads = _attribute_loads()
    assert {"match_keywords", "parser_id"} <= loads


def test_docstring_does_not_claim_the_registry_supplies_urls():
    """The claim P4 found false must not survive the field it described."""
    doc = source_registry.__doc__ or ""
    assert "nothing downstream hardcodes a URL" not in doc
    assert "seeding/config.py" in doc, (
        "the docstring should say where fetch URLs actually live"
    )


def test_registry_still_serves_its_live_readers():
    """Deleting the field must not disturb what the fetchers do read."""
    budget = SOURCE_REGISTRY["treasury_budget_estimates"]
    assert budget.match_keywords == ("programme",)
    assert budget.parser_id == "treasury_pbb_gross"
    assert SOURCE_REGISTRY["oag_national_audits"].parser_id == "oag_blue_book"
    assert SOURCE_REGISTRY["oag_county_audits"].match_keywords == ("county",)
