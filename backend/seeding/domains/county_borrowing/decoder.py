"""Run reviewed PDF parsing without changing the extraction parser identity."""
from ...county_borrowing_contract import CountyBorrowingRefused, parse_publication
from ...isolated_parser import isolated


@isolated("payload", errors=(CountyBorrowingRefused,))
def decode_publication(key, payload):
    return parse_publication(key, payload)
