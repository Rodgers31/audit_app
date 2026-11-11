"""Run reviewed PDF parsing without changing the extraction parser identity."""
from ...isolated_parser import isolated
from .parser import parse_publication
from .source import CraSourceRefused


@isolated("payload", errors=(CraSourceRefused,))
def decode_publication(payload):
    return parse_publication(payload)
