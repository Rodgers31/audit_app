"""Strict provider retry timing, with no shortening of a server's delay."""
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import re


def parse_retry_after(value, now):
    if (not isinstance(value,str) or not 1<=len(value)<=128 or not isinstance(now,datetime)
            or now.tzinfo is None or now.utcoffset() is None):
        return None
    try:
        if re.fullmatch(r'[0-9]{1,18}',value):
            result=now+timedelta(seconds=int(value))
        else:
            result=parsedate_to_datetime(value)
        return result if result.tzinfo is not None and result.utcoffset() is not None and result>now else None
    except (ValueError,TypeError,OverflowError):
        return None
