"""Document transport evidence. Registration timestamps are not downloads.

A verified successful response with a recorded digest proves bytes landed.
Extraction and publication acceptance are separate signals at their callers.
"""

from datetime import datetime, timezone
from sqlalchemy import and_, func
from models import SourceDocument


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
