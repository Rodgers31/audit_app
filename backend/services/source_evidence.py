"""Document transport evidence. Registration timestamps are not downloads.

A verified successful response with a recorded digest proves bytes landed.
Extraction and publication acceptance are separate signals at their callers.
"""

from datetime import datetime, timezone
from sqlalchemy import and_, func, not_, or_
from models import SourceDocument


def publisher_inventory_criterion():
    """Exclude declared app artefacts from the public publisher inventory.

    Ordinary publisher estimates and archived official documents remain
    registrations, whether or not transport/extraction evidence exists.
    The two legacy markers are exact stored origins from the retired county
    fixture and formula generator; IDs and government-looking URLs confer
    no publisher authority.
    """

    def text_member(key):
        return func.lower(
            func.trim(func.coalesce(SourceDocument.meta[key].as_string(), ""))
        )

    app_origin = or_(
        text_member("source_classification").in_(("test_fixture", "modelled_estimate")),
        text_member("dataset_id") == "fixture-budgets",
        text_member("source_label")
        == "estimated based on cra equitable share fy 2023/24",
    )
    return not_(app_origin)


def downloaded_document_criterion():
    digest = func.lower(SourceDocument.md5)
    for char in "0123456789abcdef":
        digest = func.replace(digest, char, "")
    return and_(
        SourceDocument.http_status == 200,
        SourceDocument.md5.isnot(None),
        func.length(SourceDocument.md5) == 32,
        digest == "",
        SourceDocument.last_verified_at.isnot(None),
        SourceDocument.last_verified_at <= datetime.now(timezone.utc),
    )
