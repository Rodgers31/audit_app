"""Explicit GDP/GCP levels crossing the parser, transport and loader boundary."""
import math
import re
from decimal import Decimal, InvalidOperation


def reported_gdp_level(value):
    """Missing is absent; finite nonnegative numbers/text preserve reported zero.

    This validates the numeric representation only. Source, units, measure and
    period remain the caller's responsibility; it does not invent a GDP level
    from a growth rate or attest that a zero is an official national observation.
    """
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (int, float, Decimal, str))
    ):
        return None
    if isinstance(value, str):
        value = value.strip()
        if "," in value or " " in value:
            if not re.fullmatch(r"\d{1,3}(?:(?:,\d{3})+|(?: \d{3})+)(?:\.\d+)?", value):
                return None
            value = value.replace(",", "").replace(" ", "")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0:
            return None
        result = float(number)
        return result if math.isfinite(result) else None
    except (InvalidOperation, ValueError, OverflowError):
        return None
