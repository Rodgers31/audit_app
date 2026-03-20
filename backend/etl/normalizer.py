"""ETL normalizer for financial data transformations."""

import logging

from utils.exchange_rate import get_usd_kes_rate

logger = logging.getLogger(__name__)


def normalize_amount_to_kes(amount_usd: float) -> float:
    """Convert a USD amount to KES using the live exchange rate."""
    rate = get_usd_kes_rate()
    return round(amount_usd * rate, 2)


def normalize_amount_to_usd(amount_kes: float) -> float:
    """Convert a KES amount to USD using the live exchange rate."""
    rate = get_usd_kes_rate()
    return round(amount_kes / rate, 2)
