"""Layer 3 — extractors: source document → ``extractions`` rows.

The middle link of the provenance chain. Every extractor takes a fetched
``SourceDocument`` (bytes on disk, md5 recorded) and writes one
``extractions`` row per finding/figure with the page it came from.

Parser ids are declared in the Layer-1 source registry; this module maps
them to implementations. A dataset with ``parser_id=None`` is fetched and
registered but never extracted — the honest state until a parser exists.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from .oag_blue_book import extract_blue_book
from .oag_county_audit import extract_county_audit

PARSERS: Dict[str, Callable] = {
    "oag_blue_book": extract_blue_book,
    "oag_county_audit": extract_county_audit,
}


def get_parser(parser_id: Optional[str]) -> Optional[Callable]:
    if parser_id is None:
        return None
    return PARSERS.get(parser_id)


__all__ = ["PARSERS", "get_parser"]
